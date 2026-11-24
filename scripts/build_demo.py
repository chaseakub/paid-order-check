"""Build the public sample audits using the same checker shipped to agents."""
import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "paid-order-audit"
sys.path.insert(0, str(SKILL / "scripts"))
from check_orders import audit, instant


def read_rows(name):
    with (SKILL / "assets" / name).open(newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def scenario(key):
    payments = read_rows("payments.csv")
    orders = read_rows("orders.csv")
    if key == "order_found":
        orders.append(dict(order_ref="order-103", payment_id="demo-pay-103", total="53.00",
                           currency="USD", status="processing"))
    if key == "payment_refunded":
        payments[1]["refunded_amount"] = payments[1]["amount"]

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        write_rows(path / "payments.csv", payments)
        write_rows(path / "orders.csv", orders)
        result = audit(path / "payments.csv", path / "orders.csv", instant("2026-11-23T00:00:00Z"), 24)
    return {"payments": payments, "orders": orders, "report": result}


if __name__ == "__main__":
    cases = {key: scenario(key) for key in ("original", "order_found", "payment_refunded")}
    (ROOT / "docs" / "sample-audits.json").write_text(json.dumps(cases, indent=2) + "\n")
