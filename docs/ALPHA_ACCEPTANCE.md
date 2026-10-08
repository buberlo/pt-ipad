# v0.1.0-alpha.1 acceptance

The milestone combines independent rebuilding and physical M2 iPad acceptance. The release is source-only. A development-signed IPA is delivered locally. No alpha tag is created until every required gate passes.

| Gate | Current outcome |
| --- | --- |
| Configurable app identity and profile validation | Passed local corruption tests and real independent iOS signing with custom ID; custom XCTest products built and validated |
| Repository-contained device coordinator | Implemented; fake-record race/stop/cleanup tests pass; bounded M2 read-only preflight passed |
| Fresh clone, empty dependencies, rebuilt pinned MoltenVK | Passed for Mac and iOS; custom signed rebuild verified. See REBUILD_REPORT.md |
| Final candidate built / signed / installed / launched | Build 7 built and signed locally; not installed/launched because a preexisting P.T. session is running |
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
