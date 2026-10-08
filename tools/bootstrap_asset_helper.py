#!/usr/bin/env python3
"""Build the pinned upstream PKG helper locally; never installs system software.

With --install-sdk, a checksum-verified macOS ARM64 SDK is staged under --work-root,
then removed after the self-contained helper has been published successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from import_pt_assets import no_symlink_path

ROOT = Path(__file__).resolve().parents[1]
LIBORBIS_COMMIT = "643477263b2644e0803e0f58b8726ea4e3f3b7d4"
SDK_VERSION = "10.0.401"
SDK_URL = f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{SDK_VERSION}/dotnet-sdk-{SDK_VERSION}-osx-arm64.tar.gz"
SDK_SHA512 = "69f64eb00dc045398755c440b152225d544301a345a146a16e86a56a0c52b7c94b2c331520e976dbb821f18d31930aafbd25bb85961e3517e0665414ce0cbcff"
RESERVE = 512 * 1024 * 1024


def require_space(root, additional):
    if shutil.disk_usage(root).free < additional + RESERVE:
        raise RuntimeError(f"Need {additional + RESERVE} free bytes including 512MiB reserve")


def download(url, path, *, expected_sha512=None, max_bytes):
    digest = hashlib.sha512()
    total = 0
    with urllib.request.urlopen(url, timeout=60) as response, path.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError("Download exceeds declared bound")
            require_space(path.parent, len(chunk))
            digest.update(chunk)
            output.write(chunk)
    if expected_sha512 and digest.hexdigest() != expected_sha512:
        raise RuntimeError("SDK SHA-512 mismatch")
    return {"url": url, "bytes": total, "sha512": digest.hexdigest()}


def safe_member(name):
    name = PurePosixPath(name)
    if name.is_absolute() or ".." in name.parts or any(":" in p for p in name.parts):
        raise RuntimeError("Unsafe path in dependency archive")
    return name


def install_sdk(work):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Pinned SDK installer currently supports macOS ARM64 only; use --dotnet elsewhere")
    require_space(work, 1024 * 1024 * 1024)
    temporary = Path(tempfile.mkdtemp(prefix=".sdk-stage-", dir=work))
    archive = temporary / "sdk.tar.gz"
    installed = temporary / "sdk"
    try:
        provenance = download(SDK_URL, archive, expected_sha512=SDK_SHA512, max_bytes=240 * 1024 * 1024)
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            require_space(work, sum(m.size for m in members if m.isfile()) + 128 * 1024 * 1024)
            # Microsoft SDK contains relative symlinks. Validate both member and target
            # containment before extraction; refuse special files and absolute links.
            for member in members:
                name = safe_member(member.name)
                if member.issym() or member.islnk():
                    target = PurePosixPath(member.linkname)
                    if target.is_absolute():
                        raise RuntimeError("Absolute dependency symlink refused")
                    target_path = installed.joinpath(*name.parts).parent.joinpath(*target.parts)
                    if not os.path.commonpath([installed, os.path.abspath(target_path)]) == str(installed):
                        raise RuntimeError("Dependency symlink escapes SDK")
                elif not (member.isfile() or member.isdir()):
                    raise RuntimeError("Special dependency file refused")
            installed.mkdir()
            if sys.version_info >= (3, 12):
                source.extractall(installed, filter="data")
            else:
                source.extractall(installed)
        archive.unlink()
        return installed / "dotnet", temporary, provenance
    except BaseException:
        shutil.rmtree(temporary)
        raise


def fetch_liborbis(work):
    source = work / "liborbis-src"
    marker = source / ".pt-liborbis-commit"
    if source.exists():
        if not marker.is_file() or marker.read_text().strip() != LIBORBIS_COMMIT:
            raise RuntimeError("Existing LibOrbis source has unknown provenance")
        return source
    temporary = Path(tempfile.mkdtemp(prefix=".liborbis-stage-", dir=work))
    archive = temporary / "source.zip"
    try:
        download(f"https://codeload.github.com/maxton/LibOrbisPkg/zip/{LIBORBIS_COMMIT}", archive,
                 max_bytes=8 * 1024 * 1024)
        with zipfile.ZipFile(archive) as packed:
            if sum(e.file_size for e in packed.infolist()) > 32 * 1024 * 1024:
                raise RuntimeError("LibOrbis source archive expands beyond bound")
            for entry in packed.infolist():
                safe_member(entry.filename)
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise RuntimeError("LibOrbis archive symlink refused")
            packed.extractall(temporary / "unpacked")
        unpacked = temporary / "unpacked" / f"LibOrbisPkg-{LIBORBIS_COMMIT}"
        if not (unpacked / "LibOrbisPkg.Core" / "LibOrbisPkg.Core.csproj").is_file():
            raise RuntimeError("Unexpected LibOrbis source layout")
        (unpacked / marker.name).write_text(LIBORBIS_COMMIT + "\n")
        os.rename(unpacked, source)
        return source
    finally:
        shutil.rmtree(temporary)


def cleanup_build_cache(work):
    """Remove only this helper's generated caches, preserving corresponding source."""
    for relative in ("Extractor/bin", "Extractor/obj", "liborbis-src/LibOrbisPkg.Core/bin",
                     "liborbis-src/LibOrbisPkg.Core/obj", "cli-home", "nuget", "tmp"):
        path = no_symlink_path(work / relative)
        if path.exists():
            shutil.rmtree(path)


def build(args):
    work = no_symlink_path(args.work_root)
    work.mkdir(parents=True, exist_ok=True)
    upstream = args.upstream.resolve(strict=True)
    output = work / "published"
    if output.exists():
        raise RuntimeError("Helper output already exists; choose a new --work-root to rebuild")
    sdk_temporary = None
    sdk_provenance = None
    if args.install_sdk:
        dotnet, sdk_temporary, sdk_provenance = install_sdk(work)
    elif args.dotnet:
        dotnet = args.dotnet.resolve(strict=True)
    else:
        raise RuntimeError("Supply --dotnet or --install-sdk")
    source = fetch_liborbis(work)
    project = source / "LibOrbisPkg.Core" / "LibOrbisPkg.Core.csproj"
    text = project.read_text(encoding="utf-8-sig")
    replacements = [("netcoreapp3.0", "net10.0"), ("<LangVersion>7.3</LangVersion>", "<LangVersion>latest</LangVersion>"),
                    ("<GenerateSerializationAssemblies>Auto</GenerateSerializationAssemblies>",
                     "<GenerateSerializationAssemblies>Off</GenerateSerializationAssemblies>")]
    for before, after in replacements:
        if after not in text and text.count(before) != 1:
            raise RuntimeError("Unexpected LibOrbis project version")
        text = text.replace(before, after)
    project.write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, str(upstream / "tools" / "patch_liborbis_readers.py"), str(source)], check=True)
    wrapper = work / "Extractor"
    if not wrapper.exists():
        shutil.copytree(upstream / "installer" / "Extractor", wrapper, ignore=shutil.ignore_patterns("bin", "obj"))
    for name in ("cli-home", "nuget", "tmp"):
        (work / name).mkdir(exist_ok=True)
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
               DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE="1",
               DOTNET_CLI_HOME=str(work / "cli-home"), NUGET_PACKAGES=str(work / "nuget"),
               TMPDIR=str(work / "tmp"), DOTNET_ROOT=str(dotnet.parent))
    sdk_version = subprocess.check_output([str(dotnet), "--version"], env=env, text=True).strip()
    require_space(work, 160 * 1024 * 1024)
    subprocess.run([str(dotnet), "publish", str(wrapper / "Extractor.csproj"), "-c", "Release",
                    "-r", args.runtime, "--self-contained", "true", f"-p:LibOrbisSource={source}",
                    "-o", str(output)], env=env, check=True)
    executable = output / ("PT.PkgExtract.exe" if args.runtime.startswith("win") else "PT.PkgExtract")
    if not executable.is_file():
        raise RuntimeError("Publish did not produce the extraction helper")
    # A no-argument run must return the wrapper's usage error, verifying startup.
    result = subprocess.run([str(executable)], capture_output=True, text=True, env=env)
    if result.returncode != 1 or "Usage: PT.PkgExtract" not in result.stderr:
        raise RuntimeError("Self-contained extraction helper startup failed")
    provenance = {"schema": "pt-ipad-asset-helper-v1", "liborbis_commit": LIBORBIS_COMMIT,
                  "sdk_version": sdk_version, "sdk_download": sdk_provenance, "runtime": args.runtime,
                  "helper": str(executable), "startup_verified": True,
                  "wrapper_sha256": hashlib.sha256((wrapper / "Program.cs").read_bytes()).hexdigest(),
                  "patch_script_sha256": hashlib.sha256((upstream / "tools" / "patch_liborbis_readers.py").read_bytes()).hexdigest()}
    (work / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if sdk_temporary and not args.keep_sdk:
        shutil.rmtree(sdk_temporary)
    if not args.keep_build_cache:
        cleanup_build_cache(work)
    print(json.dumps(provenance, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, default=ROOT / ".local" / "asset-helper")
    parser.add_argument("--upstream", type=Path, default=ROOT / "upstream" / "pt-pc")
    parser.add_argument("--runtime", default="osx-arm64")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dotnet", type=Path)
    group.add_argument("--install-sdk", action="store_true")
    parser.add_argument("--keep-sdk", action="store_true", help="retain only the SDK staged by this invocation")
    parser.add_argument("--keep-build-cache", action="store_true", help="retain generated obj/bin and private NuGet caches")
    args = parser.parse_args(argv)
    try:
        build(args)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Helper bootstrap stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
