# P.T. Native for iPad

Native ARM64 iPad port of the C++ [P.T. PC runtime](https://github.com/LoreanXavier/pt-pc), using user-supplied original game assets. The target is the complete teaser on the M2 iPad at 30 FPS, with the original presentation, touch/controller input and local microphone recognition. No Wine, FEX, VPN or CPU JIT is part of this architecture.

**Implementation is in progress. No physical-iPad gameplay or performance acceptance has been established.** See [STATUS.md](docs/STATUS.md) for tested milestones and unresolved gates. Source compilation, signing, installation, rendering and completed gameplay are separate milestones.

## Build and assets

- [Build instructions](docs/BUILD.md)
- [Approved implementation plan](docs/PLAN.md)
- [Asset status](docs/ASSET_STATUS.md)
- [Reused diagnostic provenance](reference/madeira-anyps5/PROVENANCE.md)
- [Licenses and dependency boundaries](THIRD_PARTY.md)

The upstream submodule is immutable. Local Apple changes live in `patches/series` and are applied to an ignored generated checkout by `python3 tools/prepare_source.py`. Build products, game assets and private recordings stay outside Git. This repository has GitHub Actions disabled; validation runs locally.

P.T. and its original content belong to their respective rights holders. This repository distributes no user-supplied game assets and is not affiliated with Konami or Kojima Productions.
