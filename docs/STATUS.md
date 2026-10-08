# Implementation status

As of 2026-10-08, development build 4 is a compiled and development-signed native ARM64 iPad app. Original assets are extracted and verified. Build 3 ran on the physical M2 iPad through the final-puzzle loop; build 4 contains the fixes found during that run. Full release acceptance is **not complete**.

| State | Evidence |
| --- | --- |
| Repository | Private buberlo/pt-ipad; GitHub Actions disabled; local checks only |
| Reproducible source | Immutable upstream v1.0.1 plus 14 ordered patches; fresh reconstruction matches the built source |
| Assets | CUSA01127 v01.00; three matching US archive hashes; 12 readable core packages |
| Built | Complete macOS ARM64 and iPhoneOS ARM64 build 4, 1080p internal target, 30 FPS cap |
| Signed | Build 4 signature, certificate/profile and embedded build manifest verified |
| Installed | Build 3 confirmed on the M2 iPad; build 4 installation pending |
| Launched | Build 3 foreground scenes and runtime logs confirmed, including corridor, bathroom, peephole and f160 |
| Playable | Final Mac automated ending passes; iPad scripted run reached 23/27 checkpoints but missed the timed final-puzzle sequence |
| Accepted | No: complete physical playthrough, controls, visual parity and sustained performance remain open |

## Build 4 identity

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
- Touch/gamepad action mapping and native touch menus, including first-boot Continue/Back and direct camera/settings row taps. Event integration passes 22 asset-free checks and 31 checks with original assets. These are not physical-touch acceptance.
- f080 original model-data spelling compatibility, mirror flashlight/shadow repair, fitted-output screenshot capture, thermal/power telemetry and asynchronous windowed voice-file testing.
- All 12 asset-free CTests pass. Final shared-code validation passes 97 original Lua chunks and 49/49 milestones across four headless Mac routes, including the ending, with no runtime error lines. Two original f060 waypoint diagnostics are retained separately.
- The fitted screenshot GPU regression fails against the old renderer and passes with the repair. Six matched native Mac mirror comparisons demonstrate a reflected beam and room-side shadow casting; original-game visual parity remains unverified.

See [gameplay tests](GAMEPLAY_TESTS.md), [native touch menus](NATIVE_TOUCH_MENU.md), [asset installation](ASSET_INSTALLATION.md), [mirror validation](MIRROR_REFLECTION.md), and [voice timing](VOICE_TEST_TIMING.md).

## Physical device findings

[DEVICE_REPORT.md](DEVICE_REPORT.md) records the tested build 3 run, timing limits and build 4 follow-up. Its 28,828 actual presentation observations include about 16m41s of startup, traversal, scripted waiting and idle time, not 20 minutes of representative gameplay. Guarded pre-voice traversal averages 29.997 FPS. One bathroom window has a 50 ms p95 interval; injected voice testing also produces half-second stalls. Build 4 removes the voice test's blocking wait, but its post-fix performance has not yet been measured.

The foreground route missed the final puzzle because it attempted the ten steps before the timed introduction activated the puzzle. The updated test variant waits for the original f120/f160 sequences to finish, without changing game flags or progression. Its corrected ending still needs a physical-device run.

An earlier XCTest attempt timed out while enabling Xcode automation: zero methods executed. The build 4 retry was refused before installing or launching anything because a new P.T. session was already running. That session was preserved; permission to close it for testing is pending. All processes created by the recorded build 3 run were confirmed gone before releasing its lease. Other projects' queued work remains intact.

## Open acceptance gates

1. Install build 4 and run the corrected foreground route through the ending, with working scene captures and thermal/power records.
2. Verify physical touch/controller input, saves, microphone permission/recognition, audible audio, interruptions, disconnects and background/resume.
3. Reproduce the Windows reference and compare matching corridor, bathroom, mirror, flashlight and encounter scenes against it and original-game references. The reference-machine connection details are still pending.
4. Measure at least 20 minutes of representative play; report loading separately and verify the 30 FPS / p95 ≤40 ms goal. Investigate the bathroom pacing window rather than relying on the overall average.
5. Verify launch after reboot with development tools disconnected and networking unavailable.

The measured M2 content fits the current 1,144-image/64-cube descriptor contract. Per-material paging and a host texture-conversion cache have not been implemented; no demonstrated target-device format or descriptor failure currently requires them. They remain explicit architecture gaps if later content/capability evidence requires those fallback paths.
