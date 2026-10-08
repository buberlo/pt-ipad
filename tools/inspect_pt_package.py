#!/usr/bin/env python3
"""Inspect bounded PS4 PKG/SFO/PFS metadata without extracting or executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

HEADER_SIZE = 0x1000
MAX_ENTRIES = 4096
MAX_SFO_SIZE = 1024 * 1024
MAX_SFO_ENTRIES = 1024


class PackageError(ValueError):
    pass


def checked_range(offset: int, length: int, total: int, label: str) -> None:
    if offset < 0 or length < 0 or offset > total or length > total - offset:
        raise PackageError(f"{label} is outside its container")


def parse_sfo(data: bytes) -> dict:
    if len(data) < 20 or data[:4] != b"\0PSF":
        raise PackageError("Invalid SFO header")
    _, version, keys, values, count = struct.unpack_from("<5I", data)
    if version != 0x101 or not 1 <= count <= MAX_SFO_ENTRIES:
        raise PackageError("Unsupported SFO version or entry count")
    if not 20 + count * 16 <= keys <= values <= len(data):
        raise PackageError("Invalid SFO table bounds")
    result = {}
    for i in range(count):
        key_offset, fmt, length, capacity, value_offset = struct.unpack_from(
            "<HHIII", data, 20 + i * 16)
        key_start = keys + key_offset
        if key_start >= values:
            raise PackageError("SFO key is outside key table")
        key_end = data.find(b"\0", key_start, values)
        if key_end < 0 or key_end == key_start:
            raise PackageError("Empty or unterminated SFO key")
        try:
            key = data[key_start:key_end].decode("ascii")
        except UnicodeError as exc:
            raise PackageError("Non-ASCII SFO key") from exc
        if key in result:
            raise PackageError("Duplicate SFO key")
        if length > capacity:
            raise PackageError("SFO value length exceeds capacity")
        checked_range(values + value_offset, capacity, len(data), "SFO value")
        raw = data[values + value_offset:values + value_offset + length]
        if fmt == 0x0404:
            if length != 4:
                raise PackageError("SFO integer is not four bytes")
            value = struct.unpack("<I", raw)[0]
        elif fmt == 0x0204:
            if not raw or raw[-1] != 0:
                raise PackageError("Unterminated SFO string")
            try:
                value = raw.rstrip(b"\0").decode("utf-8")
            except UnicodeError as exc:
                raise PackageError("Invalid UTF-8 SFO string") from exc
        elif fmt == 0x0004:
            value = {"binary_bytes": length}
        else:
            raise PackageError(f"Unsupported SFO value format {fmt:#x}")
        result[key] = value
    return result


def inspect_package(path: Path, with_sha256: bool = False) -> dict:
    path = Path(path).resolve(strict=True)
    if not stat.S_ISREG(path.stat().st_mode):
        raise PackageError("Input must be a regular file")
    with path.open("rb") as stream:
        initial = stream_stat = os.fstat(stream.fileno())
        if not stat.S_ISREG(stream_stat.st_mode):
            raise PackageError("Input must be a regular file")
        size = stream_stat.st_size

        def read(offset: int, length: int, label: str) -> bytes:
            checked_range(offset, length, size, label)
            stream.seek(offset)
            data = stream.read(length)
            if len(data) != length:
                raise PackageError(f"Short read: {label}")
            return data

        header = read(0, HEADER_SIZE, "PKG header")
        if header[:4] != b"\x7fCNT":
            raise PackageError("Not a PS4 PKG (wrong magic)")
        u32 = lambda off: struct.unpack_from(">I", header, off)[0]
        u64 = lambda off: struct.unpack_from(">Q", header, off)[0]
        if u64(0x430) != size:
            raise PackageError("PKG declared size differs from actual size")
        count, offset = u32(0x10), u32(0x18)
        if not 1 <= count <= MAX_ENTRIES or offset < HEADER_SIZE:
            raise PackageError("Invalid PKG entry table count or offset")
        table = read(offset, count * 32, "PKG entry table")
        entries, ids, sfo = [], set(), None
        for i in range(count):
            eid, _, flags1, flags2, start, length, _ = struct.unpack_from(">6IQ", table, i * 32)
            if eid in ids:
                raise PackageError("Duplicate PKG entry ID")
            ids.add(eid)
            checked_range(start, length, size, "PKG entry")
            entries.append({"id": f"0x{eid:04x}", "offset": start, "bytes": length,
                            "flags1": hex(flags1), "flags2": hex(flags2)})
            if eid == 0x1000:
                if flags1 & 0x80000000:
                    raise PackageError("SFO metadata is encrypted")
                if length > MAX_SFO_SIZE:
                    raise PackageError("SFO metadata exceeds bounded-read limit")
                sfo = parse_sfo(read(start, length, "SFO metadata"))
        if sfo is None:
            raise PackageError("PKG has no SFO metadata")
        if u32(0x404) != 1:
            raise PackageError("Expected one PFS image")
        pfs_start, pfs_size = u64(0x410), u64(0x418)
        checked_range(pfs_start, pfs_size, size, "PFS image")
        if pfs_start < HEADER_SIZE or pfs_size < 0x50:
            raise PackageError("Invalid PFS image bounds")
        pfs = read(pfs_start, 0x50, "PFS header")
        pfs_version, pfs_magic = struct.unpack_from("<2q", pfs)
        if pfs_version != 1 or pfs_magic != 20130315:
            raise PackageError("Unsupported PFS header")
        mode = struct.unpack_from("<H", pfs, 0x1C)[0]
        content_id = header[0x40:0x64].split(b"\0", 1)[0].decode("ascii", errors="strict")
        if sfo.get("CONTENT_ID") != content_id:
            raise PackageError("PKG and SFO content IDs differ")
        digest = None
        if with_sha256:
            stream.seek(0)
            hasher = hashlib.sha256()
            while chunk := stream.read(4 * 1024 * 1024):
                hasher.update(chunk)
            digest = hasher.hexdigest()
        final = os.fstat(stream.fileno())
        if (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
            raise PackageError("Source changed while being inspected")
    return {
        "schema": "pt-ipad-package-audit-v1", "source": str(path), "bytes": size,
        "sha256": digest,
        "pkg": {"magic": "7f434e54", "flags": hex(u32(4)), "content_id": content_id,
                "entry_count": count, "entry_offset": offset, "entries": entries},
        "sfo": {k: sfo[k] for k in ("TITLE", "TITLE_ID", "APP_VER", "VERSION", "CATEGORY",
                                      "CONTENT_ID", "SYSTEM_VER", "PUBTOOLINFO") if k in sfo},
        "pfs": {"offset": pfs_start, "bytes": pfs_size, "version": pfs_version,
                "magic": hex(pfs_magic), "mode": hex(mode), "encrypted_flag": bool(mode & 4),
                "block_bytes": struct.unpack_from("<I", pfs, 0x20)[0]},
        "evidence": {"container_metadata_read": True, "payload_extracted": False,
                     "payload_decryption_verified": False, "payload_files_validated": False},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--sha256", action="store_true", help="also read the whole file sequentially")
    parser.add_argument("--output", type=Path, help="explicit new JSON report path; never overwrites")
    args = parser.parse_args(argv)
    try:
        report = inspect_package(args.package, args.sha256)
        text = json.dumps(report, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(text)
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError, UnicodeError, struct.error) as exc:
        print(f"Package inspection refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
