"""No builds, signing identities or devices are used by these corruption tests."""
import json
from datetime import datetime, timedelta
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_provenance as provenance
import sign_ios


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def archive(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'module.cpp').write_text('int value = 1;\n')
        expected = {'kind': 'archive', 'source_tree_sha256': provenance.tree_hash(source)}
        return source, expected

    def bundle(self):
        app = self.root / 'pt.app'
        app.mkdir()
        info = {'CFBundleIdentifier': 'com.konradkern.pt.native', 'CFBundleVersion': '4',
                'CFBundleShortVersionString': '1.0.1', 'CFBundleExecutable': 'pt'}
        (app / 'Info.plist').write_bytes(plistlib.dumps(info))
        (app / 'pt').write_bytes(b'pretend executable')
        (app / 'voice').mkdir()
        (app / 'voice/model.bin').write_bytes(b'original model')
        manifest = {'schema': 1, 'status': 'built', 'platform': 'ios', 'application_build': 4,
                    'source_commit': 'c' * 40, 'source_tree_sha256': 'a' * 64,
                    'dependency_lock_sha256': 'b' * 64, 'dependency_inputs': {'library': {'commit': 'c' * 40}},
                    'unsigned_executable_sha256': provenance.digest(app / 'pt'),
                    'bundle_resources_sha256': provenance.bundle_resources_hash(app, 'pt')}
        manifest['dependency_inputs_sha256'] = provenance.canonical_hash(manifest['dependency_inputs'])
        (app / provenance.MANIFEST_NAME).write_text(json.dumps(manifest))
        return app, info, manifest

    def test_archive_cache_accepts_exact_and_rejects_changed_bytes(self):
        source, expected = self.archive()
        provenance.verify_dependency(source, expected)
        (source / 'module.cpp').write_text('int value = 2;\n')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            provenance.verify_dependency(source, expected)

    def test_added_ignored_source_is_not_omitted_from_tree_hash(self):
        source, expected = self.archive()
        (source / 'ignored.generated.cpp').write_text('unexpected implementation')
        with self.assertRaisesRegex(ValueError, 'content differs'):
            provenance.verify_dependency(source, expected)

    def test_internal_dependency_link_hashes_link_but_external_link_is_rejected(self):
        source, _ = self.archive()
        (source / 'link').symlink_to('module.cpp')
        expected = {'kind': 'archive', 'source_tree_sha256': provenance.tree_hash(source, internal_symlinks=True)}
        provenance.verify_dependency(source, expected)
        (source / 'link').unlink()
        (source / 'link').symlink_to(self.root / 'outside.cpp')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            provenance.verify_dependency(source, expected)

    def test_git_cache_rejects_wrong_commit_even_when_content_matches(self):
        source, expected = self.archive()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.STDOUT, text=True).strip()
        git('init')
        git('add', '.')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
        expected.update(kind='git', commit=git('rev-parse', 'HEAD'))
        provenance.verify_dependency(source, expected)
        expected['commit'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'commit differs'):
            provenance.verify_dependency(source, expected)

    def test_bundle_manifest_accepts_matching_resource_and_executable(self):
        app, info, manifest = self.bundle()
        actual, sha = provenance.verify_bundle_manifest(app, info)
        self.assertEqual(actual, manifest)
        self.assertEqual(sha, provenance.digest(app / provenance.MANIFEST_NAME))

    def test_model_tampering_fails_before_signing_subprocess_or_output(self):
        app, _, _ = self.bundle()
        (app / 'voice/model.bin').write_bytes(b'changed model')
        with mock.patch.object(sign_ios, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'resources differ'):
                sign_ios.sign(app, self.root / 'profile', 'identity', self.root / 'out.ipa')
            run.assert_not_called()
        self.assertFalse((self.root / 'out.ipa').exists())

    def test_hidden_git_named_bundle_resource_is_not_excluded(self):
        app, info, _ = self.bundle()
        (app / '.git').mkdir()
        (app / '.git/hidden-resource.bin').write_bytes(b'not in the built bundle')
        with self.assertRaisesRegex(ValueError, 'resources differ'):
            provenance.verify_bundle_manifest(app, info)

    def test_executable_replacement_and_dependency_record_tampering_fail(self):
        app, info, manifest = self.bundle()
        original = (app / 'pt').read_bytes()
        (app / 'pt').write_bytes(b'other executable')
        with self.assertRaisesRegex(ValueError, 'executable differs'):
            provenance.verify_bundle_manifest(app, info)
        (app / 'pt').write_bytes(original)
        manifest['dependency_inputs']['library']['commit'] = 'd' * 40
        (app / provenance.MANIFEST_NAME).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'dependency inputs'):
            provenance.verify_bundle_manifest(app, info)

    def test_unfinished_build_and_wrong_build_number_fail(self):
        app, info, manifest = self.bundle()
        for key, value in (('status', 'configured'), ('application_build', 3)):
            changed = dict(manifest, **{key: value})
            (app / provenance.MANIFEST_NAME).write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'completed iOS'):
                provenance.verify_bundle_manifest(app, info)

    def test_signing_receipt_binds_completed_manifest_and_preserves_input(self):
        app, _, manifest = self.bundle()
        original = (app / 'pt').read_bytes()
        profile = self.root / 'test.mobileprovision'
        profile.write_bytes(b'fixture profile')
        entitlement = {'application-identifier': 'TEST.com.konradkern.pt.native', 'get-task-allow': True}
        def signing_tool(*args):
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
        output = self.root / 'signed.ipa'
        with mock.patch.object(sign_ios, 'run', side_effect=signing_tool):
            receipt = sign_ios.sign(app, profile, 'fixture identity', output)
        self.assertEqual((app / 'pt').read_bytes(), original)
        self.assertEqual(receipt['source_tree_sha256'], manifest['source_tree_sha256'])
        self.assertEqual(receipt['dependency_inputs_sha256'], manifest['dependency_inputs_sha256'])
        self.assertEqual(receipt['build_manifest_sha256'], provenance.digest(app / provenance.MANIFEST_NAME))
        self.assertEqual(receipt['unsigned_executable_sha256'], provenance.digest(app / 'pt'))
        self.assertNotEqual(receipt['unsigned_executable_sha256'], receipt['executable_sha256'])
        self.assertEqual((output.with_suffix('') / 'pt.app' / provenance.MANIFEST_NAME).read_bytes(),
                         (app / provenance.MANIFEST_NAME).read_bytes())


if __name__ == '__main__':
    unittest.main()
