"""Stage a source/laptop V2 repair preview using an explicit public-file allowlist.

Does not build, publish, modify V1, or include installation data/signing material.
Run from any directory with Python 3.14 (standard library only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

VERSION = "v2-repair-preview.2026-10-22.2"
EXACT = {
    "v2/serve.py", "v2/requirements-lock.txt",
    "v2/Setup RiverGuard V2.cmd", "v2/Start RiverGuard V2.cmd",
    "v2/frontend/index.html", "v2/frontend/package.json", "v2/frontend/package-lock.json",
    "v2/frontend/tsconfig.json", "v2/frontend/vite.config.ts",
    "v2/mobile/package.json", "v2/mobile/package-lock.json", "v2/mobile/capacitor.config.json",
    "v2/hardware/firmware/platformio.ini",
    "v2/hardware/firmware/include/station_config.example.h",
    "v2/hardware/firmware/include/retry_deadline.h",
    "hardware/README.md", "hardware/Tank-Assembly.md",
    "hardware/Tank-Layout.svg", "hardware/RiverGuard-Wiring.svg",
    "output/pdf/RiverGuard-Friend-Setup.pdf",
    "scripts/release_v2_preview.py", "scripts/release_v2_preview_test.py",
    "scripts/release_downloads.py", "scripts/release_downloads_test.py",
    "docs/ANDROID-DOWNLOADS.md", "docs/downloads-repair-evidence.md", "docs/downloads.json",
}
TREES = {
    "v2/server/": {".py"}, "v2/tests/": {".py", ".json"},
    "v2/frontend/src/": {".ts", ".tsx", ".js", ".css"},
    "v2/frontend/tests/": {".cjs"},
    "v2/frontend/public/": {".png", ".svg", ".pdf"},
    "v2/mobile/web/": {".html", ".js", ".css", ".png", ".svg", ".pdf"},
    "v2/mobile/scripts/": {".cjs"},
    "v2/mobile/android/app/src/main/java/": {".java"},
    "v2/mobile/android/app/src/main/res/": {".xml", ".png"},
    "v2/mobile/android/app/src/test/": {".java"},
    "v2/mobile/android/app/src/androidTest/": {".java"},
    "v2/hardware/firmware/src/": {".cpp", ".h"},
    "v2/hardware/firmware/test/": {".cpp", ".h"},
}
EXACT.update("v2/mobile/android/" + p for p in (
    "build.gradle", "settings.gradle", "variables.gradle", "gradle.properties",
    "capacitor.settings.gradle", "app/build.gradle", "app/capacitor.build.gradle",
    "app/proguard-rules.pro", "app/src/main/AndroidManifest.xml",
    "gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.properties",
    "gradle/wrapper/gradle-wrapper.jar",
))
BLOCKED_PARTS = {"node_modules", "__pycache__", ".venv", ".git", ".gradle", ".pio", "build", "data", "logs", ".pytest_cache"}
BLOCKED_NAMES = {"station_config.h", "local.properties", "key.properties", "signing.properties", "v2-owner-link.html"}


def allowed(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    if any(p.lower() in BLOCKED_PARTS for p in path.parts) or path.name.lower() in BLOCKED_NAMES:
        return False
    if name == "v2/mobile/android/gradle/wrapper/gradle-wrapper.jar":
        return True
    if path.suffix.lower() in {".apk", ".db", ".sqlite", ".sqlite3", ".log", ".jks", ".keystore", ".pem", ".key", ".jar"}:
        return False
    if name in EXACT:
        return True
    if path.suffix == ".md" and str(path.parent) in {"v2", "v2/mobile", "v2/hardware"}:
        return True
    return any(name.startswith(prefix) and path.suffix in extensions for prefix, extensions in TREES.items())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(root: Path, output: Path, version: str = VERSION) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", version):
        raise ValueError("Use a simple version identifier.")
    files = {}
    for path in (root / "v2").rglob("*"):
        name = path.relative_to(root).as_posix()
        if path.is_file() and allowed(name):
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Refusing symlink/outside source: " + name)
            files[name] = path.read_bytes()
    for name in EXACT:
        path = root / name
        if path.is_file():
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Refusing symlink/outside source: " + name)
            files[name] = path.read_bytes()
    required = {"v2/mobile/web/index.html", "v2/serve.py", "v2/requirements-lock.txt", "v2/Setup RiverGuard V2.cmd", "v2/Start RiverGuard V2.cmd", "v2/REPAIR-CLOSURE.md", "v2/RELEASE-NOTES-REPAIR.md", "output/pdf/RiverGuard-Friend-Setup.pdf"}
    if missing := required - files.keys():
        raise ValueError("Missing required files: " + ", ".join(sorted(missing)))
    html = files["v2/mobile/web/index.html"].decode()
    for asset in re.findall(r'''(?:src|href)=["'](/assets/[^"']+)["']''', html):
        if "v2/mobile/web" + asset not in files:
            raise ValueError("Compiled index references a missing asset: " + asset)
    if not any(n.startswith("v2/mobile/web/assets/") and n.endswith(".js") for n in files):
        raise ValueError("Compiled frontend bundle missing")
    manifest = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items()))
    files["SHA256SUMS.txt"] = manifest.encode()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"RiverGuard-{version}.zip"
    if target.exists():
        raise FileExistsError("Preserve prior artifact; choose another output/version: " + str(target))
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        for name, data in files.items():
            if archive.read(name) != data:
                raise ValueError("ZIP content mismatch: " + name)
            if name != "SHA256SUMS.txt" and not allowed(name):
                raise ValueError("Unexpected private/nonallowlisted file: " + name)
    result = {"version": version, "filename": target.name, "bytes": target.stat().st_size,
              "sha256": digest(target.read_bytes()), "files": len(files), "zip_integrity": "passed",
              "allowlist_check": "passed", "compiled_assets": sorted(n for n in files if n.startswith("v2/mobile/web/assets/")),
              "apk_included": False, "published": False}
    (output / (target.name + ".sha256")).write_text(f"{result['sha256']}  {target.name}\n", encoding="utf-8")
    (output / (target.name + ".verification.json")).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    print(json.dumps(stage(args.root.resolve(), args.output.resolve(), args.version), indent=2))
