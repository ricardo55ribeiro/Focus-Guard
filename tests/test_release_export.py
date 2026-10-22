from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prepare_public_release import export, ROOT_FILES, EXTRA_FILES


class ReleaseExportTests(unittest.TestCase):
    def test_export_excludes_private_files_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            for name in (*ROOT_FILES, *EXTRA_FILES, "agent/main.py", "extension/background.js", "tests/test_example.py", "tools/example.py", ".github/workflows/checks.yml"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("public")
            private = (".git/config", "agent/config/settings.json", "agent/logs/session.json", "agent/debug/capture.py", "agent/__pycache__/main.pyc", ".env", "old-extension.zip", ".audit/report.txt", ".venv/secret.py")
            for name in private:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("private")
            destination = Path(temp) / "public"
            count = export(destination, root)
            self.assertGreater(count, 20)
            self.assertEqual((destination / "agent/main.py").read_text(), "public")
            for name in private:
                self.assertFalse((destination / name).exists(), name)
            self.assertEqual(sum(p.is_file() for p in destination.rglob("*")), count)
            with self.assertRaises(ValueError):
                export(destination, root)


if __name__ == "__main__":
    unittest.main()
