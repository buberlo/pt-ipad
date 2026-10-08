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
