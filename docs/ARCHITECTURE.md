# What this project is

P.T. for iPad is a native C++ source port based on [LoreanXavier/pt-pc](https://github.com/LoreanXavier/pt-pc), pinned to v1.0.1 at `5c6307886f4470d8391bf49445a7c9124ea9d623`.

The distinction matters: `pt-pc` reconstructs the engine and game systems in C++. This project builds that source for ARM64 and adapts it to Apple's application and graphics environment. Original packaged scripts and data are read by the port. The original console executable is not loaded or translated, and no original-executable recompilation is claimed.

## Runtime boundaries

| Part | Source and role |
| --- | --- |
| Engine, game systems and asset readers | Pinned `pt-pc` C++ source; upstream behavior and defects must be assessed |
| Original game content | Separately supplied P.T. archives: models, textures, audio, scripts and other data; absent from Git and the signed app bundle |
| Rendering | Upstream Vulkan pipeline adapted to supported Apple capabilities, with MoltenVK translating Vulkan to Metal |
| Apple application host | Native ARM64 app packaging, SDL3/UIKit window and lifecycle, application resource/save/cache paths |
| Input | Shared game actions for touch and controllers; touch menu hit testing and movement/look/action overlays |
| Voice recognition | Static ARM64 whisper.cpp; local microphone handling and separately verified model files |
| Asset installation | Manifest validation, staged installation, atomic activation and rollback, with saves stored separately |

A source port can retain original assets and scripts while differing from the original game's behavior. Faithfulness therefore requires matched scene comparisons and complete progression tests; the upstream author's completion claims are not treated as acceptance evidence.

## How the build is assembled

1. `upstream/pt-pc` identifies the immutable public upstream commit.
2. `tools/prepare_source.py` checks that baseline and applies `patches/series` in order to a generated checkout.
3. `tools/build_native.py` verifies dependency inputs and builds ARM64 macOS or iPhoneOS targets. Shader compilation runs on the host Mac; the resulting shaders are packaged as application resources.
4. Desktop extras and network update downloads are disabled in the initial Apple build. MoltenVK and whisper are linked for the target rather than loaded from desktop libraries.
5. The application records source, dependency, tool and bundle fingerprints in its build manifest. `tools/sign_ios.py` checks that manifest, signs a separate copy and publishes an ignored local IPA and signing receipt.
6. Original game data is installed separately and checked before gameplay. Updating the app does not require replacing its data container or saves.

The patch inputs are reproducible: a fresh reconstruction matches the edited source tree. The host tools are observed rather than fully pinned, and bit-identical executable reproducibility is not claimed.

## Current evidence

Build 6 is compiled, signed and installed on the development M2 iPad. Its running process was observed. Build 5's fresh startup skipped options, preserved the intro and reached the authentic corridor. Native host tests cover touch/menu mapping, installation and source compatibility. Earlier desktop automated routes reached the ending; an earlier physical-device scripted run reached the final-puzzle loop but did not complete the ending.

Full physical touch/controller validation, live microphone interaction, original-game visual parity, uninterrupted ending progression, disconnected/offline launch and the sustained 30 FPS performance target remain separate acceptance gates. Detailed identities and limitations are in [STATUS.md](STATUS.md) and [DEVICE_REPORT.md](DEVICE_REPORT.md).

## What the public repository contains

The repository contains source, patches, build/test tooling, original app artwork, dependency locks and documentation. It contains no game package, extracted proprietary data, downloaded voice model, credential, provisioning profile, signed application or private recording. Making the source public does not publish a playable asset bundle or grant rights to the original game.
