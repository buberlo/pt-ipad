# Implementation status

As of 2026-10-08, development build 6 is a compiled and development-signed native ARM64 iPad app. Build 6 is installed as P.T. on the M2 iPad. Original assets are extracted and verified. Build 3 ran on the physical M2 iPad through the final-puzzle loop; builds 4–6 contain the subsequent fixes and presentation changes. Full release acceptance is **not complete**.

| State | Evidence |
| --- | --- |
| Repository | Public buberlo/pt-ipad; GitHub Actions disabled; local checks only |
| Reproducible source | Immutable upstream v1.0.1 plus 16 ordered patches; fresh reconstruction matches the built source |
| Assets | CUSA01127 v01.00; three matching US archive hashes; 12 readable core packages |
| Built | Complete macOS ARM64 and iPhoneOS ARM64 build 6, 1080p internal target, 30 FPS cap |
| Signed | Build 6 signature, certificate/profile and embedded build manifest verified |
| Installed | Build 6 confirmed on the M2 iPad as P.T. |
| Launched | Build 6 running process observed; build 5 fresh startup and corridor verified; build 3 previously captured bathroom, peephole and f160 |
| Playable | Final Mac automated ending passes; iPad scripted run reached 23/27 checkpoints but missed the timed final-puzzle sequence |
| Accepted | No: complete physical playthrough, controls, visual parity and sustained performance remain open |

## Build 6 identity

- Patched source tree SHA-256: `dbd1a4930d595c5a27daad94225f454717b91f090651e1d9cee317df08ff165f`.
- IPA SHA-256: `d01101580c72e7d481844de6b9b68645f911d77705a95da9cbd0cc21107055e2`.
- Signed executable SHA-256: `abb8435fbc789d4e374118f1ecb9d2f9b16ded16bc906900c4fb551cf4b0d223`.
- Embedded build-manifest SHA-256: `6c295007454fe005e54f6618e94778080a9fb0f14cbc79d4e6e45a013179515b`.

Build 6 makes the look hint temporary. Native macOS/iOS builds and signatures are verified; installation and a running process are verified on the M2 iPad. The first UI-test attempt preserved an existing game session; a later attempt installed build 6 but executed zero methods because Xcode rejected its iteration argument. The argument has been removed. A retry preserved a newly opened game session. The observed process was not a controlled foreground test, so physical touch and hint-dismissal behavior remain unqualified.

## Historical build 5 identity

- Patched source tree SHA-256: `0e2690b575857642dbb52a819a1bc55df022fc3a18cf71e30dada4afb3edb1a2`.
- IPA SHA-256: `f338f9c141ccffc141ce6538bc7f853ce3d428273d65ce73a3a1359ec09c6e2d`.
- Signed executable SHA-256: `31fc45e2766f9a7098af6bd4313008cbe1554ca00ba82a4e58ef4544b8e2b25c`.
- Embedded build-manifest SHA-256: `fa4080c9b11dd661658999eba6054662026cfa4ae8a55cadf02b8d4f840ffe72`.

The app has `CFBundleName=P.T.`, `CFBundleDisplayName=P.T.` and `CFBundleVersion=5`. [Presentation changes](APP_PRESENTATION.md) cover the original icon, automatic startup and revised touch layout. The bundle identifier and application container are preserved. Installation and launch receipts remain private in `reports-private/build5-update/` and `reports-private/build5-startup/`. The fresh startup showed the original intro and corridor without opening options; [device results](DEVICE_REPORT.md) retain the timings and limitations.

## Historical build 4 identity

- Upstream: `5c6307886f4470d8391bf49445a7c9124ea9d623` (v1.0.1).
- Patched source tree SHA-256: `996fcb646a6a77b2ed37d7ed450d21606119b8a3a2ee96bceca24d70dc3d488c`.
- IPA SHA-256: `f5151e7f658121c324886962b4b6a63ecd1852f137b53756671b7f3e32aff48f`.
- Signed executable SHA-256: `77a28b27bceecf8f3cb3ed0c23e23668184c4fbf0eeea6f23b3b99d2318afb16`.
- Embedded build-manifest SHA-256: `adcab08c0c54be39220d3123ad537579de61859f40f23434f8a5ab8eb3ce12fd`.

The bundle is `com.konradkern.pt.native`, `CFBundleVersion=4`, native `arm64`, platform `IOS`, deployment target 18.0. Its development profile has no CPU-JIT entitlement. It links no Wine/FEX/desktop runtime. The signed app/IPA, profiles, raw captures and game data remain private and outside Git.

## Completed implementation and local checks

- Native build and resource packaging, host shader compilation, static ARM64 whisper, application data/save/cache paths and SDL/UIKit lifecycle support.
- Capability-aware Vulkan/MoltenVK setup, supported depth/sample selection, bounded split image/sampler descriptors, and actual presentation-timestamp tracing.
- Verified native asset staging, hash checks, atomic activation, cancellation/rollback and repair of a damaged owned installation. Twenty native installer cases pass with sanitizers.
- Touch/gamepad action mapping and native touch menus, including first-boot Continue/Back and direct camera/settings row taps. Event integration passes 22 asset-free checks and 35 checks with original assets in build 5, including startup without options and preservation of the intro. These local checks are not physical-touch acceptance.
- f080 original model-data spelling compatibility, mirror flashlight/shadow repair, fitted-output screenshot capture, thermal/power telemetry and asynchronous windowed voice-file testing.
- All 12 asset-free CTests pass. Build 4 shared-code validation passed 97 original Lua chunks and 49/49 milestones across four headless Mac routes, including the ending, with no runtime error lines. Two original f060 waypoint diagnostics are retained separately.
- The fitted screenshot GPU regression fails against the old renderer and passes with the repair. Six matched native Mac mirror comparisons demonstrate a reflected beam and room-side shadow casting; original-game visual parity remains unverified.

See [gameplay tests](GAMEPLAY_TESTS.md), [native touch menus](NATIVE_TOUCH_MENU.md), [asset installation](ASSET_INSTALLATION.md), [mirror validation](MIRROR_REFLECTION.md), and [voice timing](VOICE_TEST_TIMING.md).

## Physical device findings

[DEVICE_REPORT.md](DEVICE_REPORT.md) records the tested build 3 run, timing limits and build 4 follow-up. Its 28,828 actual presentation observations include about 16m41s of startup, traversal, scripted waiting and idle time, not 20 minutes of representative gameplay. Guarded pre-voice traversal averages 29.997 FPS. One bathroom window has a 50 ms p95 interval; injected voice testing also produces half-second stalls. Build 4 removes the voice test's blocking wait, but its post-fix performance has not yet been measured.

The foreground route missed the final puzzle because it attempted the ten steps before the timed introduction activated the puzzle. The updated test variant waits for the original f120/f160 sequences to finish, without changing game flags or progression. Its corrected ending still needs a physical-device run.

An earlier XCTest attempt timed out while enabling Xcode automation: zero methods executed. The build 4 retry was refused before installing or launching anything because a new P.T. session was already running. That session was preserved at the time. The user subsequently requested P.T. first; build 5 was then installed over the same bundle and its fresh startup was verified under a bounded lease. All processes created by the recorded build 3 run were confirmed gone before releasing its lease. Other projects' queued work remains intact.

## Open acceptance gates

1. Run the latest installed build through the corrected foreground ending route, with working scene captures and thermal/power records.
2. Verify physical touch/controller input, saves, microphone permission/recognition, audible audio, interruptions, disconnects and background/resume.
3. Reproduce the Windows reference and compare matching corridor, bathroom, mirror, flashlight and encounter scenes against it and original-game references. The reference-machine connection details are still pending.
4. Measure at least 20 minutes of representative play; report loading separately and verify the 30 FPS / p95 ≤40 ms goal. Investigate the bathroom pacing window rather than relying on the overall average.
5. Verify launch after reboot with development tools disconnected and networking unavailable.

The measured M2 content fits the current 1,144-image/64-cube descriptor contract. Per-material paging and a host texture-conversion cache have not been implemented; no demonstrated target-device format or descriptor failure currently requires them. They remain explicit architecture gaps if later content/capability evidence requires those fallback paths.

## Alpha implementation update — 2026-10-08

Independent native Mac/iPad rebuilding, custom bundle identity, real development signing and locally built custom XCTest products are verified in [REBUILD_REPORT.md](REBUILD_REPORT.md). The repository contains its own shared-device coordinator and unified local test command. Candidate **7 is built and signed locally**, but is **not installed, launched, playable-verified or accepted**. A running M2 P.T. session was preserved. Human checks were deferred by the user; automatic ending/performance and remaining acceptance gates stay open in [ALPHA_ACCEPTANCE.md](ALPHA_ACCEPTANCE.md). No alpha tag has been set.
