# Native gameplay regression evidence

Verified locally on Apple Silicon macOS on 2026-10-08 using the pinned `pt-pc` source, this repository's Apple port patches, and the user's hash-verified CUSA01127 assets. Game data, generated logs, screenshots, and executables remain ignored. These results do not establish Windows parity or physical iPad gameplay acceptance.

## Scripted progression baseline

The native macOS executable ran the upstream `tools/walkthrough.py` scenarios with one job, `PT_HEADLESS_ONLY=1`, no screenshots, isolated working directories, and `--no-save`. Every native process exited 0. A local harness recorded process exit codes separately because the upstream walkthrough's milestone checks alone do not reject every process failure. The harness imposed a 900-second timeout per scenario.

| Scenario | Milestones | Frames | Outcome |
| --- | ---: | ---: | --- |
| `full` | 27/27 | 90,000 | Original route reached `ending`, controller step 33 |
| `photo` | 6/6 | 4,000 | Tested photo pieces collected |
| `photooption` | 7/7 | 4,500 | Photo option flow; 1 internal expectation, 0 failed |
| `gouge` | 9/9 | 14,000 | Eye/gouge route; 5 internal expectations, 0 failed |

The full route includes the repeated f050 loop, XMark, f070/f080, Hello, the peephole, f120, and TrueEnd. The route injects `svoice jack`; it does **not** test microphone recognition. Headless progression skips intermediate scene rendering, and milestone regexes do not prove animation, lighting, sound, or control parity. The photo scenarios cover selected pieces rather than all collectible combinations. Saves were disabled for these four runs.

Baseline evidence is under `reports-private/walkthrough-macos/`: `invocation.json`, `process-results.json`, `summary.log`, `runtime-error-audit.json`, and per-scenario `work/` logs. The executable SHA-256 is recorded in `invocation.json`.

## Errors found and compatibility fixes

The baseline full route logged four nonfatal `trapLightEnable.lua:27` errors during f080, although every progression milestone passed. Direct inspection of the original hallway FOX2 establishes the cause: two `GeoModuleCondition` entities serialize the dynamic link-array property as `modleData`; the original Lua reads `modelData`. Other hallway light conditions serialize the canonical spelling.

Patch `0005-game-validation.patch` maps that legacy spelling only for a `GeoModuleCondition` read of a missing `modelData` property, and only when the legacy value is a dynamic `EntityLink` array. Canonical values take precedence. Other classes, malformed types, and unrelated missing properties retain their previous behavior. Neither the package nor extracted assets are changed.

The standalone `--script-test` baseline also failed six chunks: it lacked explicit boot configuration constructors/methods, returned no UI daemon object, lost class constructors after Lua replaced a class table, and could not resolve archive paths used by nested `dofile` calls. The patch adds explicit configuration adapters and refreshes missing native methods without replacing Lua implementations. Its `dofile` adapter reads the mounted PSARC only and fails on missing paths or parent traversal. Unknown APIs still fail; there is no catch-all stub.

An isolated native validation executable compiled against the existing Mac dependencies runs all **97 archived Lua chunks with 0 failures**, without starting a renderer. Its **15 synthetic regression checks pass**, covering constructor configuration, API refresh, unknown API failure, missing archive scripts, the legacy array alias, canonical precedence, and malformed/other-class rejection. Reports: `reports-private/walkthrough-macos/validation-fix/`.

Configuration adapters are deliberately stubs: they record calls and preserve the value shapes needed to validate boot Lua. This does not implement original Fox rendering services, editor functionality, or pad mappings. The port's native renderer, sound, input, and gameplay bindings require their own runtime tests.

## Patched native app retest

The rebuilt Mac app (development build 3, patches 0001–0007) passed the original `--script-test` command with **97 chunks, 0 failures, exit 0**. Its executable SHA-256 was `2d7f57fc71640bed613f7cbe9a82e3153be43889e4d02ff58839bc2ea4595040`.

The same four walkthrough scenarios passed again: **49/49 milestones, all four native exits 0, and 0 runtime errors or failed/missing script warnings**. The full route reached the ending. This confirms that the f080 compatibility change removes the observed Lua error while retaining the tested progression. Evidence is under `reports-private/walkthrough-macos-patched/` and `reports-private/walkthrough-script-test-patched/`.

Shutdown telemetry reported the following peak descriptor counts:

| Route | 2D image slots / capacity | Cube slots / capacity | Materials / capacity |
| --- | ---: | ---: | ---: |
| full | 912 / 1,144 | 8 / 64 | 535 / 16,384 |
| photo | 547 / 1,144 | 8 / 64 | 305 / 16,384 |
| photooption | 551 / 1,144 | 8 / 64 | 305 / 16,384 |
| gouge | 554 / 1,144 | 8 / 64 | 307 / 16,384 |

The tested Mac routes did not exhaust these descriptor budgets. Headless traversal and desktop resource counts do not prove iPad frame rate, physical memory use, or all intermediate rendering behavior. Later renderer changes require their own regression and visual checks against their resulting executable.

## Final build 4 shared-code regression

The final build 4 Mac executable, including patches `0001`–`0014`, passed the same four scenarios again on 2026-10-08: **49/49 milestones, four native exits 0, and 0 runtime errors or failed/missing script warnings**. The full route reached the ending. Its separate `--script-test` run passed **97 chunks, 0 failures, exit 0**.

This run used source-tree SHA-256 `996fcb646a6a77b2ed37d7ed450d21606119b8a3a2ee96bceca24d70dc3d488c` and executable SHA-256 `c6ff05b8306be0ba1fedd0f7363044965beb338ea68a9600949b28866cda14df`. Both were verified unchanged after the tests. The build manifest and all 14 patch hashes, exact commands, process results, logs and assertions are retained under `reports-private/walkthrough-macos-build4/`, with the combined result in `final-evidence.json`.

The full route retains two upstream navigation diagnostics at the same f060 waypoint: a temporary stuck warning and its bounded waypoint timeout. Progress subsequently reaches all expected milestones, including the ending. These warnings are recorded separately from runtime errors and must not be hidden or mistaken for proof that every navigation step was exact. The tests run headless with accelerated demos, no screenshots and saves disabled; they validate shared progression and script behavior, not physical input, the fitted screenshot path or sustained iPad performance.

## Offline native voice integration

A separate native Mac run used a locally synthesized Samantha voice saying “Jack.”, converted to 16 kHz mono PCM16 WAV with silence padding (2.46 seconds total). The bundled static Apple ARM64 Whisper runtime loaded `ggml-base.en-q5_1.bin` and `ggml-silero-v6.2.0.bin` in 81 ms, recognized one utterance as `Jack`, and reported one detection with probability 0.556 and decode time 215 ms. The process exited 0. Executable SHA-256: `d8a57a4a590d3244e6ab6290f2bbd1ada22bac801fb3760fd36baa15f574bcec`.

Evidence: `reports-private/voice-synthetic/result.json`, `native-voice.log`, and the generated WAV. This is one synthetic positive integration check of the native model-loading, VAD, and recognition path. No microphone was opened. Human voice accuracy, false-positive behavior, permission handling, and physical iPad microphone operation remain unverified.

## Outstanding acceptance

- Compare original Windows/native reference captures with corresponding native Mac/iPad scenes; no Windows reference run was reproduced here.
- On the physical iPad, verify asset delivery, touch/gamepad controls, real microphone recognition, save/resume, app backgrounding, visual/audio behavior, and sustained frame time in active scenes. A signed or installed application does not satisfy these checks.
