#!/usr/bin/env python3
"""Check the parent Git index for payloads, workflow files and source-pin drift."""
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".pkg", ".psarc", ".qar", ".self", ".sprx", ".ipa", ".p12", ".mobileprovision", ".mp4", ".mov"}
FORBIDDEN_ROOTS = {"build", ".local", "assets-private", "artifacts", "reports-private"}


def check():
    pin = json.loads(subprocess.check_output(["git", "show", ":source-lock.json"], cwd=ROOT))["pt_pc"]["commit"]
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT).decode().split("\0")
    problems = []
    source_found = False
    count = 0
    for entry in entries:
        if not entry:
            continue
        header, name = entry.split("\t", 1)
        mode, blob, stage = header.split()
        p = PurePosixPath(name)
        count += 1
        if stage != "0":
            problems.append(f"unmerged index entry: {name}")
        if mode == "160000":
            if name != "upstream/pt-pc" or blob != pin:
                problems.append(f"unapproved or drifting source gitlink: {name} {blob}")
            source_found |= name == "upstream/pt-pc" and blob == pin
            continue
        if p.parts[0] in FORBIDDEN_ROOTS or p.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"private/generated payload in index: {name}")
        if name.startswith(".github/workflows/") or p.name == ".env" or p.name.startswith(".env.") and p.name != ".env.example":
            problems.append(f"workflow or environment file in index: {name}")
        if p.name in {"eboot.bin", "pathid_list_ps4.bin"}:
            problems.append(f"game payload in index: {name}")
        size = int(subprocess.check_output(["git", "cat-file", "-s", blob], cwd=ROOT))
        if size > 2 * 1024 * 1024:
            problems.append(f"review required for large parent file: {name}")
    if not source_found:
        problems.append("pinned upstream gitlink is missing from index")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"Parent index checked: {count} paths; pinned source; no recognized game payloads or workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
