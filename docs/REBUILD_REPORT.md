# Independent rebuild evidence — 2026-10-08

The independent build used local implementation snapshot `f94ed9d` on `codex/alpha-rebuild-tools`. Its public equivalent is `d2bf785`, rebased onto the concurrently sanitized repository history; the runtime source and dependency recipe are unchanged. Follow-up changes add race tests, explicit signer Xcode selection and acceptance documentation; they do not change the game source recipe. The generated source hash is `dbd1a4930d595c5a27daad94225f454717b91f090651e1d9cee317df08ff165f`, identical to the active development source and a separate sixteen-patch reconstruction. Upstream remains clean at `5c6307886f4470d8391bf49445a7c9124ea9d623`.

## Fresh inputs

A separate Git clone began with no build or dependency directories. Its upstream was downloaded from the public source URL. All thirteen game dependencies were fetched into this clone and validated against `dependency-lock.json`. Voice models were downloaded into its own build directory and verified before and after bundling. The original-assets integration tests read the existing verified private extraction; the PKG extractor was not rerun for this rebuild.

MoltenVK was cloned separately, checked out at `fae55a18779ee59da2cc5373a367a0282779c171`, and compiled from source with newly fetched external dependencies and four Xcode jobs. No pre-existing driver archive was copied. Its resulting SHA-256 is `5b04b88bd96ea1905e6217b9424bc5fc4c78dd58607428b45cd6fa916464384d`, matching the historical archive. A private build receipt records all external revisions and Xcode 27.0 / 27A266a. The source checkout remained clean. A whitespace problem in the upstream Makefile was resolved through a temporary executable wrapper without editing source.

Host compiler: AppleClang 21.0.0.21000334; iPhoneOS SDK 27.0; ARM64; minimum iOS 18.0. Complete observed CMake/Ninja/glslc/Xcode/compiler versions and hashes are retained in each build manifest. Bit-identical application binaries are not claimed.

## Passed local gates

- Final tooling suite: **109 Python tests**, including custom identity/signature mismatch, resource corruption, cross-process competing leases, paused authorization, stale/missing cleanup and token protection. No external coordinator or physical device is used by these tests.
- Fresh clone: **107 Python tests** from the tested commit; **12/12 native CTests**, concurrent native touch-state checks and Metal split-descriptor 2×2 GPU readback at index 1143.
- Both development and fresh-clone original-assets integration: **35 checks** passed. This is native Mac input/menu/startup integration, not a device playthrough.
- Independent Mac and iOS apps built with `org.example.pt.rebuild`. iOS was development-signed with a matching existing wildcard profile and certificate; the signer verified entitlement, certificate, executable, resource and manifest identity.
- Custom XCTest harness/runner built and signed for iOS, then checked by the actual product validator against the signed native app. This was `build-for-testing`; **no device test methods executed** in this step.

Independent iOS manifest SHA-256: `fdc14df4bd2be280fc346ffabf11e89ab3c8790f57631d63e652af79c65651e1`. Independent unsigned executable: `fda7bf2874c931333ff79ad193411860957f04c2a68b97eb1e5dd80104b2e4d6`. Independent signed executable: `0e1171dbdafffc0ef0ce4316bc0cd37a1529630723ab940e5a3d5f7322e37b33`. Independent IPA: `42fff214839760bd8a728049e9f4aa715c0c290e0b9da05a1c2c027942bb86b1`. Raw logs, models, signing outputs and private manifests remain outside Git.

## Candidate 7 and M2 limits

The default candidate retains `com.konradkern.pt.native` and application build **7**. It is **built and signed**, with local IPA SHA-256 `39fa567266679249d4bce520a538ff09a21ee3cfdddc8b214456702cf17473a8` and signed executable SHA-256 `c4c6718cae23af587912675ff56957be6589db237482460b8b7f2549a9bd14f1`. It has **not been installed or launched** on the M2 and is **not gameplay-accepted**.

A bounded read-only lease preflight verified the current iPad Air 13-inch (M2), iPad14,10, iPadOS 27.0.1 / 24A446, and found an existing P.T. process. That session was preserved. No installation, foreground takeover, new screenshot claim, scripted ending run or timing measurement was performed. Both short leases were released after host-command cleanup and preserved the shared queue.

The user deferred complete touch/microphone and controller playthroughs plus reboot/offline checks. Ending, wider lifecycle/input, matched scene comparison and the ≥20-minute p95 ≤40 ms performance gate remain open. Earlier builds' results do not qualify candidate 7. No alpha tag or release is created until [all acceptance gates](ALPHA_ACCEPTANCE.md) pass.
