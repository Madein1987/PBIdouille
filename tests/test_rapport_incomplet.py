from pathlib import Path
import json
import sys
import tempfile
import unittest

racine = Path(__file__).resolve().parents[1] / "bidouille"
sys.path[:0] = [str(racine), str(racine / "moteurs")]

import unused_measures as um
from unittest.mock import patch


class Lecture(unittest.TestCase):
    def test_usage_ou_erreur(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(um, "REPORT_DIR", Path(tmp)):
            visuel = Path(tmp) / "visual.json"
            visuel.write_text(json.dumps({"Measure": {"Property": "Total"}}), encoding="utf-8-sig")
            self.assertEqual(um.report_used({"Total"}), {"Total": ["visual.json"]})
            visuel.write_bytes(b"{")
            for analyser in (lambda: um.report_used({"Total"}), lambda: um.report_used_columns({("T", "X")})):
                with self.assertRaisesRegex(SystemExit, "visual.json"):
                    analyser()


if __name__ == "__main__":
    unittest.main()
