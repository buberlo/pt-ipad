"""Identity and lease regression tests use fake files, never a physical device."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from app_identity import bundle_id, test_bundle_ids
from device_lease import Lease, LeaseError
import build_provenance as provenance
import sign_ios
import test_build_provenance as fixtures


class CustomIdentityTests(unittest.TestCase):
    setUp = fixtures.ProvenanceTests.setUp
    bundle = fixtures.ProvenanceTests.bundle
    def custom_bundle(self):
        app, info, manifest = self.bundle()
        info['CFBundleIdentifier'] = 'org.example.pt'
        (app / 'Info.plist').write_bytes(plistlib.dumps(info))
        manifest.update(schema=2, bundle_id=info['CFBundleIdentifier'],
                        bundle_resources_sha256=provenance.bundle_resources_hash(app, 'pt'))
        (app / provenance.MANIFEST_NAME).write_text(json.dumps(manifest))
        return app, info, manifest

    def test_custom_bundle_requires_explicit_selection(self):
        app, info, _ = self.custom_bundle()
        sign_ios.inspect_bundle(app, info['CFBundleIdentifier'])
        with self.assertRaises(ValueError):
            sign_ios.inspect_bundle(app)
        provenance.verify_bundle_manifest(app, info)

    def test_custom_manifest_mismatch_and_legacy_rejected(self):
        app, info, manifest = self.custom_bundle()
        for changes in ({'bundle_id': 'org.wrong.pt'}, {'schema': 1}):
            (app / provenance.MANIFEST_NAME).write_text(json.dumps(dict(manifest, **changes)))
            with self.assertRaisesRegex(ValueError, 'bundle ID'):
                provenance.verify_bundle_manifest(app, info)

    def test_custom_wrong_profile_rejected_without_outputs(self):
        app, info, _ = self.custom_bundle()
        profile = self.root / 'profile'
        profile.write_bytes(b'fixture')
        def tool(*args):
            if args[0] == 'file':
                return b'Mach-O 64-bit executable arm64'
            if args[0] == 'xcrun':
                return b'platform IOS\n'
            return plistlib.dumps({'ExpirationDate': datetime.now() + timedelta(days=1),
                'ProvisionedDevices': ['fixture'], 'TeamIdentifier': ['TEST'],
                'Entitlements': {'application-identifier': 'TEST.org.wrong.pt'}})
        with mock.patch.object(sign_ios, 'run', side_effect=tool):
            with self.assertRaisesRegex(ValueError, 'profile does not authorize'):
                sign_ios.sign(app, profile, 'identity', self.root / 'out.ipa', info['CFBundleIdentifier'])
        self.assertFalse((self.root / 'out.ipa').exists())

    def test_custom_signing_with_matching_profile(self):
        app, info, _ = self.custom_bundle()
        profile = self.root / 'profile'
        profile.write_bytes(b'fixture')
        entitlement = {'application-identifier': 'TEST.org.example.pt', 'get-task-allow': True}
        def tool(*args):
            if args[0] == 'file':
                return b'Mach-O 64-bit executable arm64'
            if args[0] == 'xcrun':
                return b'platform IOS\n'
            if args[0] == 'security':
                return plistlib.dumps({'ExpirationDate': datetime.now() + timedelta(days=1),
                    'ProvisionedDevices': ['fixture'], 'TeamIdentifier': ['TEST'],
                    'Entitlements': entitlement, 'DeveloperCertificates': [b'certificate']})
            if args[0] == 'codesign' and '--force' in args:
                executable = Path(args[-1]) / 'pt'
                executable.write_bytes(executable.read_bytes() + b'signed')
            if args[0] == 'codesign' and '--entitlements' in args and '-d' in args:
                return plistlib.dumps(entitlement)
            for item in args:
                if item.startswith('--extract-certificates='):
                    Path(item.split('=', 1)[1] + '0').write_bytes(b'certificate')
            return b''
        with mock.patch.object(sign_ios, 'run', side_effect=tool):
            receipt = sign_ios.sign(app, profile, 'fixture', self.root / 'out.ipa', info['CFBundleIdentifier'])
        self.assertEqual(receipt['bundle_id'], 'org.example.pt')

    def test_identifier_validation(self):
        for value in ('', 'one', 'org..pt', 'org/example', 'org.pt.*', 'org.pt\n'):
            with self.assertRaises(ValueError):
                bundle_id(value)
        self.assertEqual(test_bundle_ids('org.example.pt'), ('org.example.pt.harness', 'org.example.pt.harness.tests.xctrunner'))


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.record = self.root / 'lease.json'
        self.original = {'owner': None, 'deviceUDID': 'fixture', 'allowedOwners': ['pt-native'],
                         'nextRequestedPhases': [{'owner': 'other', 'phase': 'preserve'}], 'unknown': [1, 2]}
        self.record.write_text(json.dumps(self.original))
        self.lease = Lease(self.record, 'pt-native', 'session', 2, 'fixture')

    def change(self, **changes):
        value = json.loads(self.record.read_text())
        value.update(changes)
        self.record.write_text(json.dumps(value))

    def test_claim_release_preserves_queue_and_unknown_fields(self):
        self.lease.claim()
        self.lease.check()
        self.assertTrue(self.lease.release())
        value = json.loads(self.record.read_text())
        for key in ('nextRequestedPhases', 'unknown'):
            self.assertEqual(value[key], self.original[key])
        self.assertIsNone(value['owner'])

    def test_concurrent_and_same_session_claims_refused(self):
        self.lease.claim()
        for session in ('session', 'different'):
            with self.assertRaises(LeaseError):
                Lease(self.record, 'pt-native', session, 2, 'fixture').claim()

    def test_foreign_expired_owner_not_stolen(self):
        self.change(owner='other', reservedUntil=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
        with self.assertRaises(LeaseError):
            self.lease.claim()
        self.assertEqual(json.loads(self.record.read_text())['owner'], 'other')

    def test_pause_allowlist_and_device_mismatch(self):
        for change in ({'deviceWorkPaused': True}, {'status': 'user-stopped'},
                       {'allowedOwners': ['other']}, {'deviceUDID': 'wrong'}):
            self.record.write_text(json.dumps(dict(self.original, **change)))
            with self.assertRaises(LeaseError):
                self.lease.claim()

    def test_unsafe_records(self):
        self.record.unlink()
        target = self.root / 'other'
        target.write_text(json.dumps(self.original))
        self.record.symlink_to(target)
        with self.assertRaises(OSError):
            self.lease.claim()
        self.record.unlink()
        self.record.write_text(' ' * (1024 * 1024 + 1))
        with self.assertRaises(LeaseError):
            self.lease.claim()

    def test_newer_claim_and_paused_state_preserved(self):
        self.lease.claim()
        self.change(deviceWorkPaused=True, status='user-stopped')
        self.assertTrue(self.lease.release())
        self.assertEqual(json.loads(self.record.read_text())['status'], 'user-stopped')
        self.record.write_text(json.dumps(self.original))
        self.lease.claim()
        self.change(commandLease={'token': 'newer', 'wrapperPid': 123})
        snapshot = self.record.read_bytes()
        self.assertFalse(self.lease.release())
        self.assertEqual(self.record.read_bytes(), snapshot)

    def test_receipt_symlink_or_hardlink_never_releases(self):
        receipt = self.root / 'receipt'
        self.lease.receipt = receipt
        self.lease.claim()
        target = self.root / 'receipt-target'
        target.write_text(json.dumps({'lease_token': self.lease.token, 'cleanup_confirmed': True}))
        receipt.symlink_to(target)
        self.assertFalse(self.lease.release())
        self.assertEqual(json.loads(self.record.read_text())['status'], 'pt-device-cleanup-required')


if __name__ == '__main__':
    unittest.main()
