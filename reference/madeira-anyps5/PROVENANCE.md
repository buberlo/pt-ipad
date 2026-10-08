# Madeira/AnyPS5 reference probes

These four files are an unmodified reference subset, **not an integrated or runnable PT build**. They were exported directly from committed Git objects, not copied from the working tree. No game data, credentials, iPad execution scripts, Wine, FEX, or AnyPS5 implementation is included.

- Source repository: [buberlo/madeira-anyps5](https://github.com/buberlo/madeira-anyps5).
- Source commit: `23b07dc63a7ac90b751550e2bfdccb92c3fe7937`.
- Audited local checkout: a local checkout of buberlo/madeira-anyps5.
- Export date: 2026-10-08.
- License: MIT; each copied source header explicitly states `SPDX-License-Identifier: MIT` and `Copyright (C) 2026 buberlo`.
- The committed [NOTICE](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/NOTICE) explicitly identifies these exact four files as MIT. The committed [LICENSE](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/LICENSE) excludes files with their own SPDX identifiers from its general GPL grant. The root GPL license has **not** been copied as the license for this subset. The adjacent [LICENSE](LICENSE) supplies the standard MIT text here; it is an added license document, not a byte-for-byte upstream file.

## Verified source hashes

SHA-256 covers the complete source bytes. Exported bytes were reread and compared with a second `git show <commit>:<path>` result.

| Source-relative path, preserved here | SHA-256 |
| --- | --- |
| [tools/gpu-probe/gpu_probe.c](tools/gpu-probe/gpu_probe.c) | `2c4a4bbbae924b3ed6280a7cfbd641c8750bdd71bf57fe0a5d314966b481c8b3` |
| [tools/gpu-probe/gpu_probe.h](tools/gpu-probe/gpu_probe.h) | `dcc11b39a0b27e9330842c8b164e63e2067ac336fc8082c0285fcc802d2b6172` |
| [tools/vk-requirements/vk_requirements.c](tools/vk-requirements/vk_requirements.c) | `84729079cbe50e988dfa9cdf092ae1fcdbcfc3be653ea7cde7294adb4f8bc964` |
| [tools/ipad-probe/main.m](tools/ipad-probe/main.m) | `23b43ad1ec3d62975d7979be39f556001f242111fc4d974cc2f1af2203d779e5` |

Original immutable source links:

- [GPU probe C](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/gpu-probe/gpu_probe.c)
- [GPU probe header](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/gpu-probe/gpu_probe.h)
- [Vulkan requirements query](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/vk-requirements/vk_requirements.c)
- [UIKit probe host](https://github.com/buberlo/madeira-anyps5/blob/23b07dc63a7ac90b751550e2bfdccb92c3fe7937/tools/ipad-probe/main.m)

## Required integration work

- The GPU probe depends on Vulkan headers/loader and generated `bda_bytes.spv` and `bc_sample.spv`. Shader sources/binaries and build scripts are deliberately outside this copied subset. The UIKit source expects those resources and a build manifest; it is reference code, not a self-contained Xcode target.
- Retain Vulkan portability enumeration/subset handling and actual GPU readbacks, but derive required features from the pinned PT renderer. These probes currently enforce **AnyPS5** requirements and contain AnyPS5 names. Passing them does not establish PT compatibility.
- For a PT probe, add the actual renderer's texture/depth formats, sample counts, shader and render-pass features. The old BC1 test does not validate every compression format used by PT.
- Build a separate iPhoneOS ARM64 host against pinned MoltenVK; present through a native Metal surface. Do not add the original Wine surface bridge or CPU translation runtime.
- Retain foreground/interruption/build-identity checks. Adapt host lifecycle, bundle resource paths and output locations to the new app. Require a fresh device run under the shared iPad lease before claiming any result for PT.
- This copy performs no device operations. Physical-device tooling and lease management belong to a later integration step.

The source audit and limits of prior device evidence are in [REUSE_AUDIT.md](../../docs/REUSE_AUDIT.md).
