#!/usr/bin/env python3
"""Recover GitHub Actions runs stuck in non-terminal states.

The script first ignores active runs younger than the configured stale
threshold. For stale runs it requests a normal cancellation, then a force
cancellation. If a stale run still remains non-terminal, it finally attempts
deletion. It never acts on its own workflow run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable

ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
TERMINAL_STATUSES = {"completed"}
API_VERSION = "2022-11-28"


@dataclass(frozen=True)
class Response:
    status: int
    body: str


class GitHubAPI:
    def __init__(
        self,
        repository: str,
        token: str,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.token = token
        self.opener = opener
        self.sleep = sleep
        self.base = f"https://api.github.com/repos/{repository}"

    def request(
        self,
        method: str,
        path: str,
        *,
        retries: int = 5,
        retryable: Iterable[int] = (500, 502, 503, 504),
    ) -> Response:
        url = f"{self.base}{path}"
        retryable_set = set(retryable)
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(
                url,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": API_VERSION,
                    "User-Agent": "linux-charcoal-actions-recovery",
                },
            )
            try:
                with self.opener(req, timeout=30) as response:
                    body = response.read().decode("utf-8", "replace")
                    return Response(int(response.status), body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                if exc.code in retryable_set and attempt < retries:
                    self.sleep(min(2 ** attempt, 16))
                    continue
                return Response(int(exc.code), body)
            except urllib.error.URLError as exc:
                if attempt < retries:
                    self.sleep(min(2 ** attempt, 16))
                    continue
                return Response(0, str(exc))
        raise AssertionError("unreachable")

    def get_run(self, run_id: int) -> tuple[Response, dict[str, Any] | None]:
        response = self.request("GET", f"/actions/runs/{run_id}")
        if response.status != 200:
            return response, None
        return response, json.loads(response.body)

    def list_active_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        page = 1
        while page <= 10:
            response = self.request(
                "GET", f"/actions/runs?per_page=100&page={page}", retries=3
            )
            if response.status != 200:
                raise RuntimeError(
                    f"unable to list workflow runs: HTTP {response.status}: "
                    f"{response.body[:300]}"
                )
            payload = json.loads(response.body)
            batch = payload.get("workflow_runs", [])
            runs.extend(item for item in batch if item.get("status") in ACTIVE_STATUSES)
            if len(batch) < 100:
                break
            page += 1
        return runs

    def cancel(self, run_id: int, endpoint: str) -> Response:
        return self.request("POST", f"/actions/runs/{run_id}/{endpoint}")

    def delete(self, run_id: int) -> Response:
        return self.request("DELETE", f"/actions/runs/{run_id}", retries=3)


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def age_minutes(run: dict[str, Any], now: dt.datetime) -> float:
    created = parse_timestamp(run.get("created_at")) or parse_timestamp(
        run.get("run_started_at")
    )
    if created is None:
        return 0.0
    return max(0.0, (now - created).total_seconds() / 60.0)


def poll_terminal(
    api: GitHubAPI,
    run_id: int,
    *,
    attempts: int = 6,
    interval: float = 5.0,
) -> tuple[bool, dict[str, Any] | None, Response]:
    last_response = Response(0, "")
    last_run: dict[str, Any] | None = None
    for _ in range(attempts):
        last_response, last_run = api.get_run(run_id)
        if last_response.status == 404:
            return True, None, last_response
        if last_response.status == 200 and last_run:
            if last_run.get("status") in TERMINAL_STATUSES:
                return True, last_run, last_response
        api.sleep(interval)
    return False, last_run, last_response


def recover_run(
    api: GitHubAPI,
    run_id: int,
    *,
    self_run_id: int | None,
    stale_minutes: int,
    now: dt.datetime,
) -> dict[str, Any]:
    if self_run_id is not None and run_id == self_run_id:
        return {"run_id": run_id, "result": "self-skipped"}

    initial_response, run = api.get_run(run_id)
    if initial_response.status == 404:
        return {"run_id": run_id, "result": "already-gone"}
    if initial_response.status != 200 or run is None:
        return {
            "run_id": run_id,
            "result": "inspect-failed",
            "http": initial_response.status,
            "body": initial_response.body[:300],
        }
    if run.get("status") in TERMINAL_STATUSES:
        return {
            "run_id": run_id,
            "result": "already-terminal",
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
        }

    # A recovery pass must never disrupt a healthy new build. The stale
    # threshold gates cancellation itself, not merely the final deletion.
    initial_age = age_minutes(run, now)
    if initial_age < stale_minutes:
        return {
            "run_id": run_id,
            "result": "not-stale",
            "status": run.get("status"),
            "age_minutes": round(initial_age, 1),
            "stale": False,
        }

    actions: list[dict[str, Any]] = []
    for endpoint in ("cancel", "force-cancel"):
        response = api.cancel(run_id, endpoint)
        actions.append(
            {
                "action": endpoint,
                "http": response.status,
                "body": response.body[:300],
            }
        )
        done, polled, _ = poll_terminal(api, run_id)
        if done:
            return {
                "run_id": run_id,
                "result": f"{endpoint}-resolved",
                "actions": actions,
                "final": polled,
            }

    current_response, current = api.get_run(run_id)
    current = current or run
    stale = age_minutes(current, now) >= stale_minutes
    if stale:
        response = api.delete(run_id)
        actions.append(
            {
                "action": "delete",
                "http": response.status,
                "body": response.body[:300],
            }
        )
        done, polled, _ = poll_terminal(api, run_id, attempts=3, interval=3)
        if done:
            return {
                "run_id": run_id,
                "result": "delete-resolved",
                "actions": actions,
                "final": polled,
            }

    return {
        "run_id": run_id,
        "result": "unresolved",
        "status": current.get("status"),
        "age_minutes": round(age_minutes(current, now), 1),
        "stale": stale,
        "http": current_response.status,
        "actions": actions,
    }


def parse_run_ids(values: list[str]) -> list[int]:
    result: set[int] = set()
    for value in values:
        for token in value.replace(",", " ").split():
            if token:
                result.add(int(token))
    return sorted(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/repository",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
    )
    parser.add_argument(
        "--self-run-id",
        type=int,
        default=int(os.environ["GITHUB_RUN_ID"])
        if os.environ.get("GITHUB_RUN_ID")
        else None,
    )
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--include-all-active", action="store_true")
    parser.add_argument("--stale-minutes", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.repository:
        raise SystemExit("--repository or GITHUB_REPOSITORY is required")
    if not args.token:
        raise SystemExit("--token, GH_TOKEN or GITHUB_TOKEN is required")
    if args.stale_minutes < 1:
        raise SystemExit("--stale-minutes must be at least 1")

    api = GitHubAPI(args.repository, args.token)
    run_ids = set(parse_run_ids(args.run_id))
    if args.include_all_active:
        run_ids.update(int(item["id"]) for item in api.list_active_runs())

    now = dt.datetime.now(dt.timezone.utc)
    results = [
        recover_run(
            api,
            run_id,
            self_run_id=args.self_run_id,
            stale_minutes=args.stale_minutes,
            now=now,
        )
        for run_id in sorted(run_ids)
    ]
    print(json.dumps({"repository": args.repository, "results": results}, indent=2))

    unresolved = [item for item in results if item["result"] in {"unresolved", "inspect-failed"}]
    return 2 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
