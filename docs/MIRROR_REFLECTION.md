# Mirror beam correction and native Mac evidence

Patch `0008-mirror-reflected-light.patch` restores the existing bathroom mirror spotlight to the main raster view and clips its shadow casters at the mirror plane. The virtual spotlight sits behind the mirror: geometry behind that plane must not block the outgoing reflected beam, while objects in the room still cast shadows. A 2 mm plane offset avoids the reflective surface shadowing itself. Other lights retain a zero/disabled clip plane; GPU buffer layout and feature requirements are unchanged.

The source already generated `MirrorLight` with a reflected direction and shadows, but assigned `hidden_views = 1`, excluding the main view. Clearing that mask alone did not restore the receiver-wall beam because the wall behind the mirror occluded its virtual source. The upstream report describes missing reflected flashlight illumination and shadows on the bathroom wall; it remains open as of 2026-10-08: [pt-pc issue #10](https://github.com/LoreanXavier/pt-pc/issues/10).

Both corrections are enabled by default. For controlled comparisons, `PT_MIRROR_LIGHT_PRIMARY=0` restores the main-view exclusion; `PT_MIRROR_LIGHT_CLIP=0` disables the mirror-plane clipping. Set both to `0` for the prior behavior. The existing `PT_MIRROR_LIGHT_SHADOW=0` supplies the unshadowed control. These switches are diagnostics, not player settings.

## Reproduction

Use a built native macOS executable, the locally imported CUSA01127 assets, and Python with Pillow and NumPy (the bundled workspace Python provides them):

```sh
python3 tools/verify_mirror_reflection.py --output reports-private/mirror-validation-new
```

The tool runs six isolated headless comparisons, using the pinned upstream f060 walkthrough to reach the bathroom, 1280×720 rendering, seed 2014, 30 render warmup frames, fixed EV −1, and one camera pose. It disables saves and mods and verifies that the executable hash stays constant. It records process results, settings, camera/exposure records, screenshot hashes and receiver-pixel metrics. Images and game data remain private.

The shadow control places the existing original door mesh at file coordinates `(-4.0, -1.4, 5.65)`, yaw 90°, only within this diagnostic script. This added occluder is **not** part of normal gameplay and is not represented as an original PS4 scene. It makes the expected cast shadow measurable on the wall outside the mirror. The unmodified scene supplies the beam and unobstructed-shadow controls.

## Verified result

All six final native Mac runs exited 0 without renderer error logs. All used executable SHA-256 `a53f6e84d72af4b8f30191089304a2149a2b088f858b93393b4e31bd8c8e9aec`; captured frame 2329 at world camera `(-3.394, 1.600, 23.300)`, yaw 118.67°, pitch 0.39°, EV −1, exposure 0.022614. The changed shadow shader compiled and passed `spirv-val --target-env vulkan1.3`.

Measurements below use the receiver-wall rectangle `(0,100)–(200,620)`, outside the mirror and diagnostic door, in unmodified 8-bit RGB screenshots. Values are RGB averages, not linear luminance or radiometric measurements.

| Controlled comparison | Result |
| --- | --- |
| Prior behavior → corrected defaults | 94,181 receiver pixels brighten by more than 10/255; mean rises from 0.083 to 68.411/255 |
| Prior behavior → visibility mask only | Receiver pixels are identical: the mask change alone is insufficient |
| Corrected default → shadow disabled, no blocker | No receiver pixels differ by more than 10/255; mean difference is 0.00061/255 |
| Corrected default → shadow disabled, diagnostic blocker present | 18,772 receiver pixels brighten by more than 10/255 when the shadow is disabled; receiver mean rises from 54.544 to 68.360/255 |

Private evidence: `reports-private/mirror-validation-final/summary.json`, per-mode `capture.png`, `pt.log`, and invocation/result records. Earlier four-pose experiments under `reports-private/mirror-ab/` also showed three poses where no reflected spotlight was generated producing pixel-identical baseline/fixed screenshots.

This establishes a reflected raster beam and retained room-side cast shadows on native Apple Silicon macOS. It does **not** establish PS4 brightness, edge, aperture or full visual parity: issue #10 provides a textual description, and no matched original PS4 capture was available. Physical iPad rendering of this correction remains to be checked. The optional desktop ray-query shadow path has not been adapted or validated for this clipping plane; the native iPad route uses raster shadows.
