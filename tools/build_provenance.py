"""Local dependency validation and portable build/signing provenance."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from app_identity import DEFAULT_BUNDLE_ID

MANIFEST_NAME = "pt-build-manifest.json"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def tree_hash(root, *, exclude=(), internal_symlinks=False, skip_git_metadata=True):
    """Hash relative names and bytes, including ignored files; never follow symlinks."""
    root = Path(root)
    excluded = set(exclude)
    entries = []
    for parent, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if not skip_git_metadata or name != ".git")
        for name in directories + files:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if any(relative == item or relative.startswith(item + "/") for item in excluded):
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                if not internal_symlinks or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError(f"unexpected dependency or bundle symlink: {path}")
                entries.append((relative, "symlink:" + os.readlink(path)))
                continue
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError(f"unexpected dependency or bundle special file: {path}")
            entries.append((relative, digest(path)))
    return canonical_hash(sorted(entries))


def verify_dependency(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"dependency source directory is missing or unsafe: {path}")
    if expected["kind"] == "git":
        if not (path / ".git").exists():
            raise ValueError(f"dependency Git metadata is missing: {path}")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()
        if Path(git("rev-parse", "--show-toplevel")).resolve() != path.resolve():
            raise ValueError(f"dependency is not its own Git checkout: {path}")
        if git("rev-parse", "HEAD") != expected["commit"]:
            raise ValueError(f"dependency commit differs from lock: {path}")
        if git("status", "--porcelain", "--untracked-files=all"):
            raise ValueError(f"dependency checkout has local changes: {path}")
    actual = tree_hash(path, internal_symlinks=True)
    if actual != expected["source_tree_sha256"]:
        raise ValueError(f"dependency content differs from lock: {path}")
    return {"kind": expected["kind"], "commit": expected.get("commit"),
            "archive_sha256": expected.get("archive_sha256"), "source_tree_sha256": actual}


def bundle_resources_hash(app, executable):
    return tree_hash(app, exclude=(executable, MANIFEST_NAME, "_CodeSignature", "embedded.mobileprovision"),
                     skip_git_metadata=False)


def verify_bundle_manifest(app, info):
    """Bind the supplied bundle bytes to the manifest emitted after a successful build."""
    app = Path(app)
    manifest_path = app / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("schema") not in (1, 2) or manifest.get("status") != "built" or
            manifest.get("platform") != "ios" or
            str(manifest.get("application_build")) != info["CFBundleVersion"]):
        raise ValueError("build manifest does not identify this completed iOS application")
    if (manifest.get("schema") == 1 and info["CFBundleIdentifier"] != DEFAULT_BUNDLE_ID or
            manifest.get("schema") == 2 and manifest.get("bundle_id") != info["CFBundleIdentifier"]):
        raise ValueError("build manifest bundle ID does not match application metadata")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", ""))):
        raise ValueError("build manifest has no valid upstream source commit")
    for key in ("source_tree_sha256", "dependency_lock_sha256", "dependency_inputs_sha256",
                "unsigned_executable_sha256", "bundle_resources_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(key, ""))):
            raise ValueError(f"build manifest is missing a valid {key}")
    if not manifest.get("dependency_inputs") or canonical_hash(manifest["dependency_inputs"]) != manifest["dependency_inputs_sha256"]:
        raise ValueError("build manifest dependency inputs are missing or changed")
    if digest(app / info["CFBundleExecutable"]) != manifest["unsigned_executable_sha256"]:
        raise ValueError("application executable differs from completed build manifest")
    if bundle_resources_hash(app, info["CFBundleExecutable"]) != manifest["bundle_resources_sha256"]:
        raise ValueError("application resources differ from completed build manifest")
    return manifest, digest(manifest_path)
