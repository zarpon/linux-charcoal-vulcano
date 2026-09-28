from pathlib import Path


workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "push.yml"
workflow = workflow_path.read_text(encoding="utf-8")
start = workflow.index('release_is_stable="$(gh release view')
end = workflow.index('gh release upload "$RELEASE_TAG"', start)
verification = workflow[start:end]

assert "--json isDraft,isPrerelease" in verification
assert "--json isPrerelease,isLatest" not in verification
assert "gh api \"repos/${GITHUB_REPOSITORY}/releases/latest\" --jq '.tag_name'" in verification
assert '"$release_is_stable" != "true"' in verification
assert '"$latest_release_tag" != "$RELEASE_TAG"' in verification
