import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/paid-order-audit/scripts"
sys.path.insert(0, str(SCRIPTS))
from normalize_exports import convert


class NativeImportTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.out = self.root / "normalized"
        self.site = "https://woo.example"
        self.bound = "2026-05-01T00:00:00+00:00"
        self.charge = dict(id="ch_test", object="charge", livemode=True, status="succeeded", captured=True,
                           paid=True, disputed=False, currency="usd", amount_captured=2099, amount_refunded=0,
                           created=1750000000, metadata=dict(site_url=self.site, order_id="K10"),
                           payment_intent="pi_test", billing_details={"name":"CUSTOMER PII"})
        self.order = dict(id=10, number="K10", status="cancelled", total="20.99", currency="USD",
                          transaction_id="", meta_data=[dict(key="_stripe_intent_id", value="pi_test")])

    def run_case(self, more=False):
        charges, orders = self.root/"charges.json", self.root/"orders.json"
        charges.write_text(json.dumps(dict(object="list",has_more=more,data=[self.charge])))
        orders.write_text(json.dumps([self.order]))
        return convert([charges], [orders], self.site, self.bound, self.out, 1)

    def test_reference_capture_bound_and_no_personal_fields(self):
        self.assertEqual(self.run_case(), (1,1))
        with (self.out/"payments.csv").open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual((row["amount"],row["captured_at"],row["order_ref"]),("20.99",self.bound,"K10"))
        self.assertNotIn("CUSTOMER PII", (self.out/"payments.csv").read_text())
        self.assertIn("ch_test", (self.out/"orders.csv").read_text())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_case()

    def test_wrong_site_and_incomplete_pagination(self):
        with self.assertRaisesRegex(ValueError,"pagination"):
            self.run_case(True)
        self.charge["metadata"]["site_url"] = "https://other.example"
        with self.assertRaisesRegex(ValueError,"site_url"):
            self.run_case()
        self.assertFalse(self.out.exists())

    def test_no_guess_when_dispute_flag_absent(self):
        self.charge.pop("disputed")
        with self.assertRaisesRegex(ValueError,"disputed"):
            self.run_case()
        self.assertFalse(self.out.exists())

    def test_decline_is_skipped(self):
        self.charge.update(status="failed",captured=False,paid=False)
        self.assertEqual(self.run_case(),(0,1))
