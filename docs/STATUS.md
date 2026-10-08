# Implementation status

As of 2026-10-08, the complete engine builds for macOS ARM64 and iPhoneOS ARM64. A development-signed build has been installed and launched on the physical M2 iPad; a fresh device screenshot shows the original starting room after its opening animation. Full playability and release acceptance are still pending.

| Gate | State |
| --- | --- |
| Private GitHub repository | Created; Actions disabled |
| Native source baseline | v1.0.1 pinned; three initial patches reconstruct the tested source tree exactly |
| Original package metadata | CUSA01127, v01.00 identified and hashed |
| Game archives extracted and validated | Three archives match upstream US hashes; 12 core packages readable |
| macOS ARM64 engine | Built; real assets rendered; ten asset-free CTests pass |
| iPhoneOS ARM64 bundle | Built with static MoltenVK and whisper; no Wine, FEX or CPU JIT |
| Signed and installed on iPad | Confirmed for development build 2 (`CFBundleVersion=1`) |
| Foreground launch and authentic scene | Confirmed on M2 iPad; starting room visible, audio device initialized, touch overlay visible |
| Complete gameplay | Mac automated full route reaches 27/27 milestones and ending; physical-device playthrough remains pending |
| 30 FPS performance acceptance | Pending |

The touch-control state tests passed with AddressSanitizer and UndefinedBehaviorSanitizer. The real input/options-menu integration test also passed. These verify input mapping, not physical touchscreen or controller operation.

## Device evidence

Development build 2: native `arm64`, platform `IOS`, deployment target 18.0, bundle `com.konradkern.pt.native`. The development profile carries no CPU-JIT entitlement. IPA SHA-256: `bcfdfd659cb43f3e650119c931c039c9ad00435226e872412361376535b98986`; signed executable: `9ca5889fe8204fa2ce1a23773a27ff7c5c20d6a010193d37c3b1b8b943f843cd`.

The app loaded all core packages, initialized stereo 48 kHz audio, completed the opening animation and reached game step 15 on `f010`. The fresh 35-second screenshot shows the starting-room door and original scene with the independent touch overlay. The actual presentation counter reached 739 frames before this bounded run ended; its rolling rate settled around 30 FPS after loading. This short stationary scene is **not** a 20-minute representative-play performance result. Audible output, physical controls, microphone interaction, corridor traversal and ending on iPad remain unverified.

Rendering used an internal 1920×1080 target, a 2732×2048 display surface, a 30 FPS cap and actual `VK_GOOGLE_display_timing` timestamps. The app's own PID was terminated before releasing the shared device lease. Logs, screenshots, installation receipt and original assets remain in ignored private directories.

## Remaining acceptance work

- Atomic verified device-side asset activation, cancellation and preservation of existing saves.
- Fix and retest inherited script issues: six missing standalone test-VM APIs and `trapLightEnable.lua` receiving a missing model-data array.
- Physical touch/controller traversal, audio/microphone, interruption/background/resume and complete ending.
- Matching corridor, bathroom, mirror/flashlight and encounter image comparisons against the Windows baseline and original-game references.
- 20 minutes of representative presented-frame timing, including p95 intervals; loading reported separately.
- Reboot/disconnected/offline standalone launch and development-signed final delivery.

The macOS walkthrough uses scripted inputs, including an injected voice result. Its successful ending does not prove microphone recognition or visual parity. No Windows reference baseline has been run in this implementation session.
