#!/usr/bin/env python3
"""One local gate for repository, Python, native and optional original-assets tests."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=ROOT / 'build/port-src')
    p.add_argument('--build-dir', type=Path, default=ROOT / 'build/macos-arm64')
    p.add_argument('--developer-dir', type=Path, default=Path('/Applications/Xcode.app/Contents/Developer'))
    p.add_argument('--assets', type=Path, help='explicitly enable original-asset native tests using this extracted root')
    p.add_argument('--python-only', action='store_true', help='partial tooling validation; does not pass the native gate')
    args = p.parse_args()
    env = dict(os.environ, DEVELOPER_DIR=str(args.developer_dir.resolve()))
    commands = [[sys.executable, ROOT / 'tools/check_repository.py'],
                [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']]
    if not args.python_only:
        if not shutil.which('ctest') or not (args.build_dir / 'CTestTestfile.cmake').is_file():
            p.error('native test build missing: first run build_native.py macos --tests')
        commands.append(['ctest', '--test-dir', args.build_dir, '--output-on-failure', '-L', 'asset-free'])
        if not (args.build_dir / 'pt_touch_controls_test').is_file():
            p.error('native touch test missing: first run build_native.py macos --tests')
        commands.append([args.build_dir / 'pt_touch_controls_test'])
        commands.append([args.build_dir / 'pt_metal_capabilities_test', args.build_dir / 'tests/texture_descriptor.comp.spv'])
        from prepare_source import source_state
        manifest = json.loads((args.build_dir / 'build-wrapper-inputs.json').read_text())
        if manifest.get('status') != 'built' or manifest.get('source_tree_sha256') != source_state(args.source):
            p.error('native build does not identify this completed source recipe; rebuild first')
        if args.assets:
            if not (args.assets / 'chunk1.psarc').is_file() or not (args.assets / 'texture.qar').is_file():
                p.error('--assets must contain verified extracted chunk1.psarc and texture.qar')
            env['PT_ASSETS'] = str(args.assets.resolve())
            commands.append([args.build_dir / 'pt_ipad_input_test', args.assets.resolve()])
    elif args.assets:
        p.error('--assets requires native validation')
    for command in commands:
        subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)
    print('Python-only gate passed; native validation remains pending.' if args.python_only else 'Local gate passed. Physical-device acceptance remains separate.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Local validation failed: {error}')
