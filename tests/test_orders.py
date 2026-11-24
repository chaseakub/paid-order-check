import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/paid-order-audit/scripts"
sys.path.insert(0, str(SCRIPTS))
import check_orders as checker

NOW = checker.instant("2026-11-23T00:00:00Z")
PAYMENT = dict(payment_id="payment1", order_ref="order1", amount="12.00", currency="USD",
               captured_at="2026-11-19T00:00:00Z", refunded_amount="0", disputed="false")
ORDER = dict(order_ref="order1", payment_id="payment1", total="12.00", currency="USD", status="completed")


class AuditTests(unittest.TestCase):
    def audit(self, payments, orders):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, fields, records in (("payments", checker.PAYMENTS, payments), ("orders", checker.ORDERS, orders)):
                path = Path(directory, name + ".csv")
                with path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(records)
                paths.append(path)
            return checker.audit(*paths, NOW, 24)

    def test_installed_demo(self):
        process = subprocess.run([sys.executable, str(SCRIPTS / "check_orders.py"), "demo"],
                                 cwd=tempfile.gettempdir(), check=True, capture_output=True, text=True)
        result = json.loads(process.stdout)
        self.assertEqual(result["counts"], {"accepted_by_store": 1, "no_order_in_export": 1,
                                            "paid_order_cancelled_or_failed": 1})
        self.assertEqual(len(result["findings"]), 2)

    def test_states_and_exceptions(self):
        for changes, order_changes, expected in (
            ({}, {"status": "wc-on-hold"}, "paid_order_still_pending"),
            ({}, {"status": "shipped"}, "review_order_status"),
            ({}, {"total": "12.01"}, "review_amount_or_currency"),
            ({}, {"currency": "CAD"}, "review_amount_or_currency"),
            ({"refunded_amount": "2.00"}, {"status": "cancelled"}, "review_refund_or_dispute"),
            ({"disputed": "true"}, {}, "review_refund_or_dispute"),
            ({"captured_at": "2026-11-22T22:00:00Z"}, {"status": "pending"}, "within_grace_period"),
            ({"order_ref": ""}, {}, "accepted_by_store"),
            ({}, {"payment_id": "other"}, "review_conflicting_ids"),
        ):
            with self.subTest(expected=expected):
                r = self.audit([dict(PAYMENT, **changes)], [dict(ORDER, **order_changes)])
                self.assertEqual(r["counts"], {expected: 1})

    def test_ambiguous_and_unlinked(self):
        self.assertEqual(self.audit([PAYMENT], [ORDER, ORDER])["counts"], {"review_ambiguous_ids": 1})
        self.assertEqual(self.audit([dict(PAYMENT, order_ref="")], [])["counts"],
                         {"review_missing_shared_reference": 1})
        r = self.audit([dict(PAYMENT, order_ref=""), dict(PAYMENT, payment_id="p2")], [ORDER])
        self.assertEqual(r["counts"], {"review_ambiguous_ids": 2})

    def test_duplicate_and_future_charges_stop_report(self):
        with self.assertRaisesRegex(ValueError, "twice"):
            self.audit([PAYMENT, PAYMENT], [])
        for bad in ({"captured_at": "2031-01-01T12:00:00Z"}, {"captured_at": "2026-10-10"},
                    {"refunded_amount": ""}, {"disputed": ""}, {"amount": "NaN"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.audit([dict(PAYMENT, **bad)], [ORDER])

    def test_invalid_cli_input_never_returns_clean_audit(self):
        process = subprocess.run([sys.executable, str(SCRIPTS / "check_orders.py"), "audit",
                                  "--payments", "unknown", "--orders", "unknown", "--as-of", NOW.isoformat()],
                                 cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
