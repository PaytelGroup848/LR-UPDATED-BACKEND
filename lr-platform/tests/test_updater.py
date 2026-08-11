import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from updater.main import _replace_file


class UpdaterReplacementTests(unittest.TestCase):
    def test_replaces_target_and_removes_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "download.exe"
            target = root / "client.exe"
            source.write_bytes(b"new")
            target.write_bytes(b"old")

            _replace_file(source, target)

            self.assertEqual(target.read_bytes(), b"new")
            self.assertFalse(source.exists())
            self.assertEqual(list(root.glob("client.exe.*.old")), [])

    def test_locked_backup_cleanup_does_not_fail_completed_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "download.exe"
            target = root / "client.exe"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            original_unlink = Path.unlink

            def locked_backup(path, *args, **kwargs):
                if path.name.endswith(".old"):
                    error = PermissionError(5, "Access is denied", str(path))
                    error.winerror = 5
                    raise error
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", locked_backup):
                _replace_file(source, target)

            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual(len(list(root.glob("client.exe.*.old"))), 1)


if __name__ == "__main__":
    unittest.main()
