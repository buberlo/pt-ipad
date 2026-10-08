#!/usr/bin/env python3
"""Headless native-Mac mirror beam/shadow A/B using the user's local game assets.

Requires Pillow and NumPy for read-only pixel measurements (available in the
bundled workspace Python). The diagnostic door is an existing original mesh;
it is placed only by this test script, never by normal gameplay.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MODES = {
    "baseline": ("0", "0", "1", False),
    "visibility_only": ("1", "0", "1", False),
    "fixed": (None, None, "1", False),
    "unshadowed": (None, None, "0", False),
    "fixed_blocker": (None, None, "1", True),
    "unshadowed_blocker": (None, None, "0", True),
}


def route(blocker):
    source = ROOT / "upstream/pt-pc/tests/walkthrough"
    lines = (source / "start.txt").read_text().splitlines()
    bathroom = (source / "f060.txt").read_text().splitlines()
    lines += bathroom[:bathroom.index("fent Locator_mirror_pos") + 1]
    lines = [line for line in lines if line and not line.startswith(("#", "sshot"))]
    lines += ["swait 30", "sfree", "shandylight 1", "sev -1",
              "scamfile -3.4 0.2 5.2 -1.28 0.01 0.7 70"]
    if blocker:
        lines += ["smodel /Assets/sh/environ/object/shsb/house/shsb_hous001/scenes/shsb_hous001_door002.fmdl -4.0 -1.4 5.65 90 0 0 1"]
    lines += ["swait 60", "sshot capture.png", "swait 2", "slog", "squit"]
    return "".join("700 " + line + "\n" for line in lines)


def compare(first, second):
    a, b = [np.asarray(Image.open(p).convert("RGB"), dtype=np.float64) for p in (first, second)]
    if a.shape != (720, 1280, 3) or b.shape != a.shape:
        raise ValueError("unexpected capture extent")
    # Rectangular receiver wall, outside the mirror and the diagnostic door.
    region = np.s_[100:620, 0:200, :]
    delta = (b[region] - a[region]).mean(axis=2)
    return {"roi_xyxy": [0, 100, 200, 620], "first_rgb_mean_255": float(a[region].mean()),
            "second_rgb_mean_255": float(b[region].mean()), "mean_change_255": float(delta.mean()),
            "pixels_brighter_over_10": int((delta > 10).sum()),
            "pixels_darker_over_10": int((delta < -10).sum()),
            "max_change_255": float(delta.max()), "min_change_255": float(delta.min())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=ROOT / "build/macos-arm64/pt.app/Contents/MacOS/pt")
    parser.add_argument("--game", type=Path, default=ROOT / "assets-private/CUSA01127")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exe, game, output = [path.resolve() for path in (args.exe, args.game, args.output)]
    output.mkdir(parents=True, exist_ok=False)
    exe_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
    records = []
    for mode, (primary, clip, shadow, blocker) in MODES.items():
        work = output / mode
        work.mkdir()
        (work / "route.txt").write_text(route(blocker))
        argv = [str(exe), "--game", str(game), "--headless", "--no-save", "--no-mods", "--frames", "14000",
                "--demo-rate", "20", "--input-script", str(work / "route.txt"), "--width", "1280", "--height", "720",
                "--seed", "2014", "--start-floor", "f040", "--shot-warmup", "30", "--shot-settle",
                "--settings", str(work / "pt.ini"), "--audio-offline"]
        env = {key: value for key, value in os.environ.items() if not key.startswith("PT_")}
        env.update(PT_HEADLESS_ONLY="1", PT_SYSTEM_LANGUAGE="en-US", PT_MIRROR_TRACE="1", PT_RENDER_TRACE="1",
                   PT_MIRROR_LIGHT_SHADOW=shadow)
        if primary is not None:
            env["PT_MIRROR_LIGHT_PRIMARY"] = primary
        if clip is not None:
            env["PT_MIRROR_LIGHT_CLIP"] = clip
        record = {"mode": mode, "argv": argv, "exe_sha256": exe_hash,
                  "environment": {k: v for k, v in env.items() if k.startswith("PT_")}, "diagnostic_blocker": blocker}
        (work / "invocation.json").write_text(json.dumps(record, indent=2))
        start = time.monotonic()
        with (work / "console.log").open("w") as console:
            run = subprocess.run(argv, cwd=work, env=env, stdout=console, stderr=subprocess.STDOUT, timeout=240)
        log = (work / "pt.log").read_text(errors="replace")
        record.update(exit_code=run.returncode, elapsed_seconds=time.monotonic() - start,
                      render_errors=re.findall(r"^.*\]\s+error\s.*$", log, re.MULTILINE),
                      mirror_light_on="mirror trace: on" in log,
                      screenshot_records=re.findall(r"^.*screenshot ev.*$", log, re.MULTILINE),
                      capture_sha256=hashlib.sha256((work / "capture.png").read_bytes()).hexdigest())
        (work / "result.json").write_text(json.dumps(record, indent=2))
        records.append(record)
        if run.returncode or record["render_errors"] or not record["mirror_light_on"]:
            raise RuntimeError(f"{mode}: invalid render; inspect private logs")
        if hashlib.sha256(exe.read_bytes()).hexdigest() != exe_hash:
            raise RuntimeError("executable changed during the comparison")
        print(f"{mode}: exit 0; captured", flush=True)
    screenshot = lambda mode: output / mode / "capture.png"
    metrics = {
        "restored_beam": compare(screenshot("baseline"), screenshot("fixed")),
        "visibility_only": compare(screenshot("baseline"), screenshot("visibility_only")),
        "unobstructed_shadow_control": compare(screenshot("fixed"), screenshot("unshadowed")),
        "cast_shadow_control": compare(screenshot("fixed_blocker"), screenshot("unshadowed_blocker")),
    }
    result = {"modes": records, "metrics": metrics,
              "limits": "Native Mac raster functional comparison; no original PS4 brightness/parity reference or iPad validation."}
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    if metrics["restored_beam"]["pixels_brighter_over_10"] < 1000 or metrics["cast_shadow_control"]["pixels_brighter_over_10"] < 1000:
        raise RuntimeError("expected beam/shadow receiver signal missing; inspect captures")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
