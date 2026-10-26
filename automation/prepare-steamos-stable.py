#!/usr/bin/env python3
"""Follow Valve's stable image, its exact kernel package and matching source repo.

Do not infer stable from the largest source-index directory or kernel filename:
those indices also contain development packages and historical kernel lines.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('steamos_source', ROOT / 'automation/prepare-steamos-7.2.py')
SOURCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SOURCE
SPEC.loader.exec_module(SOURCE)

STABLE_URL = 'https://steamdeck-atomupd.steamos.cloud/meta/holo/steamos/amd64/steamdeck/stable.json'
IMAGES_URL = 'https://steamdeck-images.steamos.cloud/'
SOURCES_URL = 'https://steamdeck-packages.steamos.cloud/archlinux-mirror/sources/'


def stable_image(metadata: dict) -> dict:
    candidates = []
    for group in metadata.values():
        if not isinstance(group, dict):
            continue
        for candidate in group.get('candidates', []):
            image = candidate.get('image', {})
            if (image.get('branch') != 'stable' or image.get('product') != 'steamos'
                    or image.get('arch') != 'amd64' or image.get('variant') != 'steamdeck'):
                continue
            version = str(image.get('version', ''))
            build = str(image.get('buildid', ''))
            if not re.fullmatch(r'\d+\.\d+(?:\.\d+)*', version) or not re.fullmatch(r'\d+(?:\.\d+)*', build):
                raise ValueError('invalid stable image version/build ID')
            candidates.append(image)
    if not candidates:
        raise ValueError('Valve metadata contains no SteamOS stable image; refusing preview fallback')
    return max(candidates, key=lambda i: (tuple(map(int, i['version'].split('.'))), tuple(map(int, i['buildid'].split('.')))))


def kernel_package(packages: str) -> tuple[str, str, str]:
    kernels = []
    for line in packages.splitlines():
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r'linux-neptune-\d+', fields[0]):
            continue
        match = re.fullmatch(r'(\d+\.\d+\.\d+\.valve\d+(?:\.\d+)*)-(\d+)', fields[1])
        if not match:
            raise ValueError(f'unsupported stable kernel package: {line}')
        series = '.'.join(match[1].split('.')[:2])
        if fields[0] != 'linux-neptune-' + series.replace('.', ''):
            raise ValueError('kernel package suffix disagrees with kernel series')
        kernels.append((fields[0], match[1], match[2]))
    if len(kernels) != 1:
        raise ValueError(f'expected exactly one stock kernel in stable image, found {kernels}')
    return kernels[0]


def prepare(metadata: dict, package_list: str, base: dict, overrides: dict) -> tuple[dict, dict, dict]:
    image = stable_image(metadata)
    stock, pkgver, pkgrel = kernel_package(package_list)
    series = '.'.join(pkgver.split('.')[:2])
    suffix = series.replace('.', '')
    os_series = '.'.join(image['version'].split('.')[:2])
    index = urljoin(SOURCES_URL, f'jupiter-{os_series}/')
    filename = f'{stock}-{pkgver}-{pkgrel}.src.tar.gz'
    package = SOURCE.NeptunePackage(filename, pkgver, int(pkgrel), urljoin(index, filename))
    manifest = json.loads(json.dumps(base))
    manifest['kernel_source'] = {
        'repository': 'evlaV/linux-integration', 'series': series,
        'preferred_tag': package.tag, 'allow_prerelease': False,
        'tag_regex': rf'(?P<version>{re.escape(series)}\.\d+)-valve(?P<valve>[0-9.]+)',
    }
    policy = json.loads(json.dumps(overrides))
    for group in ('components', 'auxiliary_components'):
        for values in policy.get(group, {}).values():
            if values.get('port_for_kernel') == '7.2':
                values['port_for_kernel'] = series
    record = {
        'schema': 2, 'channel': 'stable', 'stable_metadata_url': STABLE_URL,
        'image': image, 'source_index': index, 'kernel_series': series,
        'pkgbase': f'linux-charcoal-{suffix}', 'stock_pkgbase': stock,
        'tag': package.tag, 'package': {'filename': filename, 'pkgver': pkgver, 'pkgrel': int(pkgrel), 'url': package.url},
        'ports_baseline': '7.2', 'requires_patch_preflight': True,
    }
    return manifest, policy, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-fixture', type=Path)
    parser.add_argument('--packages-fixture', type=Path)
    parser.add_argument('--fetch-config', action='store_true')
    args = parser.parse_args()
    raw = json.loads(args.metadata_fixture.read_text() if args.metadata_fixture else SOURCE.fetch_text(STABLE_URL))
    image = stable_image(raw)
    manifest_url = urljoin(IMAGES_URL, f"steamdeck/{image['buildid']}/steamdeck-{image['buildid']}-{image['version']}.manifest.pacman")
    packages = args.packages_fixture.read_text() if args.packages_fixture else SOURCE.fetch_text(manifest_url)
    base = json.loads((ROOT / 'automation/patch-sources.json').read_text())
    policy = json.loads((ROOT / 'automation/patch-source-overrides-7.2.json').read_text())
    manifest, policy, record = prepare(raw, packages, base, policy)
    record['package_manifest_url'] = manifest_url
    # Confirm the exact shipped package exists in the OS-version-derived repo.
    if not args.packages_fixture:
        links = SOURCE.LinkParser()
        links.feed(SOURCE.fetch_text(record['source_index']))
        if record['package']['filename'] not in links.hrefs:
            raise ValueError('exact stable image kernel source is absent from its corresponding source index')
    logs = ROOT / 'logs'
    logs.mkdir(exist_ok=True)
    if args.fetch_config:
        with SOURCE.request(record['package']['url'], timeout=180) as stream:
            record['config_member'] = SOURCE.extract_config_from_tar(stream, ROOT / 'config')
    for name, data in (('patch-sources-7.2.json', manifest), ('patch-source-overrides-stable.json', policy), ('steamos-stable-source.json', record)):
        (logs / name).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    pkgbuild = ROOT / 'PKGBUILD'
    text = pkgbuild.read_text()
    for name, value in (('pkgbase', record['pkgbase']), ('_nepbase', record['stock_pkgbase']), ('_tag', record['tag'])):
        text, count = re.subn(rf'(?m)^{name}=.*$', f'{name}={value}', text, count=1)
        if count != 1:
            raise ValueError(f'missing PKGBUILD assignment: {name}')
    pkgbuild.write_text(text)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, SOURCE.PrepareError) as exc:
        raise SystemExit(f'SteamOS stable resolution failed: {exc}')
