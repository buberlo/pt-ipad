# M2 frame-mode pilot report — 2026-10-08

**Stable 1080p / 60 FPS has not been reached.** These are interrupted diagnostic pilots, not final performance or visual acceptance. The default remains 30 FPS. Original quality, internal resolution and simulation speed have not been reduced to meet the target.

## Comparison candidate

- Build 9, native ARM64, development-signed, installed and launched on the M2 iPad Air 13-inch (`iPad14,10`), iPadOS 27.0.1 / 24A446.
- Upstream `5c6307886f4470d8391bf49445a7c9124ea9d623`; 18 ordered patches.
- Source SHA-256 `42eef3a2551d9701beb3f4720dc7f7542b5ae0f5b366ad7c9784a08ec152f3ff`.
- IPA SHA-256 `6a14715c823938304ed11aaea4610a2b6f20b6174b7bd9459b7eb19433c052e0`.
- Signed executable SHA-256 `b757e00d8cea69aab8fede963f19226df4cabf111db2dc852c75050a9e83d4a0`.
- Manifest SHA-256 `5d804d29b3015d0befdbe5077775f8213ffec57fa383b9bbcbff5333dc3bfe98`.
- Same installed verified US assets, seed 1, full route, demo rate 1, isolated fresh settings, saves disabled, VSync enabled, upscaler/frame generation off. Runtime status repeatedly reports 1920×1080 internal rendering. Low Power Mode was off. Existing saves were not overwritten.

## Retained actual-display intervals

The CSV parser excludes the first 30 seconds per segment. These aggregate retained intervals still include intro/loading/transitions; they are **not** reviewed active-gameplay scene windows or an accepted A/B improvement measurement.

| Requested cap | Retained intervals | Observed seconds | Actual FPS | p95 | p99 | Longest interval |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3,404 | 116.117 | 29.315 | 33.334 ms | 50.000 ms | 933.344 ms |
| 60 | 6,749 | 209.518 | 32.212 | 33.334 ms | 50.000 ms | 2,501.042 ms |

The 60 pilot ended after recorded background suspension. The 30 pilot ended when the device file service closed a transfer socket unexpectedly. Both owned processes were cleaned up and their bounded leases released. Neither run supplies a 20-minute active foreground window, all required two-minute scene windows, or a final five-minute thermal window.

Thermal state reached `serious` in the 60 pilot and `critical` in the later 30 pilot. Consequently, do not treat differences between these aggregate runs as a controlled optimization gain. Device temperature needs to settle before another matched comparison.

## Diagnostic finding

Buffered GPU samples on f010 in the 60 pilot report median total GPU time 29.21 ms, with lighting 8.42 ms and postprocessing 7.88 ms; scene recording CPU median is 0.40 ms. These are renderer samples rather than end-to-end CPU latency. GPU samples on f040 report 30.19 ms total, lighting 7.96 ms and postprocessing 7.65 ms. GPU work and thermal degradation therefore require investigation before tuning only the software cap.

Private raw evidence: `reports-private/build9-30-profile/` and `reports-private/build9-60-profile/`, including actual-present traces, GPU/CPU CSVs, route hashes, logs, images and lease cleanup receipts. Asset/model hashes and build tool/dependency versions are in the local manifests. No game data or captures are published in Git.

## Local validation and remaining gates

118 Python tests, 13 native CTests, native touch/asset checks, Metal descriptor readback, and abrupt-exit profiling recovery passed. A fresh 18-patch source reconstruction matches Build 9. Both explicit FPS modes passed the Mac progression scenarios: 98/98 checkpoints including both full-route endings; 97 Lua chunks with zero failures. Headless accelerated tests do not prove physical timing or input acceptance.

The physical USE report remains open. Matching scene captures, real touch/controller/microphone input, lifecycle/audio interruption/Low Power Mode behavior, complete ending and reboot/offline launch remain open. No 60-FPS default, alpha tag or accepted-performance status is justified by these pilots.


## Archived trial

The optional [lighting experiment](../experiments/README.md) was built as Build 10, signed, installed and launched. Its short pilot also ended after background suspension. No controlled gain or matching-image acceptance was established, so the normal source recipe remains the 18-patch Build 9 baseline. Build 10 was the last temporary device installation; Build 9's signed IPA remains available locally. No reinstall was performed after stopping performance work.
