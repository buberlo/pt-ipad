#!/usr/bin/env python3
"""Stage and verify P.T. assets using the separately built upstream PKG helper.

Only the known US asset set is accepted. The input PKG is hashed before and after
extraction. A complete staged directory is published by rename; saves stay outside.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import uuid

from inspect_pt_package import PackageError, checked_range, inspect_package

ROOT = Path(__file__).resolve().parents[1]
KNOWN_ASSETS = {
    "chunk1.psarc": (421978112, "f3cf67ef215065df01619fb0b3fd03fba7f465752ac4107e485dd0ea9dda41ef"),
    "texture.qar": (892291044, "436bb79d9d47df685423a9afaed89a8be5e88a938347dd18e63e94398c6ed9b0"),
    "pathid_list_ps4.bin": (93248, "6b4641bafe18f785229500454c5d44cba04cc1302fd8e187c53047a04d2633d0"),
}
MANIFEST = "import-manifest.json"


class ImportError(ValueError):
    pass


class ImportCancelled(Exception):
    pass


def no_symlink_path(path: Path) -> Path:
    """Do not resolve symlinks away before checking path ancestry."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            if stat.S_ISLNK(part.lstat().st_mode):
                raise ImportError(f"Symbolic links are refused: {part}")
        except FileNotFoundError:
            continue
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ImportError(f"Not a regular file: {path.name}")
        while chunk := source.read(4 * 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ImportError(f"File changed during hashing: {path.name}")
    return digest.hexdigest()


def archive_metadata(directory: Path) -> dict:
    psarc = directory / "chunk1.psarc"
    with psarc.open("rb") as source:
        header = source.read(32)
    if len(header) != 32:
        raise ImportError("Truncated PSARC header")
    magic, version, compression, toc, stride, count, block, flags = struct.unpack(">4sI4s5I", header)
    if magic != b"PSAR" or compression != b"zlib" or stride != 30 or not 1 <= count <= 100000:
        raise ImportError("Unsupported PSARC header")
    if toc < 32 + stride * count or not block or block & (block - 1):
        raise ImportError("Invalid PSARC table/block size")
    checked_range(0, toc, psarc.stat().st_size, "PSARC table")
    qar = directory / "texture.qar"
    with qar.open("rb") as source:
        if qar.stat().st_size < 36:
            raise ImportError("Truncated QAR footer")
        source.seek(-36, 2)
        footer = source.read(36)
        qar_count, qar_flags, qar_magic, table16 = struct.unpack_from("<IHHI", footer, 16)
        if qar_magic != 0x7161 or not 1 <= qar_count <= 1000000:
            raise ImportError("Invalid QAR footer")
        table_offset = table16 << 4
        checked_range(table_offset, qar_count * 16, qar.stat().st_size - 36, "QAR table")
        source.seek(table_offset)
        for _ in range(qar_count):
            raw = source.read(16)
            if len(raw) != 16:
                raise ImportError("Truncated QAR entry")
            _, start16, length = struct.unpack("<QII", raw)
            checked_range(start16 << 4, length, table_offset, "QAR entry")
    pathlist = directory / "pathid_list_ps4.bin"
    if not 32 <= pathlist.stat().st_size <= 16 * 1024 * 1024:
        raise ImportError("Path list size outside bounds")
    data = pathlist.read_bytes()
    path_version, path_count, dirs, names = struct.unpack_from("<4I", data)
    if path_version != 1 or not 1 <= path_count <= 100000 or not dirs or not names:
        raise ImportError("Invalid path list header")
    align16 = lambda n: (n + 15) & ~15
    records = align16(32 + path_count * 8)
    dir_offsets = align16(records + path_count * 4)
    name_offsets = align16(dir_offsets + dirs * 4)
    strings = align16(name_offsets + names * 4)
    checked_range(0, strings, len(data), "Path list tables")
    for i in range(path_count):
        record = struct.unpack_from("<I", data, records + i * 4)[0]
        if (record & 0xFFFF) >= names or (record >> 20) >= dirs:
            raise ImportError("Path list record index outside tables")
    for base, count_offsets in ((dir_offsets, dirs), (name_offsets, names)):
        for i in range(count_offsets):
            off = strings + struct.unpack_from("<I", data, base + i * 4)[0]
            if off >= len(data) or data.find(b"\0", off) < 0:
                raise ImportError("Path list string outside table")
    if b"pt14_" not in data[strings:]:
        raise ImportError("Path list lacks P.T. level identity")
    return {"psarc": {"version": hex(version), "toc_entries": count, "block_bytes": block,
                       "archive_flags": flags},
            "qar": {"entries": qar_count, "flags": qar_flags},
            "pathlist": {"version": path_version, "paths": path_count, "directories": dirs, "names": names}}


def validate_assets(directory: Path, expected=KNOWN_ASSETS) -> dict:
    allowed = set(expected) | {"source.txt"}
    if any(p.name not in allowed for p in directory.iterdir()):
        raise ImportError("Extractor wrote an unexpected path")
    files = {}
    for name, (length, expected_hash) in expected.items():
        if Path(name).name != name or name in (".", "..") or ":" in name or "\\" in name:
            raise ImportError("Unsafe expected asset name")
        path = no_symlink_path(directory / name)
        if not path.is_file() or path.stat().st_size != length:
            raise ImportError(f"Missing or wrong-sized asset: {name}")
        digest = sha256_file(path)
        if digest != expected_hash:
            raise ImportError(f"SHA-256 mismatch: {name}")
        files[name] = {"bytes": length, "sha256": digest, "matches_known_us_data": True}
    source = directory / "source.txt"
    if source.exists():
        no_symlink_path(source)
        if not source.is_file() or source.stat().st_size > 65536:
            raise ImportError("Invalid source metadata")
    return files


def run_extractor(command: list[str], package: Path, stage: Path) -> None:
    process = subprocess.Popen([*command, str(package), str(stage)], start_new_session=True)
    try:
        while True:
            try:
                result = process.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if shutil.disk_usage(stage).free < 512 * 1024 * 1024:
                    raise ImportError("Free space fell below the 512MiB reserve during extraction")
        if result != 0:
            raise ImportError("Upstream extraction helper refused the package; see its diagnostic")
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        raise


def publish_stage(stage: Path, destination: Path, replace: bool = False) -> None:
    no_symlink_path(stage)
    no_symlink_path(destination)
    backup = destination.with_name(f".pt-assets-old-{uuid.uuid4().hex}")
    previous = destination.exists()
    if previous:
        if not replace:
            raise ImportError("Destination exists; use --replace only for a verified prior import")
        marker = destination / MANIFEST
        no_symlink_path(marker)
        if not marker.is_file() or marker.stat().st_size > 1024 * 1024:
            raise ImportError("Refusing to replace an unowned destination")
        if json.loads(marker.read_text()).get("schema") != "pt-ipad-assets-v1":
            raise ImportError("Refusing to replace an unowned destination")
        if any(p.name not in set(KNOWN_ASSETS) | {"source.txt", MANIFEST} for p in destination.iterdir()):
            raise ImportError("Existing destination contains unrelated files or saves")
    old_moved = new_moved = False
    # A signal between rename() returning and the bookkeeping assignment must
    # not hide a completed rename from rollback. Defer signal exceptions over
    # this tiny transaction and check cancellation before its commit point.
    pending_signals, handlers = [], {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, lambda s, f: pending_signals.append(s))
    try:
        if previous:
            os.rename(destination, backup)
            old_moved = True
        if pending_signals:
            raise ImportCancelled("cancelled before asset publication")
        os.rename(stage, destination)
        new_moved = True
        if pending_signals:
            raise ImportCancelled("cancelled during asset publication")
    except BaseException:
        if new_moved:
            os.rename(destination, stage)
        if old_moved:
            os.rename(backup, destination)
        raise
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    if old_moved:
        # Cleanup follows the completed directory commit. A leftover backup is safe.
        shutil.rmtree(backup)


def import_assets(package: Path, private_root: Path, command: list[str], *,
                  replace=False, expected_package_sha256=None, report_path=None,
                  save_root=None, extractor=run_extractor, expected=KNOWN_ASSETS,
                  metadata_reader=archive_metadata) -> dict:
    package = no_symlink_path(package)
    private_root = no_symlink_path(private_root)
    save_root = no_symlink_path(save_root or ROOT / ".local" / "user-data")
    if private_root == save_root or private_root in save_root.parents or save_root in private_root.parents:
        raise ImportError("Asset and save roots must be separate")
    if private_root == package or private_root in package.parents:
        raise ImportError("Source package must stay outside the asset root")
    destination = private_root / "CUSA01127"
    if destination.exists() and not replace:
        raise ImportError("Destination already exists")
    before = inspect_package(package, with_sha256=True)
    if before["sfo"].get("TITLE_ID") != "CUSA01127" or before["sfo"].get("TITLE") != "P.T.":
        raise ImportError("This importer requires the verified US P.T. package")
    if expected_package_sha256 and before["sha256"] != expected_package_sha256:
        raise ImportError("Source PKG SHA-256 differs from expected value")
    private_root.mkdir(parents=True, exist_ok=True)
    required_space = sum(length for length, _ in expected.values()) + 512 * 1024 * 1024
    if shutil.disk_usage(private_root).free < required_space:
        raise ImportError(f"Insufficient free space: need at least {required_space} bytes")
    stage = Path(tempfile.mkdtemp(prefix=".pt-assets-stage-", dir=private_root))
    try:
        extractor(command, package, stage)
        assets = validate_assets(stage, expected)
        metadata = metadata_reader(stage)
        after_hash = sha256_file(package)
        if after_hash != before["sha256"]:
            raise ImportError("Source package changed during extraction")
        report = {"schema": "pt-ipad-assets-v1", "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_package": before, "source_sha256_after": after_hash,
                  "source_unchanged": True, "destination": str(destination),
                  "save_root": str(save_root), "assets": assets, "metadata": metadata,
                  "evidence": {"extracted": True, "hash_verified": True,
                               "runtime_verified": False, "device_verified": False}}
        (stage / MANIFEST).write_text(json.dumps(report, indent=2) + "\n")
        if report_path:
            report_path = no_symlink_path(Path(report_path))
            if report_path.exists() or private_root == report_path or private_root in report_path.parents:
                raise ImportError("Report must be a new path outside the asset root")
            report_path.parent.mkdir(parents=True, exist_ok=True)
        publish_stage(stage, destination, replace)
        if report_path:
            with report_path.open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2)
                output.write("\n")
        return report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--extractor", type=Path, required=True, help="upstream PT.PkgExtract executable or DLL")
    parser.add_argument("--dotnet", type=Path, help="dotnet executable, required for a DLL helper")
    parser.add_argument("--private-root", type=Path, default=ROOT / "assets-private")
    parser.add_argument("--save-root", type=Path, default=ROOT / ".local" / "user-data")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--expected-package-sha256")
    args = parser.parse_args(argv)
    command = [str(args.extractor.resolve(strict=True))]
    if args.extractor.suffix.lower() == ".dll":
        if not args.dotnet:
            parser.error("--dotnet is required when --extractor is a DLL")
        command.insert(0, str(args.dotnet.resolve(strict=True)))
    def cancelled(signum, frame):
        raise ImportCancelled(f"cancelled by signal {signum}")
    old_handlers = {s: signal.signal(s, cancelled) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        report = import_assets(args.package, args.private_root, command, replace=args.replace,
                               expected_package_sha256=args.expected_package_sha256,
                               report_path=args.report, save_root=args.save_root)
        print(f"Verified {len(report['assets'])} assets at {report['destination']}; runtime validation remains open.")
        return 0
    except (ImportCancelled, KeyboardInterrupt):
        print("Asset import cancelled; incomplete staging removed.", file=sys.stderr)
        return 130
    except (OSError, ValueError, PackageError, struct.error) as exc:
        print(f"Asset import refused: {exc}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
