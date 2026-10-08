# Local native builds

The complete C++ engine builds as native ARM64 macOS and iOS applications. GitHub Actions are disabled. Game archives remain separate from source and application bundles.

## Prerequisites

Use full Xcode and a host `glslc`, CMake and Ninja. Set `DEVELOPER_DIR` per command; the wrapper does this without changing the global Xcode selection. The verified host uses Xcode 27.0, iPhoneOS SDK 27.0, CMake, Ninja, Homebrew shaderc 2026.4, Vulkan headers 1.4.363.0 and macOS MoltenVK 1.4.2. The build defaults to four jobs and refuses to start below 512 MiB of free space. Allow several GiB for dependency sources, both platform builds, archives and signing copies.

```sh
brew install cmake ninja shaderc molten-vk vulkan-headers
```

For iOS, provide a locally built ARM64 MoltenVK archive. The default is the existing sibling `anyps5-ipad/upstreams/MoltenVK` checkout. Its source commit must match `source-lock.json`. The wrapper records the actual archive path and SHA-256 independently of that source checkout; it does not claim to have rebuilt a pre-existing archive.

The inspected iOS source commit is `fae55a18779ee59da2cc5373a367a0282779c171`. The reused archive at `Package/Release/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a` has SHA-256 `5b04b88bd96ea1905e6217b9424bc5fc4c78dd58607428b45cd6fa916464384d`.

## Source preparation

```sh
git submodule update --init upstream/pt-pc
python3 tools/prepare_source.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Preparation verifies the upstream commit and patch order, writes ignored `build/port-src`, and refuses to overwrite an altered or unmarked checkout. Reusing an exactly matching generated checkout is safe. To rebuild a changed patch recipe, choose a fresh source directory instead of deleting active work.

## Build and verify

These are the validated wrapper commands:

```sh
python3 tools/build_native.py macos --tests
python3 tools/build_native.py ios
```

`--prepare-source` explicitly requests safe source preparation before configuring. `--source`, `--build-dir`, `--developer-dir`, `--host-glslc`, `--voice-dir`, `--moltenvk-root`, `--moltenvk-library` and `--moltenvk-include` select local inputs. `--configure-only` stops before compilation. Use one build at a time with the shared dependency cache.

The wrapper generates Ninja Release builds for ARM64, with deployment targets macOS 14.0 or iOS 18.0. Host `glslc` compiles Vulkan 1.3 SPIR-V. iOS links its own MoltenVK archive and headers; desktop libraries are never used as the iOS driver. Source dependencies and voice models are reused while macOS and iOS have separate dependency binary directories. Desktop upscalers, Streamline, OpenXR, the external enhanced-texture executable, Game+ and update checks are disabled.

Whisper is statically linked for ARM64. Lua retains its standard library but `os.execute` reports an error on iOS because child processes are unavailable. The iOS bridge exposes actual UIApplication foreground state for the main loop and rendering startup. Runtime resources include shaders, fonts, offline voice models and dependency notices; they contain no P.T. game archives.

Outputs:

- `build/macos-arm64/pt.app`
- `build/ios-arm64/pt.app`
- Each build's `apple-build-inputs.txt` and `build-wrapper-inputs.json` identify its target and input artifacts.

The iOS Mach-O was verified as platform `IOS`, architecture `arm64`, minimum OS `18.0`, SDK `27.0`. Its identifier is `com.konradkern.pt.native`; it declares microphone access, landscape iPad support and Documents file sharing.

The host suite passed all twelve asset-free CTest targets, including native asset installation, script compatibility, and touch actions mapped into the real input and options-menu code. A separate touch-state test passed concurrent movement, camera motion, taps, held zoom and lifecycle reset. The native Metal capability probe created the split image/sampler descriptor layout and passed a 2×2 GPU readback through its highest legal texture index. This validates the tested host driver contract; physical iPad gameplay has separate acceptance checks.

## Signing

Signing is explicit and separate from building. Use a local development provisioning profile and matching signing identity; keep both outside Git:

```sh
python3 tools/sign_ios.py \
  --app build/ios-arm64/pt.app \
  --profile /absolute/private/path/development.mobileprovision \
  --identity 'Apple Development: local identity' \
  --output artifacts/PT-build6.ipa
```

The signer preserves its input bundle. It signs a private copy, verifies its entitlements and certificate against the profile, then publishes the IPA, JSON receipt and signed `artifacts/PT-build6/pt.app`. Existing outputs are refused. Install that signed copy. Re-sign after every executable, metadata or resource change; use `--build-number` with the build wrapper to identify a new app build. Building or signing does not prove installation, foreground launch or playable device behavior. [Device testing](DEVICE_TESTING.md) requires shared-device ownership and separate acceptance evidence.

## Private data

Keep the source package in its original location. The host importer installs into ignored `assets-private/CUSA01127` and records private input paths in ignored reports. Device game data goes in the application's Documents/CUSA01127 directory; saves remain separate. Never add the game data to a Git commit or release.
