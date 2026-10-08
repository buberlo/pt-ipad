#!/usr/bin/env python3
"""Configure and build the complete native engine locally, without signing or installing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from prepare_source import source_state
from build_provenance import (MANIFEST_NAME, bundle_resources_hash, canonical_hash,
                              digest, tree_hash, verify_dependency)

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ('sdl3', 'zlib', 'whisper', 'volk', 'vma', 'glm', 'imgui', 'stb',
                'lua51', 'bc7enc', 'harfbuzz', 'ogg', 'vorbis')
HOST_TESTS = ('pt_tests', 'pt_voice_match_test', 'pt_graphics_preset_test',
              'pt_blur_sway_test', 'pt_descriptor_budget_test', 'pt_settings_roundtrip_test',
              'pt_save_status_test', 'pt_save_reset_test', 'pt_mods_test', 'pt_ipad_input_test',
              'pt_asset_install_test', 'pt_script_api_test')


def capture(args, *, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def run(args, *, env):
    print('+ ' + ' '.join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], env=env, check=True)


def target_inputs(build):
    target = dict(line.split('=', 1) for line in (build / 'apple-build-inputs.txt').read_text().splitlines())
    headers = Path(target['vulkan_headers'])
    # A Homebrew include root contains unrelated symlinked packages; hash the actual
    # Vulkan/MoltenVK header trees, not the whole global include directory.
    header_trees = {name: tree_hash((headers / name).resolve(), internal_symlinks=True)
                    for name in ('vulkan', 'vk_video', 'MoltenVK') if (headers / name).is_dir()}
    if 'vulkan' not in header_trees:
        raise ValueError('target Vulkan headers disappeared after configuration')
    return {'sdk': target['sdk'], 'minimum_os': target['minimum_os'],
            'moltenvk_archive_sha256': digest(Path(target['moltenvk_library'])),
            'vulkan_headers_sha256': canonical_hash(header_trees)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('macos', 'ios'))
    parser.add_argument('--source', type=Path, default=ROOT / 'build/port-src')
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--prepare-source', action='store_true',
                        help='use prepare_source.py, which preserves any changed or unmarked checkout')
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--tests', action='store_true', help='run the asset-free host suite and a GPU descriptor readback')
    parser.add_argument('--configure-only', action='store_true')
    parser.add_argument('--developer-dir', type=Path, default=Path('/Applications/Xcode.app/Contents/Developer'))
    parser.add_argument('--minimum-os', help='default macOS 14.0 or iOS 18.0')
    parser.add_argument('--build-number', type=int, default=4)
    parser.add_argument('--host-glslc', type=Path)
    parser.add_argument('--voice-dir', type=Path)
    parser.add_argument('--moltenvk-root', type=Path,
                        default=ROOT.parent / 'anyps5-ipad/upstreams/MoltenVK')
    parser.add_argument('--moltenvk-library', type=Path)
    parser.add_argument('--moltenvk-include', type=Path)
    args = parser.parse_args(argv)
    if args.build_number < 1:
        parser.error('--build-number must be positive')
    if args.tests and args.platform != 'macos':
        parser.error('--tests runs host binaries and is only valid for macos')
    env = os.environ.copy()
    env['DEVELOPER_DIR'] = str(args.developer_dir.resolve())
    if not args.developer_dir.is_dir():
        parser.error('the selected full Xcode Developer directory is missing')
    for program in ('cmake', 'ninja'):
        if not shutil.which(program):
            parser.error(f'{program} is missing from PATH')
    glslc = args.host_glslc or Path(shutil.which('glslc') or '')
    if not glslc.is_file():
        parser.error('a host glslc executable is required; pass --host-glslc')
    if args.prepare_source:
        run([sys.executable, ROOT / 'tools/prepare_source.py', '--output', args.source], env=env)
    if not (args.source / 'cmake/Apple.cmake').is_file():
        parser.error('patched source is missing; use --prepare-source or select an existing patched --source')
    lock = json.loads((ROOT / 'source-lock.json').read_text())
    dependency_lock_path = ROOT / 'dependency-lock.json'
    dependency_lock = json.loads(dependency_lock_path.read_text())
    if (dependency_lock.get('schema') != 1 or dependency_lock.get('upstream_commit') != lock['pt_pc']['commit']
            or set(dependency_lock.get('dependencies', {})) != set(DEPENDENCIES)):
        parser.error('dependency lock does not match the supported source and dependency set')
    if capture(['git', 'rev-parse', 'HEAD'], cwd=args.source) != lock['pt_pc']['commit']:
        parser.error('source HEAD differs from the pinned upstream; local edits are preserved, build refused')
    build = (args.build_dir or ROOT / f'build/{args.platform}-arm64').resolve()
    build.mkdir(parents=True, exist_ok=True)
    # Do not run a multi-hundred-MB configure/build with the startup disk nearly full.
    if shutil.disk_usage(build).free < 512 * 1024 * 1024:
        parser.error('less than 512 MiB free at the build destination; recover space before building')
    cache_sources = ROOT / 'build/deps'
    deps = cache_sources if args.platform == 'macos' else ROOT / 'build/deps-ios'
    existing_voice = ROOT / 'build/macos-arm64/voice'
    voice = args.voice_dir or (existing_voice if (existing_voice / 'ggml-base.en-q5_1.bin').is_file()
                              else ROOT / 'build/shared/voice')
    minimum = args.minimum_os or ('18.0' if args.platform == 'ios' else '14.0')
    cmake = ['cmake', '-S', args.source.resolve(), '-B', build, '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_OSX_ARCHITECTURES=arm64',
             f'-DCMAKE_OSX_DEPLOYMENT_TARGET={minimum}', f'-DFETCHCONTENT_BASE_DIR={deps}',
             f'-DPT_APP_BUILD={args.build_number}',
             f'-DPT_HOST_GLSLC={glslc.resolve()}', f'-DPT_VOICE_DIR={voice.resolve()}']
    for option in ('UPSCALERS', 'STREAMLINE', 'OPENXR', 'ENHANCED_TEXTURES', 'GAMEPLUS', 'NETWORK_UPDATES'):
        cmake.append(f'-DPT_{option}=OFF')
    manifest = {'schema': 1, 'status': 'preparing', 'platform': args.platform, 'source_commit': lock['pt_pc']['commit'],
                'application_build': args.build_number,
                'source_tree_sha256': source_state(args.source),
                'developer_dir': str(args.developer_dir), 'minimum_os': minimum,
                'host_glslc': str(glslc.resolve()), 'jobs': args.jobs,
                'dependency_lock_sha256': digest(dependency_lock_path),
                'host_tools_pinned': False, 'bit_reproducible': False}
    observed = {}
    for name, command in (('cmake', ['cmake', '--version']), ('ninja', ['ninja', '--version']),
                          ('glslc', [str(glslc), '--version']),
                          ('xcode', ['xcodebuild', '-version']),
                          ('clang', ['xcrun', '--sdk', 'iphoneos' if args.platform == 'ios' else 'macosx', 'clang', '--version'])):
        if name == 'clang':
            program = Path(capture(command[:-1] + ['--print-prog-name=clang'], env=env)).resolve()
        elif name == 'xcode':
            program = args.developer_dir / 'usr/bin/xcodebuild'
        else:
            program = Path(shutil.which(command[0]) or command[0]).resolve()
        observed[name] = {'path': str(program), 'sha256': digest(program),
                          'version': capture(command, env=env)}
    manifest['host_tools_observed'] = observed
    dependency_paths = {}
    for name in DEPENDENCIES:
        cached = cache_sources / f'{name}-src'
        source = cached if args.platform == 'macos' or cached.exists() else deps / f'{name}-src'
        dependency_paths[name] = source
        if source.exists() or source.is_symlink():
            verify_dependency(source, dependency_lock['dependencies'][name])
            override = str(source.resolve())
        else:
            override = ''  # Clear any unrelated override retained by an old CMake cache.
        cmake.append(f'-DFETCHCONTENT_SOURCE_DIR_{name.upper()}={override}')
    if args.platform == 'ios':
        root = args.moltenvk_root.resolve()
        commit = capture(['git', 'rev-parse', 'HEAD'], cwd=root)
        if commit != lock['moltenvk_target']:
            parser.error('iOS MoltenVK source HEAD differs from source-lock.json')
        if capture(['git', 'status', '--porcelain'], cwd=root):
            parser.error('iOS MoltenVK source has local modifications; build refused without changing it')
        library = args.moltenvk_library or root / 'Package/Release/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a'
        headers = args.moltenvk_include or root / 'Package/Release/MoltenVK/include'
        if not library.is_file() or not (headers / 'vulkan/vulkan.h').is_file():
            parser.error('the pinned iOS MoltenVK archive or headers are missing; build that dependency locally first')
        cmake += ['-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_SYSROOT=iphoneos',
                  f'-DPT_MOLTENVK_LIBRARY={library.resolve()}', f'-DPT_MOLTENVK_INCLUDE_DIR={headers.resolve()}',
                  f'-DPT_MOLTENVK_LICENSE={root / "LICENSE"}']
        manifest['moltenvk_source_commit'] = commit
        manifest['moltenvk_library'] = str(library.resolve())
        manifest['moltenvk_archive_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
        # This records the inspected source and artifact separately. It does not claim the
        # pre-existing archive was rebuilt from that checkout during this invocation.
        manifest['moltenvk_rebuilt_here'] = False
    else:
        if args.moltenvk_library:
            cmake.append(f'-DPT_MOLTENVK_LIBRARY={args.moltenvk_library.resolve()}')
        if args.moltenvk_include:
            cmake.append(f'-DPT_MOLTENVK_INCLUDE_DIR={args.moltenvk_include.resolve()}')
    (build / 'build-wrapper-inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    run(cmake, env=env)
    manifest['target_inputs_observed'] = target_inputs(build)
    manifest['dependency_inputs'] = {name: verify_dependency(path, dependency_lock['dependencies'][name])
                                     for name, path in dependency_paths.items()}
    manifest['dependency_inputs_sha256'] = canonical_hash(manifest['dependency_inputs'])
    manifest['voice_models'] = {}
    for name, expected in dependency_lock['voice_models'].items():
        actual = digest(voice / name)
        if actual != expected:
            parser.error(f'voice model differs from dependency lock: {name}')
        manifest['voice_models'][name] = actual
    manifest['status'] = 'configured'
    (build / 'build-wrapper-inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if args.configure_only:
        return 0
    targets = ['pt']
    if args.tests:
        targets += list(HOST_TESTS) + ['pt_metal_capabilities_test', 'pt_texture_descriptor_shader']
    run(['cmake', '--build', build, '--target', *targets, f'-j{args.jobs}'], env=env)
    if args.tests:
        run(['ctest', '--test-dir', build, '--output-on-failure', '-L', 'asset-free'], env=env)
        touch_test = build / 'pt_touch_controls_test'
        run(['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-O2', '-UNDEBUG',
             '-I', args.source.resolve() / 'src', ROOT / 'tests/touch_controls_test.cpp', '-o', touch_test], env=env)
        run([touch_test], env=env)
        run([build / 'pt_metal_capabilities_test', build / 'tests/texture_descriptor.comp.spv'], env=env)
    app = build / 'pt.app'
    # Source and dependency mutation during compilation invalidates this build's receipt.
    if source_state(args.source) != manifest['source_tree_sha256']:
        parser.error('source changed during this build; no completed provenance was published')
    for name, path in dependency_paths.items():
        verify_dependency(path, dependency_lock['dependencies'][name])
    if target_inputs(build) != manifest['target_inputs_observed']:
        parser.error('target library or headers changed during compilation; no completed provenance was published')
    resources = app if args.platform == 'ios' else app / 'Contents/Resources'
    info_path = app / ('Info.plist' if args.platform == 'ios' else 'Contents/Info.plist')
    info = plistlib.loads(info_path.read_bytes())
    relative_executable = info['CFBundleExecutable'] if args.platform == 'ios' else f"Contents/MacOS/{info['CFBundleExecutable']}"
    manifest['unsigned_executable_sha256'] = digest(app / relative_executable)
    manifest['runtime_links_observed'] = capture(['otool', '-L', str(app / relative_executable)], env=env).splitlines()[1:]
    for name, expected in manifest['voice_models'].items():
        if digest(resources / 'voice' / name) != expected:
            parser.error(f'bundled voice model differs from validated input: {name}')
    manifest['bundle_resources_sha256'] = bundle_resources_hash(app, relative_executable)
    manifest['status'] = 'built'
    payload = json.dumps(manifest, indent=2) + '\n'
    (app / MANIFEST_NAME).write_text(payload)
    (build / 'build-wrapper-inputs.json').write_text(payload)
    print(f'Built {app}. Signing, installation and device acceptance are separate steps.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Native build failed: {error}')
