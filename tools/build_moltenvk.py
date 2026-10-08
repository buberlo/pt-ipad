#!/usr/bin/env python3
"""Build the pinned iOS driver from source with four bounded compilation jobs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from build_provenance import digest

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path, help='independent pinned MoltenVK checkout')
    p.add_argument('--developer-dir', type=Path, default=Path('/Applications/Xcode.app/Contents/Developer'))
    p.add_argument('--jobs', type=int, choices=range(1, 5), default=4)
    p.add_argument('--dependencies-ready', action='store_true', help='explicitly reuse dependencies built in this driver checkout')
    args = p.parse_args()
    root = args.root.resolve()
    pin = json.loads((ROOT / 'source-lock.json').read_text())['moltenvk_target']
    def git(*command):
        return subprocess.check_output(['git', '-C', str(root), *command], text=True).strip()
    if git('rev-parse', 'HEAD') != pin or git('status', '--porcelain'):
        p.error('driver checkout must be clean at the locked source commit')
    if shutil.disk_usage(root).free < 2 * 1024 ** 3:
        p.error('driver build requires at least 2 GiB free; preserve other projects')
    xcode = args.developer_dir.resolve() / 'usr/bin/xcodebuild'
    if not xcode.is_file():
        p.error('full Xcode developer directory is required')
    receipt = root / 'Package/Release/pt-driver-build.json'
    if receipt.exists():
        p.error('driver build receipt already exists; choose a fresh checkout')
    with tempfile.TemporaryDirectory(prefix='pt-xcode-jobs-') as directory:
        wrapper = Path(directory) / 'xcodebuild'
        quoted = shlex.quote(str(xcode))
        wrapper.write_text('#!/bin/sh\nfor arg in "$@"; do\n'
            f'  if [ "$arg" = "-create-xcframework" ]; then exec {quoted} "$@"; fi\n'
            f'done\nexec {quoted} -jobs {args.jobs} "$@"\n')
        wrapper.chmod(0o700)
        env = dict(os.environ, DEVELOPER_DIR=str(args.developer_dir.resolve()), PATH=directory + os.pathsep + os.environ['PATH'])
        if not args.dependencies_ready:
            subprocess.run(['./fetchDependencies', '--ios', '--no-parallel-build'], cwd=root, env=env, check=True)
        subprocess.run(['make', 'ios'], cwd=root, env=env, check=True)
        archive = root / 'Package/Release/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a'
        if git('rev-parse', 'HEAD') != pin or git('status', '--porcelain'):
            p.error('driver source changed during compilation; no receipt published')
        externals = {}
        for path in sorted((root / 'External').iterdir()):
            if (path / '.git').exists():
                externals[path.name] = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        value = {'schema': 1, 'source_commit': pin, 'archive_sha256': digest(archive),
                 'external_revisions': externals, 'jobs': args.jobs,
                 'xcode_version': subprocess.check_output([str(xcode), '-version'], env=env, text=True).strip(),
                 'completed_at': datetime.now(timezone.utc).isoformat(),
                 'dependencies_reused': args.dependencies_ready, 'driver_compiled_here': True}
        # This report stays in the ignored driver directory, never in source control.
        receipt.write_text(json.dumps(value, indent=2) + '\n')
        print(json.dumps(value, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'MoltenVK build failed: {error}')
