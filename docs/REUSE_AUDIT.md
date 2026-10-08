# Reuse audit

Inspected on 2026-10-08. The chosen runtime is the native C++ source port, not the PS5 executable-conversion stack. The generated PT build tree applies the patches to `pt-pc` v1.0.1, commit `5c6307886f4470d8391bf49445a7c9124ea9d623`; [source lock](../source-lock.json) records the pins.

## Sources and boundaries

| Source | Exact inspected pin / local path | Decision |
| --- | --- | --- |
| Madeira/AnyPS5 | `23b07dc63a7ac90b751550e2bfdccb92c3fe7937`; `a local checkout of buberlo/madeira-anyps5` (origin renamed to `buberlo/madeira-anyps5`) | Reuse the four expressly MIT native GPU probe files and verified integration lessons. Active changes in the original checkout were not copied. |
| Penta | `d095299cc86baafce3bd22dab1f658b3920daa53`; `a local checkout of buberlo/penta` | Reference importer, separate saves and displayed-frame measurement designs. Its GPL-3.0-or-later Swift/Wine implementation is not included. |
| MoltenVK target | `fae55a18779ee59da2cc5373a367a0282779c171`; source checkout `a local MoltenVK checkout (upstreams/MoltenVK)` | Apache-2.0 native Vulkan-to-Metal runtime. Actual builds record which archive they used; a host Homebrew test is not proof for the pinned iPad archive. |
| Older Madeira workspace | `a local checkout of the older Madeira workspace` (root had no committed HEAD) | Shared iPad lease coordination remains relevant; do not treat the workspace as a reproducible source revision. |

## Reuse versus replacement

| Area | Source evidence | PT treatment |
| --- | --- | --- |
| GPU feature/readback probes | [GPU C/header](https://github.com/buberlo/madeira-anyps5/tree/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/gpu-probe), [UIKit host](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/ipad-probe/main.m), [requirements query](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/vk-requirements/vk_requirements.c) | Four files copied byte-identically into [reference/madeira-anyps5](../reference/madeira-anyps5/PROVENANCE.md), with hashes and MIT attribution. Reference only: their missing shader/build resources mean this subset is not an integrated app. Requirements for PT are queried independently. |
| Safe asset installation | [PentaImport.swift](https://github.com/buberlo/penta/blob/d095299cc86baafce3bd22dab1f658b3920daa53/app/PentaImport.swift) | Reuse the approach: immutable originals, streaming hashes, safe paths, staged publication, separate saves and explicit preparation state. Replace PS5 ELF/NID relinking and Windows job transport with PT archive import. |
| Touch and controllers | [Madeira TouchGamepad.swift](https://github.com/willfaust/Madeira/blob/48f976429c189f8396e23d251d8a82f43c705922/app/Madeira/TouchGamepad.swift) | New native controls feed game actions directly. The original fixed 18-control Wine/XInput path is unnecessary. No GPL controller code was copied. |
| GPU lifecycle and measurement | [Penta display timing](https://github.com/buberlo/penta/blob/d095299cc86baafce3bd22dab1f658b3920daa53/docs/DISPLAY_TIMING.md), [Madeira lifecycle patch](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/patches/madeira/0028-menu-vulkan-lifecycle.patch) | Pause rendering/audio/input around iOS inactivity, drain GPU work, reset timing after resume. Use actual presentation timestamps when available; no submitted-frame count is called display FPS. Reimplement directly at the native Vulkan boundary. |
| CPU execution, console HLE | [Madeira/AnyPS5 architecture](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/docs/ARCHITECTURE.md) | Exclude Wine, FEX, JIT helpers, pairing/VPN, PE modules, AnyPS5 relinker/HLE, guest arenas and x86 exception machinery. The existing relinker targets x86-64, not ARM64; PS5 AGC/RDNA work is not a ready PS4 GNM/GCN implementation. Native PT source removes that prerequisite. |

AnyPS5 is GPL-2.0-only, Madeira is GPL-3.0-or-later, and MoltenVK is Apache-2.0. The old project kept AnyPS5 in separate Windows modules; this audit does not authorize merging incompatible source into one native application. The copied probes have their own explicit MIT grants, confirmed by the pinned [NOTICE](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/NOTICE).

## Evidence limits and concrete renderer work

The old [native M2 qualification](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/docs/evidence/ipad-m2-native-gpu-qualification.json) records only native offscreen GPU success. Its [sample-count queries](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/docs/evidence/solitaire-ipad-msaa-capabilities.json) support 1/2/4 samples, reject 8 samples and D16/S8, and do not prove a multisample draw. Neither result proves PT gameplay.

[Renderer patch 0002](../patches/0002-metal-renderer.patch) enables portability only when advertised, queries required features, validates image formats/extents/sample support, and replaces 8,192 duplicated combined samplers with bounded sampled-image arrays and two shared samplers. It checks both per-stage and per-set limits and fails explicitly if content exceeds capacity. A device lacking update-unused-while-pending uses synchronized descriptor publication; the material-buffer descriptor no longer unnecessarily requires update-after-bind. The shader operations and original texture data are preserved.

On the development Mac (Apple M3 Pro, host MoltenVK reporting Vulkan 1.3.357), the real layout query reports `maxPerSetDescriptors=1212`, yielding 1,144 2D slots and 64 cube slots. A native compute test sampled the highest 2D slot, 1,143, and read back the expected 2x2 red texture. Seven descriptor-budget boundary cases passed; all 65 shader modules, including the descriptor probe, compiled and passed SPIR-V validation. These checks establish host resource/shader contracts, not scene completeness, an iPad run, or a frame-rate result. The actual peak PT texture count and complete gameplay remain acceptance work.

All builds/tests are local. No GitHub Actions or physical-device operations were performed for this audit. Follow [STATUS.md](STATUS.md) for subsequent build, asset, signing and device evidence.
