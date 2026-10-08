import hashlib
import json
import os
from pathlib import Path
import struct
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import import_pt_assets as assets
from test_inspect_pt_package import synthetic_pkg


class AssetImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / "source.pkg"
        self.package.write_bytes(synthetic_pkg())
        self.private = self.root / "assets-private"
        self.destination = self.private / "CUSA01127"
        self.payload = b"synthetic asset data"
        self.expected = {"chunk1.psarc": (len(self.payload), hashlib.sha256(self.payload).hexdigest())}

    def extractor(self, command, package, stage):
        (stage / "chunk1.psarc").write_bytes(self.payload)

    def run_import(self, **kwargs):
        return assets.import_assets(self.package, self.private, [], expected=self.expected,
                                    extractor=kwargs.pop("extractor", self.extractor),
                                    metadata_reader=lambda _: {"synthetic": True}, **kwargs)

    def test_success_source_unchanged_and_evidence_limited(self):
        before = self.package.read_bytes()
        report = self.run_import()
        self.assertEqual(self.package.read_bytes(), before)
        self.assertTrue(report["source_unchanged"])
        self.assertFalse(report["evidence"]["runtime_verified"])
        self.assertEqual((self.destination / "chunk1.psarc").read_bytes(), self.payload)
        self.assertFalse(list(self.private.glob(".pt-assets-stage-*")))

    def test_existing_data_and_saves_survive_cancel(self):
        self.run_import()
        old = (self.destination / assets.MANIFEST).read_bytes()
        saves = self.root / "saves"
        saves.mkdir()
        (saves / "save.bin").write_bytes(b"old save")
        def cancelled(command, package, stage):
            (stage / "chunk1.psarc").write_bytes(b"partial")
            raise assets.ImportCancelled()
        with self.assertRaises(assets.ImportCancelled):
            self.run_import(replace=True, extractor=cancelled, save_root=saves)
        self.assertEqual((self.destination / assets.MANIFEST).read_bytes(), old)
        self.assertEqual((saves / "save.bin").read_bytes(), b"old save")
        self.assertFalse(list(self.private.glob(".pt-assets-stage-*")))

    def test_corruption_rejected_before_publish(self):
        def bad(command, package, stage): (stage / "chunk1.psarc").write_bytes(b"x" * len(self.payload))
        with self.assertRaisesRegex(assets.ImportError, "SHA-256"):
            self.run_import(extractor=bad)
        self.assertFalse(self.destination.exists())

    def test_unexpected_extractor_path_rejected(self):
        def extra(command, package, stage):
            self.extractor(command, package, stage)
            (stage / "eboot.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(assets.ImportError, "unexpected"):
            self.run_import(extractor=extra)
        self.assertFalse(self.destination.exists())

    def test_symlink_asset_rejected(self):
        external = self.root / "external"
        external.write_bytes(self.payload)
        def linked(command, package, stage): (stage / "chunk1.psarc").symlink_to(external)
        with self.assertRaisesRegex(assets.ImportError, "Symbolic"):
            self.run_import(extractor=linked)
        self.assertEqual(external.read_bytes(), self.payload)

    def test_symlink_destination_ancestor_rejected(self):
        external = self.root / "external"
        external.mkdir()
        self.private.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(assets.ImportError, "Symbolic"):
            self.run_import()
        self.assertEqual(list(external.iterdir()), [])

    def test_save_root_inside_assets_rejected(self):
        with self.assertRaisesRegex(assets.ImportError, "separate"):
            self.run_import(save_root=self.destination / "saves")

    def test_package_hash_change_rejected(self):
        def mutation(command, package, stage):
            self.extractor(command, package, stage)
            data = bytearray(package.read_bytes())
            data[-1] ^= 1
            package.write_bytes(data)
        with self.assertRaisesRegex(assets.ImportError, "changed during extraction"):
            self.run_import(extractor=mutation)
        self.assertFalse(self.destination.exists())

    def test_unknown_destination_not_replaced(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "keep.txt"
        marker.write_text("keep")
        with self.assertRaisesRegex(assets.ImportError, "unowned"):
            self.run_import(replace=True)
        self.assertEqual(marker.read_text(), "keep")

    def test_commit_failure_restores_previous_directory(self):
        self.run_import()
        old = (self.destination / assets.MANIFEST).read_bytes()
        rename = assets.os.rename
        def fail_stage(source, dest):
            if Path(source).name.startswith(".pt-assets-stage-"):
                raise OSError("synthetic rename failure")
            return rename(source, dest)
        with mock.patch.object(assets.os, "rename", side_effect=fail_stage):
            with self.assertRaises(OSError): self.run_import(replace=True)
        self.assertEqual((self.destination / assets.MANIFEST).read_bytes(), old)
        self.assertFalse(list(self.private.glob(".pt-assets-old-*")))

    def test_signal_after_old_rename_rolls_back(self):
        self.run_import()
        old = (self.destination / assets.MANIFEST).read_bytes()
        rename = assets.os.rename
        def interrupted(source, dest):
            rename(source, dest)
            if Path(dest).name.startswith(".pt-assets-old-"):
                os.kill(os.getpid(), signal.SIGINT)
        with mock.patch.object(assets.os, "rename", side_effect=interrupted):
            with self.assertRaises(assets.ImportCancelled): self.run_import(replace=True)
        self.assertEqual((self.destination / assets.MANIFEST).read_bytes(), old)
        self.assertFalse(list(self.private.glob(".pt-assets-old-*")))

    def test_low_space_refuses_before_extraction(self):
        with mock.patch.object(assets.shutil, "disk_usage", return_value=mock.Mock(free=0)):
            with self.assertRaisesRegex(assets.ImportError, "Insufficient"):
                self.run_import(extractor=lambda *_: self.fail("extractor must not run"))

    def test_path_traversal_expected_name_rejected(self):
        self.private.mkdir()
        with self.assertRaisesRegex(assets.ImportError, "Unsafe"):
            assets.validate_assets(self.private, {"../outside": (0, "")})

    @unittest.skipUnless(os.name == "posix", "process-group cancellation is POSIX-specific")
    def test_running_helper_is_terminated_on_interrupt(self):
        stage = self.root / "stage"
        stage.mkdir()
        helper = self.root / "sleep_helper.py"
        helper.write_text("import os,sys,time\nfrom pathlib import Path\n"
                          "Path(sys.argv[2], 'pid').write_text(str(os.getpid()))\n"
                          "time.sleep(30)\n")
        runner = self.root / "runner.py"
        tools_dir = str(Path(assets.__file__).parent)
        runner.write_text("import sys\nfrom pathlib import Path\n"
                          f"sys.path.insert(0, {tools_dir!r})\n"
                          "from import_pt_assets import run_extractor\n"
                          "run_extractor([sys.executable, sys.argv[1]], Path(sys.argv[2]), Path(sys.argv[3]))\n")
        process = subprocess.Popen([sys.executable, str(runner), str(helper), str(self.package), str(stage)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not (stage / "pid").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((stage / "pid").exists(), "helper did not start")
            helper_pid = int((stage / "pid").read_text())
            process.send_signal(signal.SIGINT)
            process.wait(timeout=5)
            with self.assertRaises(ProcessLookupError): os.kill(helper_pid, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


class ArchiveMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "chunk1.psarc").write_bytes(
            struct.pack(">4sI4s5I", b"PSAR", 0x10004, b"zlib", 62, 30, 1, 65536, 0) + bytes(30))
        qar = bytearray(68)
        struct.pack_into("<QII", qar, 16, 1, 0, 16)
        struct.pack_into("<IHHI", qar, 32 + 16, 1, 0, 0x7161, 1)
        (self.root / "texture.qar").write_bytes(qar)
        pathlist = bytearray(96)
        struct.pack_into("<4I", pathlist, 0, 1, 1, 1, 1)
        directory = b"/app0/as/sh/pt14_room\0"
        struct.pack_into("<I", pathlist, 80, len(directory))
        pathlist.extend(directory + b"texture\0")
        (self.root / "pathid_list_ps4.bin").write_bytes(pathlist)

    def mutate(self, name, offset, fmt, value):
        path = self.root / name
        data = bytearray(path.read_bytes())
        struct.pack_into(fmt, data, offset, value)
        path.write_bytes(data)

    def test_metadata_structure(self):
        result = assets.archive_metadata(self.root)
        self.assertEqual(result["psarc"]["toc_entries"], 1)
        self.assertEqual(result["qar"]["entries"], 1)
        self.assertEqual(result["pathlist"]["paths"], 1)

    def test_psarc_table_overflow(self):
        self.mutate("chunk1.psarc", 12, ">I", 0xFFFFFFFF)
        with self.assertRaises(ValueError): assets.archive_metadata(self.root)

    def test_qar_data_entry_outside_data(self):
        self.mutate("texture.qar", 24, "<I", 0xFFFFFFFF)
        with self.assertRaises(ValueError): assets.archive_metadata(self.root)

    def test_qar_table_outside_archive(self):
        self.mutate("texture.qar", 56, "<I", 0xFFFFFFFF)
        with self.assertRaises(ValueError): assets.archive_metadata(self.root)

    def test_pathlist_bad_record_index(self):
        self.mutate("pathid_list_ps4.bin", 48, "<I", 2)
        with self.assertRaises(ValueError): assets.archive_metadata(self.root)

    def test_pathlist_string_offset_outside_file(self):
        self.mutate("pathid_list_ps4.bin", 64, "<I", 0xFFFFFFFF)
        with self.assertRaises(ValueError): assets.archive_metadata(self.root)


if __name__ == "__main__": unittest.main()
