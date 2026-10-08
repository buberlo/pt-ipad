# Native P.T. implementation plan

Approved target: a standalone ARM64 app for the existing M2 iPad, reconstructed C++ game logic with original P.T. assets, faithful presentation and a sustained 30 FPS. Original-executable recompilation, VR, enhancement features and store publication are outside the first release.

## Ordered milestones

1. **Reproducible source:** public source repository, clean pinned upstream v1.0.1, ordered Apple patches, pinned dependencies, local builds and license provenance. A fresh checkout must reconstruct the tested source. Game data and signed application artifacts remain private.
2. **Assets and reference:** hash the CUSA01127 v01.00 package; validate extraction using the supported host helper; retain a manifest for the three original archives. Reproduce the Windows reference and record its known fidelity/progression defects. Package metadata alone is not asset acceptance.
3. **Native builds:** macOS ARM64 baseline followed by an iPhoneOS ARM64 bundle. Separate host shader tools from target libraries, statically link voice recognition, fix platform paths and omit desktop enhancement executables, upscalers, OpenXR and Game+.
4. **Renderer qualification:** probe actual features, shader translation, formats, sample counts and descriptor limits. Adapt texture bindings and portability handling. Require authentic corridor rendering, movement, collision and audio on-device.
5. **iPad integration:** shared touch/controller game actions, microphone permission, offline voice recognition, foreground-only rendering, interruption handling, staged verified assets and separate saves. Complete the teaser and resolve relevant upstream regressions.
6. **Acceptance and delivery:** match original-reference scenes, complete touch/controller playthroughs, verify cold offline launch and lifecycle behavior, and measure at least 20 minutes of representative play. Deliver a development-signed IPA and exact build/source/assets evidence only after these gates pass.

## Native interfaces

- Host services provide application resources, writable save/cache/data directories, lifecycle state, microphone access and actual presentation measurements.
- Input produces the existing engine's movement, look, interaction, zoom and pause actions; touch and physical controllers share those actions.
- Asset installation validates hashes into a staging directory and activates only complete data. Saves remain in a separate application-support location.

## Acceptance criteria

- Preserve 1080p internal rendering and a 30 FPS cap initially; verify actual scene resolution independently of the window or display size.
- Test corridor/bathroom/mirror/flashlight/encounter scenes at matched state. Explicit regression cases: upstream loop 7/8 progression and mirror flashlight reflection.
- Exercise malformed archives, cancelled/failed imports, full storage, save preservation, controller disconnection, microphone denial, background/resume and audio interruption.
- Count presented frames rather than submission calls. Require steady-state p95 frame intervals at most 40 ms during a representative 20-minute run; report loading separately.
- Verify launch after reboot with development tools disconnected and networking unavailable. No CPU JIT activation or VPN is permitted.
- Acquire and release a bounded shared-device lease for every device command. Preserve the queue and unrelated paused projects.

Implementation status and test evidence belong in STATUS.md; unchecked milestones are not implied by this plan.
