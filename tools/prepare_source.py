#!/usr/bin/env python3
"""Reconstruct the pinned engine and patch series without discarding local edits."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def source_state(path):
    names = run("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", cwd=path).split("\0")
    h = hashlib.sha256()
    for name in sorted(set(names)):
        if not name:
            continue
        f = path / name
        h.update(name.encode() + b"\0")
        if f.is_symlink():
            h.update(b"symlink:" + str(f.readlink()).encode())
        elif f.is_file():
            h.update(hashlib.sha256(f.read_bytes()).digest())
        else:
            h.update(b"missing")
    return h.hexdigest()


def prepare(destination):
    lock = json.loads((ROOT / "source-lock.json").read_text())
    pin = lock["pt_pc"]["commit"]
    upstream = ROOT / "upstream/pt-pc"
    if run("git", "rev-parse", "HEAD", cwd=upstream) != pin:
        raise ValueError("upstream HEAD differs from source-lock.json; initialize the pinned submodule")
    if run("git", "status", "--porcelain", cwd=upstream):
        raise ValueError("upstream has local changes; refusing to use an altered baseline")
    patches = []
    for line in (ROOT / "patches/series").read_text().splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if Path(name).name != name or not name.endswith(".patch"):
            raise ValueError(f"unsafe patch series entry: {name!r}")
        patch = ROOT / "patches" / name
        patches.append((patch, hashlib.sha256(patch.read_bytes()).hexdigest()))
    recipe = {"upstream": pin, "patches": [{"name": p.name, "sha256": h} for p, h in patches]}
    destination = destination.absolute()
    if destination.exists():
        marker = destination / ".git/pt-source.json"
        if marker.is_file():
            old = json.loads(marker.read_text())
            if old.get("recipe") == recipe and old.get("tree_sha256") == source_state(destination):
                print(f"Source already matches recipe: {destination}")
                return
        raise ValueError(f"preserving existing checkout at {destination}; choose a fresh --output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pt-source-", dir=destination.parent))
    try:
        # A shared object store avoids duplicating history and binary upstream resources.
        run("git", "clone", "--shared", "--no-checkout", str(upstream), str(staging))
        run("git", "checkout", "--detach", pin, cwd=staging)
        for patch, _ in patches:
            run("git", "apply", "--check", str(patch), cwd=staging)
            run("git", "apply", str(patch), cwd=staging)
        metadata = {"recipe": recipe, "tree_sha256": source_state(staging)}
        (staging / ".git/pt-source.json").write_text(json.dumps(metadata, indent=2) + "\n")
        staging.rename(destination)
        print(f"Prepared {pin} plus {len(patches)} patches: {destination}")
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/port-src")
    args = parser.parse_args()
    try:
        prepare(args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Source preparation failed: {error}\n")
