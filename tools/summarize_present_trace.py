#!/usr/bin/env python3
"""Summarize opt-in VK_GOOGLE_display_timing CSV; never infer display FPS from submissions.

Intervals end in their assigned window. Lifecycle/swapchain boundaries and the
first observation of every segment contribute no interval. Warmup is excluded
at the start of EACH segment; report it explicitly when comparing runs.
"""
import argparse
import csv
import json
import math
from pathlib import Path

FIELDS = ["schema_version", "segment", "segment_reason", "present_id", "actual_present_ns", "interval_ns",
          "desired_present_ns", "earliest_present_ns", "present_margin_ns", "poll_monotonic_ns",
          "surface_width", "surface_height", "unobserved_ids_before"]
NORMAL_RESETS = {"initial", "swapchain", "lifecycle", "background", "foreground", "present_id_wrap"}
MAX_ROWS = 2_000_000


class TraceError(ValueError):
    pass


def _stats(intervals, target_fps, tolerance_ms):
    values = sorted(intervals)
    period = 1_000_000_000 / target_fps
    def percentile(fraction):
        return values[max(0, math.ceil(len(values) * fraction) - 1)] / 1e6 if values else None
    elapsed = sum(values)
    return {
        "intervals": len(values), "observed_interval_seconds": elapsed / 1e9,
        "actual_display_fps": len(values) * 1e9 / elapsed if elapsed else None,
        "p50_ms": percentile(.5), "p95_ms": percentile(.95), "p99_ms": percentile(.99),
        "max_ms": values[-1] / 1e6 if values else None,
        "overshoot_count": sum(x > period + tolerance_ms * 1e6 for x in values),
        "at_least_two_periods_count": sum(x >= period * 2 for x in values),
        "over_100ms_count": sum(x > 100_000_000 for x in values),
    }


def summarize(path, target_fps=30.0, tolerance_ms=.5, warmup_seconds=0.0, window_seconds=60.0):
    if not all(math.isfinite(x) for x in (target_fps, tolerance_ms, warmup_seconds, window_seconds)):
        raise TraceError("parameters must be finite")
    if target_fps <= 0 or tolerance_ms < 0 or warmup_seconds < 0 or window_seconds <= 0:
        raise TraceError("positive FPS/window and nonnegative tolerance/warmup required")
    warmup_ns, window_ns = round(warmup_seconds * 1e9), round(window_seconds * 1e9)
    if window_ns < 1:
        raise TraceError("window must be at least one nanosecond")
    segments, windows, eligible = [], [], []
    duplicate_rows = missing_ids = warmup_intervals = 0
    previous = None
    current = None
    with Path(path).open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != FIELDS:
            raise TraceError("unsupported/missing CSV header")
        for line, raw in enumerate(reader, 2):
            if line > MAX_ROWS + 1:
                raise TraceError("trace exceeds parser row bound")
            if None in raw or any(value is None or len(value) > 128 for value in raw.values()):
                raise TraceError(f"line {line}: truncated or oversized row")
            try:
                row = {key: int(value) if key != "segment_reason" else value for key, value in raw.items()}
            except ValueError as error:
                raise TraceError(f"line {line}: invalid integer") from error
            if any(value < 0 or value > 2**64 - 1 for key, value in row.items() if key != "segment_reason"):
                raise TraceError(f"line {line}: integer outside uint64")
            if (row["schema_version"] != 1 or not row["segment"] or
                not 0 < row["present_id"] < 2**32 or not row["actual_present_ns"] or
                not row["surface_width"] or not row["surface_height"] or not row["segment_reason"]):
                raise TraceError(f"line {line}: invalid version, ID, timestamp or extent")
            if previous and row["segment"] < previous["segment"]:
                raise TraceError(f"line {line}: segment regressed")
            if previous and row["segment"] == previous["segment"]:
                if row["present_id"] == previous["present_id"]:
                    if row != previous:
                        raise TraceError(f"line {line}: conflicting duplicate ID")
                    duplicate_rows += 1
                    continue
                if (row["present_id"] != previous["present_id"] + 1 or
                    row["actual_present_ns"] <= previous["actual_present_ns"]):
                    raise TraceError(f"line {line}: ID/time discontinuity requires a new segment")
                if row["interval_ns"] != row["actual_present_ns"] - previous["actual_present_ns"]:
                    raise TraceError(f"line {line}: interval does not match actual timestamps")
                if (row["segment_reason"] != previous["segment_reason"] or row["unobserved_ids_before"] or
                    (row["surface_width"], row["surface_height"]) != current["surface"]):
                    raise TraceError(f"line {line}: changed segment metadata requires a new segment")
            else:
                if row["interval_ns"]:
                    raise TraceError(f"line {line}: first segment observation must have interval zero")
                current = {"segment": row["segment"], "reason": row["segment_reason"],
                           "surface": (row["surface_width"], row["surface_height"]),
                           "first_actual_ns": row["actual_present_ns"], "observations": 0,
                           "intervals": [], "windows": {}}
                segments.append(current)
            missing_ids += row["unobserved_ids_before"]
            current["observations"] += 1
            current["last_actual_ns"] = row["actual_present_ns"]
            if row["interval_ns"]:
                origin = current["first_actual_ns"] + warmup_ns
                if previous["actual_present_ns"] >= origin:
                    interval = row["interval_ns"]
                    eligible.append(interval)
                    current["intervals"].append(interval)
                    index = (row["actual_present_ns"] - origin) // window_ns
                    current["windows"].setdefault(index, []).append(interval)
                else:
                    warmup_intervals += 1
            previous = row
    for segment in segments:
        origin = segment["first_actual_ns"] + warmup_ns
        for index, intervals in sorted(segment.pop("windows").items()):
            start, end = origin + index * window_ns, origin + (index + 1) * window_ns
            windows.append({"segment": segment["segment"], "window_index": index,
                            "start_actual_ns": start, "end_actual_ns": end,
                            "partial_end": segment["last_actual_ns"] < end,
                            **_stats(intervals, target_fps, tolerance_ms)})
        segment.update(_stats(segment.pop("intervals"), target_fps, tolerance_ms))
    return {
        "schema_version": 1, "source": "VK_GOOGLE_display_timing.actualPresentTime",
        "input": str(path), "target_fps": target_fps, "overshoot_tolerance_ms": tolerance_ms,
        "overshoot_rule": "interval_ms > 1000 / target_fps + tolerance_ms",
        "warmup_seconds_per_segment": warmup_seconds, "window_seconds": window_seconds,
        "window_assignment": "interval ending in window; intervals never cross a segment boundary",
        "quantile_method": "nearest rank", "duplicate_rows_skipped": duplicate_rows,
        "unobserved_present_ids": missing_ids, "warmup_intervals_excluded": warmup_intervals,
        "trace_discontinuity": bool(missing_ids or any(s["reason"] not in NORMAL_RESETS for s in segments)),
        "observations": sum(s["observations"] for s in segments),
        "measurement_available": bool(eligible), "summary": _stats(eligible, target_fps, tolerance_ms),
        "segments": segments, "windows": windows,
        "limits": ["Actual observations only; unreported presentations cannot be reconstructed.",
                   "Intervals excluded by reset/warmup are not evidence of sustained performance.",
                   "A partial last window may represent an unfinished run; check renderer write_ok log.",
                   "This timing summary does not establish foreground state, gameplay coverage, thermal stability or visual correctness."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-fps", type=float, default=30)
    parser.add_argument("--overshoot-tolerance-ms", type=float, default=.5)
    parser.add_argument("--warmup-seconds", type=float, default=0)
    parser.add_argument("--window-seconds", type=float, default=60)
    args = parser.parse_args()
    try:
        result = summarize(args.trace, args.target_fps, args.overshoot_tolerance_ms, args.warmup_seconds, args.window_seconds)
    except (OSError, UnicodeError, TraceError, csv.Error) as error:
        parser.exit(2, f"presentation trace: {error}\n")
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if result["measurement_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
