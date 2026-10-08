import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import inspect_pt_package as pkg

CONTENT_ID = "UP4511-CUSA01127_00-PPPPPPPPTTTTTTTT"


def synthetic_sfo():
    values = {"TITLE": "P.T.", "TITLE_ID": "CUSA01127", "CONTENT_ID": CONTENT_ID,
              "APP_VER": "01.00", "VERSION": "01.00"}
    keys, body, records = bytearray(), bytearray(), []
    for key, value in values.items():
        raw = value.encode() + b"\0"
        records.append(struct.pack("<HHIII", len(keys), 0x204, len(raw), len(raw), len(body)))
        keys.extend(key.encode() + b"\0")
        body.extend(raw)
    key_start = 20 + 16 * len(records)
    return struct.pack("<5I", 0x46535000, 0x101, key_start, key_start + len(keys), len(records)) + b"".join(records) + keys + body


def synthetic_pkg():
    data = bytearray(0x4000)
    data[:4] = b"\x7fCNT"
    struct.pack_into(">I", data, 0x10, 1)
    struct.pack_into(">I", data, 0x18, 0x1200)
    data[0x40:0x40 + len(CONTENT_ID)] = CONTENT_ID.encode()
    struct.pack_into(">I", data, 0x404, 1)
    struct.pack_into(">Q", data, 0x410, 0x3000)
    struct.pack_into(">Q", data, 0x418, 0x1000)
    struct.pack_into(">Q", data, 0x430, len(data))
    sfo = synthetic_sfo()
    struct.pack_into(">6IQ", data, 0x1200, 0x1000, 0, 0, 0, 0x2000, len(sfo), 0)
    data[0x2000:0x2000 + len(sfo)] = sfo
    struct.pack_into("<2q", data, 0x3000, 1, 20130315)
    struct.pack_into("<H", data, 0x301C, 0xD)
    struct.pack_into("<I", data, 0x3020, 65536)
    return data


class PackageInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.pkg"
        self.data = synthetic_pkg()
        self.path.write_bytes(self.data)

    def inspect(self):
        self.path.write_bytes(self.data)
        return pkg.inspect_package(self.path)

    def test_metadata_does_not_claim_decryption(self):
        result = self.inspect()
        self.assertEqual(result["sfo"]["TITLE_ID"], "CUSA01127")
        self.assertTrue(result["pfs"]["encrypted_flag"])
        self.assertFalse(result["evidence"]["payload_decryption_verified"])
        self.assertIsNone(result["sha256"])

    def test_optional_full_hash(self):
        result = pkg.inspect_package(self.path, True)
        self.assertEqual(result["sha256"], hashlib.sha256(self.data).hexdigest())

    def test_truncated_header(self):
        self.data = self.data[:100]
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_declared_size_mismatch(self):
        struct.pack_into(">Q", self.data, 0x430, len(self.data) + 1)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_bounded_entry_count(self):
        struct.pack_into(">I", self.data, 0x10, pkg.MAX_ENTRIES + 1)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_table_outside_file(self):
        struct.pack_into(">I", self.data, 0x18, len(self.data) - 1)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_sfo_outside_file(self):
        struct.pack_into(">I", self.data, 0x1210, len(self.data) - 1)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_sfo_value_over_capacity(self):
        struct.pack_into("<I", self.data, 0x2000 + 24, 999)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_sfo_key_outside_table(self):
        struct.pack_into("<H", self.data, 0x2000 + 20, 0xFFFF)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_encrypted_sfo_is_refused(self):
        struct.pack_into(">I", self.data, 0x1208, 0x80000000)
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_pfs_outside_file(self):
        struct.pack_into(">Q", self.data, 0x418, len(self.data))
        with self.assertRaises(pkg.PackageError): self.inspect()

    def test_existing_output_cannot_overwrite_input(self):
        before = self.path.read_bytes()
        self.assertEqual(pkg.main([str(self.path), "--output", str(self.path)]), 1)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__": unittest.main()
