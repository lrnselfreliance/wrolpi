#!/usr/bin/env python3
"""Publish the AI model catalog to the WROLPi CDN.

For every model in modules/ai/catalog.py AI_MODELS this expects the GGUF file in MODELS_DIR,
then produces and uploads (the same trust chain the maps use):
  - <model>.gguf.meta4   Metalink4 with size, sha-256, and a GPG signature of the hash
                         (aria2c enforces the hash; WROLPi GPG-verifies it before download)
  - ai/models.json       the manifest, with the real sha256/size values
  - ai/models.json.sig   detached GPG signature of the manifest

Run on a machine with the roland@learningselfreliance.com secret key and an s3cmd configured
for the wrolpi Spaces bucket:

    python3 wrolpi/scripts/publish_ai_models.py <models_dir> [--upload]

Afterwards, copy the printed sha256/size values into AI_MODELS (the bundled offline catalog).
"""
import argparse
import json
import pathlib
import subprocess
import sys

PROJECT_DIR = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from modules.ai.catalog import AI_MODELS, MODELS_MANIFEST_URL  # noqa: E402
from wrolpi.scripts.build_map_regions import generate_meta4, sha256_file, sign_hash  # noqa: E402

BUCKET = 's3://wrolpi/ai'
GPG_UID = 'roland@learningselfreliance.com'


def sign_file(path: pathlib.Path) -> pathlib.Path:
    sig_path = path.with_suffix(path.suffix + '.sig')
    sig_path.unlink(missing_ok=True)
    subprocess.run(['gpg', '--batch', '-u', GPG_UID, '--detach-sign', '--armor',
                    '-o', str(sig_path), str(path)], check=True)
    return sig_path


def upload(path: pathlib.Path):
    subprocess.run(['s3cmd', 'put', '--acl-public', str(path), f'{BUCKET}/{path.name}'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models_dir', type=pathlib.Path)
    parser.add_argument('--upload', action='store_true', help='Upload to the CDN with s3cmd')
    args = parser.parse_args()

    manifest_models = []
    artifacts = []
    for model in AI_MODELS:
        path = args.models_dir / model['name']
        if not path.is_file():
            print(f'MISSING: {path} — download it first', file=sys.stderr)
            return 1

        size = path.stat().st_size
        print(f'Hashing {model["name"]} ({size:,} bytes)...')
        sha256 = sha256_file(str(path))
        signature = sign_hash(sha256)
        meta4_path = pathlib.Path(f'{path}.meta4')
        meta4_path.write_text(generate_meta4(model['name'], model['url'], sha256, size, signature))
        print(f'  sha256 {sha256}')

        manifest_models.append(dict(model, sha256=sha256, size=size,
                                    meta4_url=f'{model["url"]}.meta4'))
        artifacts += [path, meta4_path]

    manifest_path = args.models_dir / 'models.json'
    manifest_path.write_text(json.dumps(dict(version=1, models=manifest_models), indent=2) + '\n')
    sig_path = sign_file(manifest_path)
    artifacts += [manifest_path, sig_path]
    print(f'Manifest written: {manifest_path} (URL: {MODELS_MANIFEST_URL})')

    if args.upload:
        for path in artifacts:
            print(f'Uploading {path.name}...')
            upload(path)
        print('Upload complete.')
    else:
        print('\nDry run (no --upload).  Artifacts ready:')
        for path in artifacts:
            print(f'  {path}')

    print('\nCopy these real values into modules/ai/catalog.py AI_MODELS:')
    for model in manifest_models:
        print(f'  {model["name"]}: sha256={model["sha256"]} size={model["size"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
