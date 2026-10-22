import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from release_downloads import DownloadError, inspect_asset, stage_zip, verify_bytes


class ReleaseDownloadsTest(unittest.TestCase):
    def setUp(self):
        self.data = b"PK" + bytes(range(256)) * 600
        self.asset = {"id": "test", "tag": "preview.1", "filename": "RiverGuard-test.apk",
                      "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}
        self.calls = []

    def fetch(self, url, maximum, byte_range=None):
        self.calls.append((url, byte_range))
        info = {"status": 200, "content_type": "application/vnd.android.package-archive",
                "content_disposition": "attachment; filename=RiverGuard-test.apk", "content_range": ""}
        data = self.data
        if byte_range:
            start, end = byte_range.split("-")
            start, end = int(start), int(end) if end else len(data)-1
            data = data[start:end+1]
            info.update(status=206, content_range=f"bytes {start}-{end}/{len(self.data)}")
        return data, info

    def test_full_and_fresh_entry_resume_match(self):
        data, result = inspect_asset("owner/repo", self.asset, self.fetch)
        self.assertEqual(data, self.data)
        self.assertTrue(result["passed"])
        self.assertFalse(result["physical_android_browser_verified"])
        self.assertEqual([item[1] for item in self.calls], [None, "0-65535", "65536-"])
        self.assertEqual(len({item[0] for item in self.calls}), 1)
        self.assertIn("github.com/owner/repo/releases/download/preview.1/", self.calls[0][0])

    def test_wrong_size_is_failure(self):
        with self.assertRaisesRegex(DownloadError, "byte count"):
            verify_bytes(self.data[:-1], self.asset)

    def test_wrong_hash_is_failure(self):
        with self.assertRaisesRegex(DownloadError, "SHA-256"):
            verify_bytes(self.data[:-1] + b"X", self.asset)

    def test_ignored_range_is_not_reported_as_resume(self):
        def fetch(url, maximum, byte_range=None):
            data, info = self.fetch(url, maximum, byte_range)
            if byte_range:
                info["status"] = 200
            return data, info
        with self.assertRaisesRegex(DownloadError, "Resume not confirmed"):
            inspect_asset("owner/repo", self.asset, fetch)

    def test_wrong_resume_offset_is_failure(self):
        def fetch(url, maximum, byte_range=None):
            data, info = self.fetch(url, maximum, byte_range)
            if byte_range:
                info["content_range"] = "bytes 1-2/3"
            return data, info
        with self.assertRaisesRegex(DownloadError, "Content-Range"):
            inspect_asset("owner/repo", self.asset, fetch)

    def test_html_or_missing_attachment_rejected(self):
        for field, value in [("content_type", "text/html"), ("content_disposition", "")]:
            with self.subTest(field=field):
                def fetch(url, maximum, byte_range=None):
                    data, info = self.fetch(url, maximum, byte_range)
                    info[field] = value
                    return data, info
                with self.assertRaises(DownloadError):
                    inspect_asset("owner/repo", self.asset, fetch)

    def test_zip_contains_identical_apk_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            result = stage_zip(folder, self.asset, self.data)
            with zipfile.ZipFile(result["zip"]) as z:
                self.assertEqual(z.read(self.asset["filename"]), self.data)
                self.assertIn(self.asset["sha256"], z.read("SHA256SUMS.txt").decode())
                self.assertIsNone(z.testzip())
            self.assertEqual(Path(result["apk"]).read_bytes(), self.data)
            with self.assertRaisesRegex(DownloadError, "already exist"):
                stage_zip(folder, self.asset, self.data)

    def test_staging_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(DownloadError, "plain APK"):
                stage_zip(folder, self.asset | {"filename": "../bad.apk"}, self.data)


if __name__ == "__main__":
    unittest.main()
