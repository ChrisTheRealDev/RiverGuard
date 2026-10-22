import tempfile
import unittest
from pathlib import Path
from release_v2_preview import allowed, stage


class PreviewTests(unittest.TestCase):
    def test_private_and_build_files_never_allowed(self):
        for name in ("v2/data/v2.db", "v2/data/v2-owner-link.html", "v2/frontend/node_modules/pkg/index.js",
                     "v2/hardware/firmware/include/station_config.h", "v2/mobile/android/local.properties",
                     "v2/mobile/android/app/build/output.apk", "v2/mobile/android/signing.properties",
                     "v2/mobile/android/private.keystore", "v2/server/__pycache__/x.py",
                     "v2/mobile/web/logs/error.log", "v2/../secret.md", "/v2/README.md", "v2/mobile/android/other.jar"):
            with self.subTest(name=name):
                self.assertFalse(allowed(name))

    def test_runtime_and_developer_sources_allowed(self):
        for name in ("v2/mobile/web/assets/index-final.js", "v2/mobile/web/guides/RiverGuard-Wiring.svg",
                     "v2/server/app.py", "v2/tests/test_repairs.py", "v2/requirements-lock.txt",
                     "v2/hardware/firmware/include/station_config.example.h",
                     "v2/mobile/android/app/src/androidTest/java/com/riverguard/v2/PhoneStoreRepairTest.java",
                     "v2/mobile/android/gradle/wrapper/gradle-wrapper.jar", "v2/mobile/android/gradlew"):
            with self.subTest(name=name):
                self.assertTrue(allowed(name))

    def test_missing_required_assets_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "v2").mkdir()
            with self.assertRaises(ValueError):
                stage(root, root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
