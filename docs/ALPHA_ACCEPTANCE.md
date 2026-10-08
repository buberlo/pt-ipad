# v0.1.0-alpha.1 acceptance

The milestone combines independent rebuilding and physical M2 iPad acceptance. The release is source-only. A development-signed IPA is delivered locally. No alpha tag is created until every required gate passes.

| Gate | Current outcome |
| --- | --- |
| Configurable app identity and profile validation | Implementation in progress; fake signing and corruption tests cover identities |
| Repository-contained device coordinator | Implementation in progress; fake-record tests only |
| Fresh clone, empty dependencies, rebuilt pinned MoltenVK | Pending |
| Final candidate built / signed / installed / launched | Pending; older build 6 remains separate evidence |
| Corrected scripted route reaches actual ending on M2 | Pending |
| Touch and microphone full playthrough | Deferred by user; pending human test |
| Controller full playthrough and disconnect | Deferred by user; pending human test |
| Lifecycle, save/reload, audio interruption, microphone denial | Pending |
| 20 minutes foreground, 1080p, 30 FPS, p95 ≤40 ms | Pending |
| Reboot, tools disconnected, networking unavailable | Deferred by user; pending human test |
| Matched native Mac / iPad scenes | Pending |
| Complete original visual fidelity | Open until original references are reviewed |

## One candidate

Record repository revision, ordered patch hashes, generated source hash, build manifest, IPA/executable hashes, device/OS identity and installed executable identity. Do not combine older builds' results into acceptance of a new candidate. Repeat affected gates after relevant changes.

## Human checklist

On the final supplied build: move and look together; USE, held zoom, pause and settings; check that the look hint disappears on first swipe or within eight active gameplay seconds. Complete the ending with touch and actual microphone input, then with a controller. Save and reload; background/resume; interrupt audio; disconnect controller; deny microphone permission. Reboot, disconnect development tools, disable networking and launch again. Record pass/fail and checkpoint for each item. User deferred these human checks on 2026-10-08.

## Performance and visual checks

Measure actual presented frames over at least 20 minutes of representative foreground play; loading and menus are separate. Report p95, slow intervals, thermal state and coverage of corridor/bathroom/mirror/flashlight/encounters. A scripted route's elapsed duration alone does not qualify this gate. Compare corresponding native Mac/iPad captures and retain private evidence locally.
