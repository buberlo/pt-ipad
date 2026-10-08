# Third party sources

| Source | Revision | Treatment |
| --- | --- | --- |
| LoreanXavier/pt-pc | `5c6307886f4470d8391bf49445a7c9124ea9d623` (v1.0.1) | Pinned submodule. Its own code declares MIT; dependencies retain separate terms. |
| buberlo/madeira-anyps5 | `23b07dc63a7ac90b751550e2bfdccb92c3fe7937` | Four explicitly MIT diagnostic files copied under reference/, with their provenance and MIT text. |
| KhronosGroup/MoltenVK | Target pin `fae55a18779ee59da2cc5373a367a0282779c171` | Apache-2.0; target library revision and hash must be recorded for device builds. |

The upstream submodule also contains fonts, sample mod media, documentation media and an enhancement model. It is a pointer to an independently licensed upstream repository, not a claim that every upstream file is source code. These items must be reviewed before inclusion in an application. Only required fonts and notices are included by the Apple resource build; sample mods, documentation media and the enhancement model are not application resources.

The package extraction helper is a separate host process using LibOrbisPkg under its own LGPL terms. It is not linked into the iPad runtime. Preserve corresponding source, licenses and the upstream helper patches when distributing that helper.

whisper.cpp, its voice models, SDL3, Vulkan dependencies, fonts and all other linked libraries retain their notices. Apple packages must carry those notices. The root MIT license covers new original code in this repository; it does not relicense upstream code, copied code, game assets or dependencies.

Madeira/Penta application code and AnyPS5 implementation code have not been copied into this native application. Their import, lifecycle and measurement designs inform independently implemented host adapters.

## Verified Apple resource notices

The signed build 3 bundle and its IPA were inspected on 2026-10-08. These notice files match the resources in that delivered artifact; paths below are relative to `pt.app`. Build 3's signature, receipt executable hash and IPA hash were verified. `otool -L` lists Apple system libraries/frameworks only; SDL, Lua, Whisper/ggml, HarfBuzz, Vorbis and MoltenVK are statically linked. The host extraction helper and Homebrew build tools are not application runtime dependencies.

| Included component | Notice in the Apple bundle | Terms represented |
| --- | --- | --- |
| pt-pc original port code | `licenses/pt-pc-MIT.txt` | MIT, LoreanXavier |
| SDL 3.4.16; zlib 1.3.2 | `licenses/sdl3-LICENSE.txt`; `licenses/zlib-LICENSE` | zlib |
| Whisper 1.9.4 and bundled ggml | `licenses/whisper-LICENSE`; `voice/licenses/whisper.cpp-MIT.txt` | MIT, ggml authors; this release has no separate `ggml/LICENSE` |
| Volk 1.4.350; VMA 3.4.0; Dear ImGui 1.92.9b docking | `licenses/volk-LICENSE.md`; `licenses/vma-LICENSE.txt`; `licenses/imgui-LICENSE.txt` | MIT |
| GLM 1.0.3 | `licenses/glm-copying.txt` | MIT or Happy Bunny license |
| stb and bc7enc | `licenses/stb-LICENSE`; `licenses/bc7enc-LICENSE` | Their MIT/public-domain alternatives; the app compiles `bc7enc.cpp` |
| Lua 5.1.5 | `licenses/lua51-COPYRIGHT` | MIT |
| HarfBuzz 14.6.0 core | `licenses/harfbuzz-COPYING` | Old MIT; the separate Microsoft data notice is addressed below |
| Ogg 1.3.5; Vorbis 1.3.7 | `licenses/ogg-COPYING`; `licenses/vorbis-COPYING` | BSD |
| ww2ogg codebooks at `14ed9b0dd62e815a38702b5f03c57006cbe2501b` | `licenses/ww2ogg-COPYING` | BSD; codebook bytes and notice have pinned SHA256 values |
| MoltenVK | `licenses/MoltenVK-LICENSE` | Apache-2.0 |
| MoltenVK's SPIRV-Cross, SPIRV-Tools, Vulkan-Headers, Volk and cereal | `licenses/MoltenVK-*-LICENSE*` | Component notices copied from the selected target source tree, including nested cereal/RapidJSON/msinttypes and SPIR-V Headers notices |
| Noto Sans, Noto Sans SC, Noto Naskh Arabic, Noto Kufi Arabic | `licenses/OFL-*.txt` and `fonts/OFL-*.txt` | SIL Open Font License |
| Whisper base.en model; Silero VAD model | `voice/licenses/OpenAI-Whisper-MIT.txt`; `voice/licenses/Silero-VAD-MIT.txt` | MIT |

Build 3 omitted the root project's buberlo MIT notice and HarfBuzz's Microsoft MIT notice for `src/ms-use` data used by the compiled Universal Shaping Engine table. Patch `0011-dependency-provenance.patch` adds `licenses/PT-iPad-MIT.txt` and `licenses/harfbuzz-ms-use-MIT.txt` for the next build. The first is sourced from a patch-tracked `third_party/apple_notices/PT-iPad-MIT.txt`, identical to this repository's root `LICENSE`, so a fresh generated checkout carries it. Existing signed build 3 artifacts are unchanged.

The delivered voice model hashes match the expected hashes in `cmake/Dependencies.cmake` and `dependency-lock.json`:

| File | SHA256 |
| --- | --- |
| `voice/ggml-base.en-q5_1.bin` | `4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f` |
| `voice/ggml-silero-v6.2.0.bin` | `2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987` |

## Dependency and tool provenance

`dependency-lock.json` records the ten resolved Git commits and three archive hashes/content trees verified against the build 3 dependency sources. The extracted Whisper, Lua and bc7enc trees also match their cached original archives. Patch 0011 replaces dependency tag selectors with those exact commits and adds the missing bc7enc archive digest. The wrapper validates reused sources before configuration and again before publishing a completed build manifest; it checks newly fetched sources after configuration and before compilation. Unexpected content, dirty Git sources and mismatched commits fail without altering the source cache. Wwise codebook cache bytes are checked before generating the compiled data.

The next completed wrapper build embeds `pt-build-manifest.json` with source/dependency hashes, models, target library/header hashes, observed tool versions and executable/resource hashes. Signing requires the input bytes to match that completed manifest, preserves it in the signed app, and binds its hash plus source/dependency hashes into the signing receipt. This records build inputs and artifact identity; it is not an independently witnessed compiler attestation.

Homebrew CMake 4.4.4, Ninja 1.13.2 and shaderc 2026.4, plus Xcode 27.0 build 27A266a/Apple clang 21.0.0, were observed on the build 3 host. Their versions are not pinned by the installation command. Homebrew Vulkan-Headers 1.4.363.0 and MoltenVK 1.4.2 supplied the Mac reference build; iOS uses the separate source-pinned MoltenVK target archive and its packaged headers. The iOS archive digest is recorded, but that archive was not rebuilt in this task. Host-tool pinning, a fresh target-library rebuild and bit-identical reproducibility remain unverified; manifests label the host tools as observed and `bit_reproducible` as false.
