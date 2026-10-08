# M2 1080p / 60 FPS qualification

The target is 1920 × 1080 internal rendering at 60 **actually presented** frames per second, with original graphics parameters and game speed. This target is not yet accepted. [Current pilot results](PERFORMANCE_60FPS_REPORT.md) record the interruptions and GPU/thermal findings. Build 9 introduces the comparison controls; it does not claim an optimized renderer. The source remains the pinned reconstructed C++ P.T. port with original assets.

## Frame-rate controls

On iPad, pause → Settings → Display → Frame rate offers 30 FPS and 60 FPS. The selection is persisted in `display.fps_limit`. New settings default to 30 during qualification; an existing 60 selection survives startup. The internal 1080p render target and graphics settings are unchanged.

`--fps-limit 30` or `--fps-limit 60` overrides the effective presentation cap for that launch only. Other values fail with exit 2. During an override the settings row displays the effective value and cannot overwrite the stored selection. Restart normally to edit it. This parameter does not change the simulation tick, demo rate or original animation timing. GPU profiling uses `PT_GPU_LIVE_CSV`; final qualification leaves it unset.

The 60 default must only be introduced after device acceptance. The unresolved physical USE-button report remains separate from timing results.

## Repeatable local and device checks

```sh
python3 tools/prepare_source.py --output build/reconstructed
python3 tools/build_native.py macos --tests --build-number 9
python3 tools/build_native.py ios --build-number 9 --moltenvk-root build/alpha-MoltenVK
python3 tools/validate_local.py --assets /absolute/path/to/your/extracted-assets
```

Follow [REBUILD.md](REBUILD.md) for dependency preparation, original-asset import, signing with your own profile and installation. The pinned source plus 18 ordered patches reconstructs the Build 9 source. Signed artifacts, original assets, model downloads and raw reports stay outside Git.

The bounded route helper uses isolated settings, saves disabled, the same seed 1, route, assets and demo rate 1 for both caps:

```sh
python3 tools/device_walkthrough.py --device YOUR_UDID --session-id YOUR_SESSION \
  --fps-limit 60 --profile --seconds 480 --output reports-private/profile-60
python3 tools/device_walkthrough.py --device YOUR_UDID --session-id YOUR_SESSION \
  --fps-limit 30 --profile --seconds 480 --output reports-private/profile-30
```

Profiling permits 120–1800 seconds for bounded pilots; final runs without `--profile` require 1200–1800 seconds.

The helper acquires the shared lease and refuses existing game sessions. `--profile` enables the buffered CPU tick and GPU pass CSVs, flushed every 60 rows so external termination preserves completed batches. Omit it for final low-overhead measurement; actual display timestamps and thermal/Low Power Mode logs remain available. A route may finish or fail early; requested duration is never proof of 20 minutes of active gameplay. Synthetic voice input is explicitly not real microphone acceptance.

Before interpreting a run, record signed executable, source, manifest, asset, model and route hashes; effective graphics settings; device/OS; thermal state; Low Power Mode; foreground and matching image evidence. Compare corridor, the whole bathroom, mirror/flashlight, encounter and microphone work. Keep loading, menus and background time separate. CPU/GPU diagnostics identify the bottleneck; every optimization needs a matched-scene, single-change comparison and visual regression review.

## Timing gate

Provide a reviewed window specification using driver `segment` and actual `present_id`, rather than mixing runtime log seconds with the driver's clock:

```json
{"schema":1,"windows":[
  {"name":"active-play","role":"gameplay","segment":2,"first_present_id":1000,"last_present_id":73000},
  {"name":"last-five-minutes","role":"tail","segment":2,"first_present_id":55000,"last_present_id":73000},
  {"name":"corridor","role":"scene","segment":2,"first_present_id":1000,"last_present_id":8200}
]}
```

These IDs are illustrative, not measured evidence. Supply all five scene windows named `corridor`, `bathroom`, `mirror_flashlight`, `encounter`, `microphone`, each within the reviewed active-play window. The main window needs at least 1200 seconds after warmup; each scene at least 120 seconds; the tail must cover the final 300 seconds. If a complete scene route is shorter, extend representative play rather than counting menus or waiting screens.

```sh
python3 tools/qualify_60fps.py reports-private/final/present.csv \
  --windows reports-private/final/windows.json --output reports-private/final/timing-gate.json
```

Every window must reach average ≥59.9 displayed FPS, p95 and p99 ≤17.2 ms, and no more than 0.1% intervals above 25 ms. Maximum interval and intervals above 100 ms are also reported. Missing presentations, absent endpoints and incomplete coverage cannot pass. Output `timing_passed` concerns timing only: `accepted` remains false until render extent, foreground/scene association, unchanged images, warmup, device identity and thermal/power evidence are separately reviewed. Swapchain dimensions are not the internal render dimensions.

After any relevant change, rebuild, sign and repeat affected checks on the same final candidate. Test Low Power Mode separately, plus resume and audio interruption. The full alpha ending, real touch/microphone/controller and offline/reboot checks remain additional gates.
