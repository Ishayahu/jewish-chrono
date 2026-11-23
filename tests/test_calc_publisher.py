# VERSION: 2026-11-23T06:50:15.437+00:00
"""Tests for the configurable Calc -> encrypted finance dashboard publisher."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from finance import publish_from_calc as pub


class FakeReader:
    def __init__(self, path):
        self.path = path
        self.numbers = {}
        self.labels = {}
        for key, ref in pub.CELLS.items():
            self.numbers[ref] = 0.0
        self.numbers[pub.CELLS["usdDebt"]] = 29580.0
        self.numbers[pub.CELLS["rate"]] = 80.0
        self.numbers[pub.CELLS["familyDeficit"]] = 1128419.73
        self.numbers[pub.CELLS["deficit"]] = 85000.0
        for ref in pub.RUB_DEBTS.values():
            self.numbers[ref] = 2000.0
        for ref in pub.CHILDREN.values():
            self.numbers[ref] = 200.0
        for refs in pub.INSTALLMENTS.values():
            self.numbers[refs["count"]] = 2.0
            self.numbers[refs["payment"]] = 1000.0
        for i, cycle in enumerate(pub.CYCLES):
            self.labels[cycle["label"]] = f"Цикл {i+1}"
            self.numbers[cycle["income"]] = 50000.0
            self.numbers[cycle["expenses"]] = 30000.0
            for name in pub.BUDGET_ROWS:
                limit, spent = pub.budget_refs(name, i, cycle)
                self.numbers[limit] = 100.0
                self.numbers[spent] = 40.0

    def money(self, ref, label):
        return self.numbers[ref]

    def text(self, ref, label):
        return self.labels[ref]


class CalcPublishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "budget.ods"
        self.file.write_bytes(b"fixture for path timestamp")
        self.reader = FakeReader(self.file)

    def test_report_schema_three_cycles_and_no_duplicate_usd_reserve(self):
        result = pub.build_report(self.reader)
        self.assertEqual(len(result["cycles"]), 3)
        self.assertEqual(result["familyDeficit"], 1128419.73)
        self.assertEqual(result["deficit"], 85000.0)
        self.assertEqual(result["usdDebt"], 29580.0)
        self.assertEqual(result["day"]["target"], 0)
        self.assertEqual(result["cycles"][0]["expenses"], 30000)
        self.assertEqual(len(result["cycles"][0]["budgets"]), len(pub.BUDGET_ROWS))
        subs = next(item for item in result["cycles"][0]["budgets"] if item["name"] == "Подписки (USD-резерв)")
        self.assertEqual(subs["limit"], 100.0)
        self.assertIsNone(subs["spent"])
        self.assertTrue(subs["informational"])

    def test_budget_limits_cannot_exceed_expense_plan(self):
        self.reader.numbers[pub.CYCLES[0]["expenses"]] = 1000.0
        with self.assertRaises(pub.ConfigError):
            pub.build_report(self.reader)

    def test_unclassified_expenses_are_not_discarded(self):
        self.reader.numbers[pub.CELLS["unmappedTotal"]] = 350.0
        result = pub.build_report(self.reader)
        self.assertEqual(result["cycles"][0]["unmappedExpenses"][0]["amount"], 350.0)
        self.assertEqual(result["cycles"][1]["unmappedExpenses"], [])

    def test_ciphertext_format_compatible_with_dashboard(self):
        sample = {"asOf": "23.11.2026 09:00 МСК", "cycle": None}
        payload = json.loads(pub.encrypt_report(sample, "long-test-password-2026"))
        self.assertEqual(payload["v"], 1)
        self.assertEqual(payload["iterations"], 600000)
        salt = base64.b64decode(payload["salt"])
        iv = base64.b64decode(payload["iv"])
        key = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000
        ).derive(b"long-test-password-2026")
        recovered = AESGCM(key).decrypt(iv, base64.b64decode(payload["ciphertext"]), None)
        self.assertEqual(json.loads(recovered), sample)

    def test_refuses_publishing_while_google_builder_is_active(self):
        with mock.patch.object(pub, "github_json", return_value={
            "content": base64.b64encode(b"python finance/build_encrypted.py").decode()
        }):
            with self.assertRaises(pub.ConfigError):
                pub.require_switched_workflow("fake-token")


if __name__ == "__main__":
    unittest.main()
