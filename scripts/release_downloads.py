"""Anonymous, end-to-end release asset verification; no GitHub token required.

Fetch through the public release URL each time, including resume requests. Never
persist or print the signed CDN redirect URL. Optional staging creates a ZIP
containing the exact verified APK, without changing or re-signing it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
APK_TYPE = "application/vnd.android.package-archive"


class DownloadError(Exception):
    pass


class Redirects(HTTPRedirectHandler):
    def __init__(self):
        self.hosts: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original, destination = urlsplit(req.full_url), urlsplit(newurl)
        if original.scheme == "https" and destination.scheme != "https":
            raise DownloadError("Refusing an insecure download redirect.")
        self.hosts.append(destination.hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_url(repository, asset):
    return (f"https://github.com/{repository}/releases/download/"
            f"{quote(asset['tag'], safe='')}/{quote(asset['filename'], safe='')}")


def fetch(url, maximum, byte_range=None, timeout=45):
    # A fresh entry URL avoids replaying an expired, cached signed CDN redirect.
    separator = "&" if "?" in url else "?"
    fresh_url = url + separator + urlencode({"riverguard_check": uuid.uuid4().hex})
    headers = {"User-Agent": "RiverGuard-public-release-check/1", "Accept-Encoding": "identity",
               "Cache-Control": "no-cache"}
    if byte_range is not None:
        headers["Range"] = "bytes=" + byte_range
    redirects = Redirects()
    opener = build_opener(redirects)
    started = time.monotonic()
    with opener.open(Request(fresh_url, headers=headers), timeout=timeout) as response:
        chunks = bytearray()
        try:
            while len(chunks) <= maximum:
                chunk = response.read(min(65536, maximum + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
        except Exception as exc:
            chunks.extend(getattr(exc, "partial", b""))
            raise DownloadError(f"Transfer stopped after {len(chunks)} bytes ({type(exc).__name__}).") from None
        data = bytes(chunks)
        if len(data) > maximum:
            raise DownloadError("The server returned more bytes than the selected release allows.")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) != len(data):
            raise DownloadError(f"Incomplete transfer: expected {length} bytes; received {len(data)}.")
        info = {
            "status": response.status, "bytes": len(data),
            "content_type": response.headers.get_content_type(),
            "content_length": length,
            "content_disposition": response.headers.get("Content-Disposition", ""),
            "accept_ranges": response.headers.get("Accept-Ranges", ""),
            "content_range": response.headers.get("Content-Range", ""),
            "redirect_hosts": redirects.hosts,
            "destination_host": urlsplit(response.url).hostname,
            "seconds": round(time.monotonic() - started, 3),
        }
        return data, info


def verify_bytes(data, asset):
    if len(data) != asset["size"]:
        raise DownloadError(f"Wrong byte count: {len(data)}; expected {asset['size']}.")
    digest = hashlib.sha256(data).hexdigest()
    if digest != asset["sha256"]:
        raise DownloadError("SHA-256 does not match the release manifest.")
    if not data.startswith(b"PK"):
        raise DownloadError("The download is not an APK/ZIP archive.")
    return digest


def verify_range(info, start, end, total):
    expected = f"bytes {start}-{end}/{total}"
    if info["status"] != 206 or info["content_range"] != expected:
        raise DownloadError(f"Resume not confirmed: expected HTTP 206 and Content-Range {expected}.")


def inspect_asset(repository, asset, fetcher=fetch):
    url = public_url(repository, asset)
    data, full = fetcher(url, asset["size"])
    digest = verify_bytes(data, asset)
    if full["status"] != 200 or full["content_type"] not in (APK_TYPE, "application/octet-stream"):
        raise DownloadError("The full transfer did not return a downloadable APK response.")
    disposition = full["content_disposition"]
    if not disposition.lower().startswith("attachment") or asset["filename"] not in disposition:
        raise DownloadError("Missing or unexpected attachment filename.")
    split = min(65536, max(1, asset["size"] // 2))
    prefix, first = fetcher(url, split, f"0-{split-1}")
    verify_range(first, 0, split-1, asset["size"])
    suffix, resumed = fetcher(url, asset["size"] - split, f"{split}-")
    verify_range(resumed, split, asset["size"]-1, asset["size"])
    verify_bytes(prefix + suffix, asset)
    return data, {"id": asset["id"], "filename": asset["filename"], "url": url,
                  "sha256": digest, "full": full, "partial": first,
                  "resumed": resumed, "passed": True,
                  "physical_android_browser_verified": False}


def stage_zip(directory, asset, data):
    verify_bytes(data, asset)
    name = asset["filename"]
    if Path(name).name != name or not re.fullmatch(r"[A-Za-z0-9._-]+\.apk", name):
        raise DownloadError("Use a plain APK filename for staging.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    apk = directory / name
    archive = directory / (name[:-4] + "-download.zip")
    if apk.exists() or archive.exists():
        raise DownloadError("Staging files already exist; choose a new directory to preserve previous artifacts.")
    apk.write_bytes(data)
    checksum = f"{asset['sha256']}  {name}\n"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, data)
        z.writestr("SHA256SUMS.txt", checksum)
        z.writestr("INSTALL.txt", "Extract the APK, then open it in Android Files.\n"
                   "This is the original signed APK, unchanged. Updating a standalone installation\n"
                   "must not require uninstalling it; uninstalling removes saved phone data.\n")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or z.read(name) != data:
            raise DownloadError("ZIP verification failed.")
    return {"apk": str(apk), "zip": str(archive), "zip_size": archive.stat().st_size,
            "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/downloads.json")
    parser.add_argument("--asset", action="append", help="Manifest ID; repeat for multiple assets. Default: all.")
    parser.add_argument("--release-tag", help="Require and verify this exact published tag in the manifest.")
    parser.add_argument("--report", type=Path, help="Write non-secret transfer evidence JSON.")
    parser.add_argument("--stage", type=Path, help="Save verified APKs and ZIP alternatives in a new staging directory.")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    assets = [a for a in manifest["assets"] if (args.asset is None or a["id"] in args.asset)
              and (args.release_tag is None or a["tag"] == args.release_tag)]
    if not assets:
        parser.error("No manifest assets match. Add the exact published release's build size/hash before accepting it.")
    if args.asset and set(args.asset) - {a["id"] for a in assets}:
        parser.error("Unknown asset ID.")
    results = []
    for asset in assets:
        try:
            data, result = inspect_asset(manifest["repository"], asset)
            if args.stage:
                result["staged"] = stage_zip(args.stage, asset, data)
        except Exception as exc:
            # Exception strings from urllib may contain signed redirect URLs. Do not log them.
            result = {"id": asset["id"], "passed": False, "error_type": type(exc).__name__,
                      "error": str(exc) if isinstance(exc, DownloadError) else "Transfer failed; retry from the public release URL. No signed URL or credentials were logged."}
            if isinstance(exc, HTTPError):
                result["http_status"] = exc.code
        results.append(result)
        print(json.dumps(result), flush=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"assets": results}, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
