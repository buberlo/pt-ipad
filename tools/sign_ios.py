#!/usr/bin/env python3
"""Sign the native iPad bundle with an explicit local development profile and identity."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import zipfile


def run(*cmd):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT)


def sign(app, profile_path, identity, output):
    app = app.resolve()
    info = plistlib.loads((app / "Info.plist").read_bytes())
    bundle = info["CFBundleIdentifier"]
    if bundle != "com.konradkern.pt.native":
        raise ValueError("refusing to sign an unrelated bundle")
    exe = app / info["CFBundleExecutable"]
    description = run("file", str(exe)).decode()
    if "Mach-O 64-bit executable arm64" not in description:
        raise ValueError("expected a native ARM64 Mach-O executable")
    platform = run("xcrun", "vtool", "-show-build", str(exe)).decode()
    if "platform IOS\n" not in platform:
        raise ValueError("executable is not built for physical iOS")
    profile = plistlib.loads(run("security", "cms", "-D", "-i", str(profile_path)))
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
    output = output.absolute()
    if output.exists():
        raise ValueError("output IPA already exists; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(profile_path, app / "embedded.mobileprovision")
    with tempfile.TemporaryDirectory(prefix="pt-sign-") as directory:
        entitlements_path = Path(directory) / "entitlements.plist"
        entitlements_path.write_bytes(plistlib.dumps(entitlements))
        run("codesign", "--force", "--sign", identity, "--entitlements", str(entitlements_path), str(app))
    run("codesign", "--verify", "--deep", "--strict", str(app))
    raw_entitlements = run("codesign", "-d", "--entitlements", ":-", str(app))
    begin, end = raw_entitlements.find(b"<?xml"), raw_entitlements.rfind(b"</plist>")
    if begin < 0 or end < begin:
        raise ValueError("codesign did not return a plist of signed entitlements")
    actual = plistlib.loads(raw_entitlements[begin:end + len(b"</plist>")])
    if actual.get("application-identifier") != expected:
        raise ValueError("signed application identity mismatch")
    with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".partial", dir=output.parent, delete=False) as f:
        temporary = Path(f.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            for f in sorted(app.rglob("*")):
                if f.is_symlink():
                    raise ValueError("unexpected symlink in static application bundle")
                if f.is_file():
                    archive.write(f, str(Path("Payload") / app.name / f.relative_to(app)))
        # Create without replacing an IPA produced by a concurrent command.
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {
        "schema": 1, "bundle_id": bundle, "architecture": "arm64", "platform": "iOS",
        "signed": True, "installed": False, "gameplay_accepted": False,
        "ipa_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "profile_expires": expires.isoformat(),
    }
    output.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        sign(args.app, args.profile, args.identity, args.output)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Signing failed: {error}\n")
