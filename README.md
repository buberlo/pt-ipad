# P.T. for iPad

<p align="center"><img src="art/Icon.png" alt="P.T. app icon" width="128"></p>

A native ARM64 iPad source port of P.T., built on the open-source [LoreanXavier/pt-pc](https://github.com/LoreanXavier/pt-pc) C++ port and using separately supplied original game assets.

This project compiles the reconstructed C++ engine and game systems directly for Apple hardware. The runtime also reads original game data and packaged scripts. It does not run the original PlayStation executable or emulate the console CPU. The iPad adaptation adds native application packaging, touch controls, lifecycle handling, verified asset installation and a Vulkan renderer running over Metal through MoltenVK.

**Development status:** build 6 is built, development-signed and installed on an M2 iPad. The original corridor and startup were verified on build 5. Complete physical-device progression, visual fidelity and sustained performance acceptance remain open. This is a working development port, not a finished release. See [the current status](docs/STATUS.md) and [device results](docs/DEVICE_REPORT.md).

## What runs on the iPad

- The `pt-pc` C++ runtime, pinned to **v1.0.1 / `5c6307886f4470d8391bf49445a7c9124ea9d623`**, compiled as native ARM64 code.
- Original models, textures, audio and game scripts loaded from a separately verified P.T. dataset.
- The adapted Vulkan renderer, translated to Metal by **MoltenVK**.
- **SDL3/UIKit** application hosting, touch/gamepad input and Apple lifecycle handling.
- Statically linked **whisper.cpp** for local voice recognition; downloaded voice models stay outside Git.

The initial target is the M2 iPad, landscape presentation, a 1080p internal render target and a **30 FPS goal**. The goal is not yet a sustained-performance result.

## iPad behavior

The app is named **P.T.** and has its own icon. Startup skips the initial settings screen while preserving the intro; settings remain available from pause. Touch controls provide a floating movement stick, a swipe area for looking, a large USE button, ZOOM and pause. The look hint disappears after the first swipe or eight seconds of active gameplay.

[Architecture and source boundaries](docs/ARCHITECTURE.md) explain exactly what comes from the C++ port, what is adapted for iPad, and what still needs verification.

## Source and local builds

```sh
git clone --recurse-submodules https://github.com/buberlo/pt-ipad.git
cd pt-ipad
python3 tools/prepare_source.py
```

The pinned upstream submodule stays clean. Sixteen ordered patches reconstruct the Apple source under the ignored `build/port-src` checkout. Dependency revisions and archive hashes are recorded in `dependency-lock.json`; builds and tests run locally. GitHub Actions are disabled.

See [local build and signing instructions](docs/BUILD.md) for Xcode, native dependencies, host shader compilation, target MoltenVK and development signing. Applications, provisioning profiles, model downloads and build outputs are not distributed in this repository.

## Game data

**No P.T. game package or extracted game content is included.** You must supply the original assets separately from your own legally obtained copy. The dataset verified during development is the US **CUSA01127 v01.00** release. Do not assume that an arbitrary package can be extracted or that another release is compatible.

- [Asset verification](docs/ASSET_STATUS.md)
- [Verified installation and separate saves](docs/ASSET_INSTALLATION.md)
- [Implementation plan](docs/PLAN.md)
- [Gameplay verification](docs/GAMEPLAY_TESTS.md)
- [Device testing](docs/DEVICE_TESTING.md)

## Licenses and attribution

The upstream `pt-pc` source and this project's own adaptations are MIT-licensed; see [LICENSE](LICENSE). Dependency licenses and exact provenance are retained in [THIRD_PARTY.md](THIRD_PARTY.md) and the corresponding notices. That source license does not grant rights to the original game assets.

P.T. and its original content belong to their respective rights holders. This project is not affiliated with Konami or Kojima Productions and redistributes no original game data.
