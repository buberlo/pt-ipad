# M2 iPad evidence report — 2026-10-08

**Acceptance: incomplete.** This report distinguishes the measured build 3 from the signed build 4 candidate. It does not qualify complete gameplay or sustained performance.

## Device and inputs

Physical iPad Air 13-inch (M2), model iPad14,10. Rendering uses the Apple M2 GPU, a 1920×1080 internal target, a 2732×2048 drawable and a 30 FPS cap. Game data is the verified CUSA01127 v01.00 US dataset in [ASSET_STATUS.md](ASSET_STATUS.md). The shared device lease was held during installation, launch, sampling and process cleanup. Private device identifiers remain in the local receipts.

Measured build 3 source: `f84de4a53b0ef63635f10832cd39f59f62cf085de68993379f3ca07288a373ab`; signed executable: `03960d6fe63adf0e1c5114d8d62bffc89534ab0ac26243dc5e89d10301f090a8`. This is the nine-patch build, not the later 14-patch candidate.

The run uses a foreground SDL window, no save writes, seed 1, original demo speed, scripted navigation and a locally synthesized prerecorded “Jack” sample. It neither exercises a physical microphone nor proves physical touch/controller input. Native archive verification completes successfully before game loading. Original scene content appears in all periodic post-startup device captures.

## Progression

The first options screen closes at 28.553 s and f010 starts at 69.768 s. The route traverses the corridor and bathroom, passes f080, clears the peephole sequence and reaches f160 at 696.073 s. It completes 23/27 expected milestones. The final puzzle is not completed: the accelerated desktop route attempts the ten steps before its real-time introductory sequence activates TrueEnd.

The f120 scene is not permanently hung. Its 5,878-frame sequence begins at 564.340 s and sends Endf120 at 662.506 s; the scripted restart follows. Premature navigation faces a wall during much of that wait. Later f160 images show a stationary corridor, not an ending.

Twenty-five error lines are failed native screenshot writes from the fixed-render-target/letterbox readback defect. Nine independent OS screenshots remain usable evidence of displayed scenes. All errors and waypoint warnings are preserved. The normal application shutdown is logged at 1001.479 s; process exit is separately confirmed after SIGKILL escalation.

## Actual presentation timing

The retained CSV contains 28,828 `VK_GOOGLE_display_timing` actual presentations, with no missing IDs or duplicate rows. Two early actual-time reversals create segment boundaries; intervals across those boundaries are not reconstructed. Renderer trace shutdown reports `write_ok=true`.

CSV row/count alignment was checked against 923 log anchors. Source frame numbers differ from presentation IDs and were not used interchangeably. Phase boundaries use displayed-count anchors with two-second guards; they are coarse phase summaries, not exact frame-by-frame scene synchronization.

| Sample | Actual FPS | p95 interval | Maximum interval | Meaning |
| --- | ---: | ---: | ---: | --- |
| Guarded traversal before voice, approximately 71–568 s | 29.997 | 33.334 ms | 83.335 ms | Multiple moving scenes and local scripted holds |
| Full bathroom/f060 window, approximately 225–286 s | 29.991 | 50.000 ms | 50.001 ms | Pacing exceeds the 40 ms target in this scene window despite the average |
| Full f160 voice-file window, approximately 706–765 s | 26.816 | 33.334 ms | 550.004 ms | Thirteen intervals above 100 ms; p95 alone hides rare long stalls |

The total run is about 16m41s and includes startup, timed waiting, restart and idle tails. It is **not** a 20-minute representative-play benchmark. Thermal pressure and Low Power Mode were not recorded by build 3.

## Corrections in build 4, awaiting device retest

- Working screenshot readback for the fitted 1080p frame; a real GPU regression validates fresh pixels and repeated/resized captures.
- Native first-launch/pause/settings touch navigation and correct letterbox hit testing.
- Thermal-pressure and Low Power Mode samples alongside actual presentation timing.
- Windowed prerecorded voice follows the same asynchronous worker path as the normal microphone; deterministic Drain waits remain limited to headless tests.
- The host route variant waits for the original f120/f160 demos before continuing, retaining original gameplay commands and recording its provenance.

The measured voice stalls coincide with the old file-input Drain wait. Removing that wait does not establish the new frame rate or eliminate possible CPU contention. The bathroom pacing issue remains open and requires controlled device comparison.

Build 4 is built and signed as identified in [STATUS.md](STATUS.md). Its installation/test attempt was refused before mutation because another P.T. session was open. The new session was preserved. An earlier XCTest attempt executed zero methods because Xcode automation initialization timed out; no physical-control pass is claimed.

## Retained private evidence

Raw artifacts and full analysis are under `reports-private/ipad-walkthrough-build3-run3/`, including `recovered-artifacts/` and `analysis/`. They are intentionally excluded from Git.

| File | SHA-256 |
| --- | --- |
| Actual presentation CSV | `928f53ce8b41e63e26180ea9480b89a69a95b0769b677b412b068f2c7de3189e` |
| Runtime log | `cf44ecda451e55dcbd2a3f3e7b2022f26ff490b23b46aecacb3afa85bf186d9d` |
| Executed route | `bb293b204d1d6b3ca3d7e6779a766c4c067fbf01dbce0db91b81aea024c603f9` |

Final acceptance still requires a physical ending, touch/controller and live-microphone play, lifecycle/save testing, original-reference visual comparison, 20-minute representative timing and reboot/disconnected/offline launch.


## Build 5 presentation and startup check

After the user requested P.T. first, a bounded lease installed development build 5 over the existing bundle. App-list evidence confirms the display name P.T. and bundle version 5. A separate 90-second fresh-startup check used `--no-save --no-mods` without a forced floor or options flag. Original assets verified successfully, controller step 6 went directly to step 8 at 4.944 seconds, and the original preface played. StartGame occurred at 44.516 seconds, followed by controller step 15 at 44.550 seconds. The 90-second foreground capture shows the authentic corridor and revised touch layout. No options menu opened.

The invocation-owned process was confirmed gone after SIGKILL escalation; its cleanup receipt released the shared lease. Receipts, images and runtime logs are private under `reports-private/build5-update/` and `reports-private/build5-startup/`. This verifies startup and visible controls; it does not establish touch behavior, complete gameplay or sustained performance.


## Build 6 installation and test limits

Build 6 is development-signed and installed as P.T., bundle version 6. App-list and process receipts match the installed bundle path; a game process was present during the read-only observation. The screenshot was not a controlled foreground game capture, so it cannot establish rendering or hint dismissal for this build. The updated look hint is implemented to disappear on the first swipe or after eight seconds of active gameplay.

The first input-test attempt preserved an existing game process before mutation. The deployment/test attempt installed build 6, but Xcode 27 rejected `-test-iterations 1`; zero methods executed. The helper now omits this unsupported argument and uses the default single execution. A subsequent attempt preserved a newly opened game session. No automated physical-touch pass is claimed. Private receipts are under `reports-private/build6-ui*` and `reports-private/build6-observed/`. Each bounded test reservation was released after its owned-process cleanup was confirmed; existing user sessions were preserved.
