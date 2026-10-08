#!/usr/bin/env python3
"""Sign a private copy of the native iPad bundle and publish new local artifacts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from app_identity import DEFAULT_BUNDLE_ID, bundle_id
from build_provenance import MANIFEST_NAME, verify_bundle_manifest


def run(*cmd):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def absent(path):
    # exists() alone does not recognize a dangling symlink.
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists; choose a new path: {path}")


def inspect_bundle(app, expected_bundle=DEFAULT_BUNDLE_ID):
    if app.is_symlink() or not app.is_dir():
        raise ValueError("input must be a real application directory")
    for parent, directories, files in os.walk(app, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"unexpected symlink or special file in static application bundle: {path}")
    info = plistlib.loads((app / "Info.plist").read_bytes())
    if info["CFBundleIdentifier"] != bundle_id(expected_bundle):
        raise ValueError("refusing to sign an unrelated bundle")
    executable = info["CFBundleExecutable"]
    if not isinstance(executable, str) or executable in ("", ".", "..") or Path(executable).name != executable:
        raise ValueError("invalid application executable name")
    for key in ("CFBundleVersion", "CFBundleShortVersionString"):
        if not isinstance(info.get(key), str) or not info[key]:
            raise ValueError(f"missing application version: {key}")
    return info


def sign(app, profile_path, identity, output, expected_bundle=DEFAULT_BUNDLE_ID):
    # All bundle shape checks precede even copying the profile; the input remains read-only.
    info = inspect_bundle(app, expected_bundle)
    app = app.resolve()
    build_manifest, build_manifest_sha256 = verify_bundle_manifest(app, info)
    bundle = info["CFBundleIdentifier"]
    if output.suffix != ".ipa":
        raise ValueError("--output must end in .ipa")
    output = output.absolute()
    receipt_path = output.with_suffix(".json")
    signed_root = output.with_suffix("")
    signed_app = signed_root / "pt.app"
    for path in (output, receipt_path, signed_root):
        if path.resolve().is_relative_to(app):
            raise ValueError("signing outputs must be outside the input application")
        absent(path)
    exe = app / info["CFBundleExecutable"]
    description = run("file", str(exe)).decode()
    if "Mach-O 64-bit executable arm64" not in description:
        raise ValueError("expected a native ARM64 Mach-O executable")
    platform = run("xcrun", "vtool", "-show-build", str(exe)).decode()
    if "platform IOS\n" not in platform:
        raise ValueError("executable is not built for physical iOS")
    profile_bytes = profile_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="pt-profile-") as directory:
        profile_snapshot = Path(directory) / "profile.mobileprovision"
        profile_snapshot.write_bytes(profile_bytes)
        profile = plistlib.loads(run("security", "cms", "-D", "-i", str(profile_snapshot)))
    expires = profile["ExpirationDate"].replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise ValueError("development profile expired")
    if not profile.get("ProvisionedDevices"):
        raise ValueError("expected a development profile with provisioned devices")
    entitlements = dict(profile["Entitlements"])
    team = profile["TeamIdentifier"][0]
    expected = team + "." + bundle
    allowed = entitlements.get("application-identifier", "")
    if allowed != expected and not (allowed.endswith(".*") and expected.startswith(allowed[:-1])):
        raise ValueError("profile does not authorize this bundle ID")
    if not entitlements.get("get-task-allow"):
        raise ValueError("expected a development signing profile")
    entitlements["application-identifier"] = expected
    if "keychain-access-groups" in entitlements:
        entitlements["keychain-access-groups"] = [expected]
    for key in entitlements:
        if "allow-jit" in key or "unsigned-executable-memory" in key or "dynamic-codesigning" in key:
            raise ValueError("unexpected CPU code-execution entitlement")
    certificates = profile.get("DeveloperCertificates", [])
    if not certificates or not all(isinstance(value, bytes) for value in certificates):
        raise ValueError("profile has no development signing certificates")
    output.parent.mkdir(parents=True, exist_ok=True)
    published = []
    with tempfile.TemporaryDirectory(prefix=".pt-sign-", dir=output.parent) as directory:
        stage = Path(directory)
        staged_app = stage / "pt.app"
        shutil.copytree(app, staged_app, symlinks=True)
        if inspect_bundle(staged_app, expected_bundle) != info:
            raise ValueError("application metadata changed during copying")
        copied_manifest, copied_manifest_sha256 = verify_bundle_manifest(staged_app, info)
        if copied_manifest_sha256 != build_manifest_sha256 or copied_manifest != build_manifest:
            raise ValueError("application build provenance changed during copying")
        staged_exe = staged_app / info["CFBundleExecutable"]
        if ("Mach-O 64-bit executable arm64" not in run("file", str(staged_exe)).decode() or
                "platform IOS\n" not in run("xcrun", "vtool", "-show-build", str(staged_exe)).decode()):
            raise ValueError("copied executable does not match the physical iOS target")
        (staged_app / "embedded.mobileprovision").write_bytes(profile_bytes)
        entitlements_path = stage / "entitlements.plist"
        entitlements_path.write_bytes(plistlib.dumps(entitlements))
        run("codesign", "--force", "--sign", identity, "--entitlements", str(entitlements_path), str(staged_app))
        run("codesign", "--verify", "--deep", "--strict", str(staged_app))
        raw = run("codesign", "-d", "--entitlements", ":-", str(staged_app))
        begin, end = raw.find(b"<?xml"), raw.rfind(b"</plist>")
        if begin < 0 or end < begin:
            raise ValueError("codesign did not return a plist of signed entitlements")
        actual = plistlib.loads(raw[begin:end + len(b"</plist>")])
        if actual.get("application-identifier") != expected:
            raise ValueError("signed application identity mismatch")
        certificate_prefix = stage / "signing-certificate-"
        run("codesign", "-d", f"--extract-certificates={certificate_prefix}", str(staged_app))
        if Path(str(certificate_prefix) + "0").read_bytes() not in certificates:
            raise ValueError("signing identity is not authorized by the provisioning profile")
        ipa = stage / "package.ipa"
        with zipfile.ZipFile(ipa, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for path in sorted(staged_app.rglob("*")):
                if path.is_symlink():
                    raise ValueError("unexpected symlink in signed static application bundle")
                if path.is_file():
                    archive.write(path, str(Path("Payload/pt.app") / path.relative_to(staged_app)))
        receipt = {
            "schema": 1, "bundle_id": bundle, "architecture": "arm64", "platform": "iOS",
            "application_build": info["CFBundleVersion"], "version": info["CFBundleShortVersionString"],
            "signed": True, "installed": False, "gameplay_accepted": False,
            "ipa_sha256": digest(ipa), "executable_sha256": digest(staged_app / info["CFBundleExecutable"]),
            "profile_expires": expires.isoformat(), "signed_app": str(signed_app),
            "build_manifest": MANIFEST_NAME, "build_manifest_sha256": build_manifest_sha256,
            "source_commit": build_manifest["source_commit"],
            "source_tree_sha256": build_manifest["source_tree_sha256"],
            "dependency_lock_sha256": build_manifest["dependency_lock_sha256"],
            "dependency_inputs_sha256": build_manifest["dependency_inputs_sha256"],
            "unsigned_executable_sha256": build_manifest["unsigned_executable_sha256"],
            "bundle_resources_sha256": build_manifest["bundle_resources_sha256"],
        }
        staged_receipt = stage / "receipt.json"
        staged_receipt.write_text(json.dumps(receipt, indent=2) + "\n")
        # Reserve the new app container exclusively; another invocation cannot claim
        # it. Final files use hard-link publication, which never replaces a target.
        try:
            signed_root.mkdir()
            try:
                staged_app.rename(signed_app)
            except BaseException:
                signed_root.rmdir()  # Only our still-empty reservation is removed.
                raise
            published.append(str(signed_app))
            os.link(ipa, output)
            published.append(str(output))
            os.link(staged_receipt, receipt_path)
            published.append(str(receipt_path))
        except BaseException:
            print("Signing publication incomplete; confirmed created artifacts: " + (", ".join(published) or "none") +
                  ". Inspect these reserved output paths before retrying: " +
                  ", ".join(map(str, (signed_root, output, receipt_path))), file=sys.stderr)
            raise
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", type=bundle_id, default=DEFAULT_BUNDLE_ID)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        sign(args.app, args.profile, args.identity, args.output, args.bundle_id)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Signing failed: {error}\n")
