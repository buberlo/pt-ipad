# P.T. asset intake

Status checked 2026-10-08: all three required assets were extracted successfully
to ignored `assets-private/CUSA01127`, and every full-file SHA-256 matches the
upstream tested US data set. The source package's SHA-256 is identical before and
after extraction. Runtime and device acceptance remain open.

## Package evidence

The user-provided package remains in its original local location. Its path and
full inspection report are kept only in ignored `reports-private/`.

| Field | Observed value |
| --- | --- |
| Container | PS4 PKG, `7f434e54` |
| Bytes | 1,478,164,480 |
| SHA-256 | `5aa60a4d8cbaa6a1b765d1d6a6347a4a7c433e912db7535da2fb667f8ea76cb5` |
| SFO title / title ID | P.T. / CUSA01127 |
| Content ID | `UP4511-CUSA01127_00-PPPPPPPPTTTTTTTT` |
| App / package version | 01.00 / 01.00 |
| Metadata records | 20 |
| SFO | readable, 2,708 bytes at offset `0x19a10` |
| PFS image | 1,435,172,864 bytes at offset `0x02900000` |
| PFS mode | `0x000d`, encrypted bit set |

The readable header/SFO does not prove the game payload can be read. The embedded
package creation metadata includes `c_date=20220306`; the package hash identifies
this local container, not an independently authenticated original retail package.

## Extractor

`tools/bootstrap_asset_helper.py --install-sdk` was run successfully. It built and
smoke-tested the separate upstream helper with:

- Microsoft .NET SDK 10.0.401 for macOS ARM64, verified against Microsoft's
  published SHA-512 before unpacking.
- [LibOrbisPkg commit 6434772](https://github.com/maxton/LibOrbisPkg/tree/643477263b2644e0803e0f58b8726ea4e3f3b7d4).
- The pinned `upstream/pt-pc/installer/Extractor` wrapper and its
  `tools/patch_liborbis_readers.py` fixes, applied to a private source copy.

The self-contained helper is under `.local/asset-helper/published/`; corresponding
patched LGPL source, wrapper source and `provenance.json` remain beside it.
The newly downloaded SDK and generated build/NuGet caches were removed after
successful publication and startup verification. No global .NET installation or
upstream source modification was made.

The helper supports the upstream fPKG/dump route and successfully opened this
package using that supported route. It does not use console-unique retail keys.
Successful extraction and exact archive hashes are separate from the earlier
helper startup check.

## Import gate

`tools/import_pt_assets.py` extracts into a fresh staging directory, accepts only
the three fixed asset names, verifies their full SHA-256 values against the
upstream tested US set, and validates bounded PSARC/QAR/path-list metadata. It
hashes the source package before and after extraction. Only the complete validated
directory is published as `assets-private/CUSA01127` by rename.

| Required file | Bytes | Verified SHA-256 (matches upstream US reference) |
| --- | ---: | --- |
| chunk1.psarc | 421,978,112 | `f3cf67ef215065df01619fb0b3fd03fba7f465752ac4107e485dd0ea9dda41ef` |
| texture.qar | 892,291,044 | `436bb79d9d47df685423a9afaed89a8be5e88a938347dd18e63e94398c6ed9b0` |
| pathid_list_ps4.bin | 93,248 | `6b4641bafe18f785229500454c5d44cba04cc1302fd8e187c53047a04d2633d0` |

The staging volume needs at least **1,851,233,316 free bytes**, including a 512 MiB
reserve. Concurrent builds need additional headroom. Intake waited for sufficient
space, then completed with approximately 662 MiB free. A separate volume can be
selected with `--private-root`; symbolic-link destinations are refused. The helper
is terminated if free space falls below the reserve during extraction.

Validated metadata: PSARC version 1.4, 95 entries, 65,536-byte blocks; QAR 4,862
entries; path list version 1, 4,955 paths, 135 directories and 1,096 names.
The complete private report is `reports-private/asset-import.json`.

The default save root is `.local/user-data`, separate from the immutable asset
directory. Existing imports are refused unless `--replace` is explicit. Replacing
unknown directories or directories containing unrelated files is refused.
Cancellation terminates the running helper, removes staging, and retains the
previous import. A failed directory replacement restores the previous directory.

Reproduce in a fresh asset root with the local package path supplied explicitly
(an existing verified import requires explicit `--replace`):

```sh
python3 tools/import_pt_assets.py "$PT_PACKAGE" \
  --extractor .local/asset-helper/published/PT.PkgExtract \
  --expected-package-sha256 5aa60a4d8cbaa6a1b765d1d6a6347a4a7c433e912db7535da2fb667f8ea76cb5 \
  --report reports-private/asset-import.json
```

The report records package pre/post hashes, asset hashes, metadata and the
separate save root. It explicitly leaves runtime/device verification false.

## Verification

32 synthetic tests pass across the two intake test files. They cover bounded
container/SFO reads, source preservation, asset corruption, PSARC/QAR/path-list
bounds, unexpected paths, symlinks, disk-space refusal, source mutation,
cancellation with process termination, previous-data/save preservation and
directory-swap rollback, including cancellation immediately after a rename.

```sh
python3 -m unittest discover -s tests -p 'test_*package*.py'
python3 -m unittest discover -s tests -p 'test_*assets*.py'
```

The next baseline step is the native engine's archive/scene loading checks against
the imported asset directory. Exact asset hashes establish intake identity; they
do not establish rendering, gameplay, microphone behavior or iPad performance.
