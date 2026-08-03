import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web


class TelegramAccessTests(unittest.TestCase):
    def test_load_allowed_ids_from_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("123\n456\n# comment\n")
            temp_path = handle.name

        try:
            self.assertEqual(web.load_allowed_telegram_ids(temp_path), [123, 456])
        finally:
            os.remove(temp_path)

    def test_is_allowed_returns_true_for_allowed_id(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("1001\n")
            temp_path = handle.name

        try:
            self.assertTrue(web.is_telegram_user_allowed(1001, temp_path))
            self.assertFalse(web.is_telegram_user_allowed(9999, temp_path))
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
