#!/usr/bin/env python3
"""Check local captured-payment and store-order exports. Uses Python 3.9+."""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

PAYMENTS = ("payment_id", "order_ref", "captured_at", "amount", "currency", "refunded_amount", "disputed")
ORDERS = ("order_ref", "payment_id", "total", "currency", "status")
AMOUNT = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z")
CURRENCY = re.compile(r"[A-Z]{3}\Z")
ASSETS = Path(__file__).resolve().parents[1] / "assets"


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def money(value):
    if not AMOUNT.fullmatch(value):
        raise ValueError("amounts must be nonnegative decimal numbers in major currency units")
    return Decimal(value)


def read_rows(path, fields):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = set(fields).difference(headers)
        if missing or len(headers) != len(set(headers)):
            raise ValueError(f"{path.name}: duplicate column names or missing columns {sorted(missing)}")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"{path.name} line {reader.line_num}: wrong number of columns")
            data = {key: row[key].strip() for key in fields}
            try:
                data["currency"] = data["currency"].upper()
                if not CURRENCY.fullmatch(data["currency"]):
                    raise ValueError("currency must be a three-letter code")
                if fields == PAYMENTS:
                    if not data["payment_id"]:
                        raise ValueError("payment_id is required")
                    data["captured_at"] = instant(data["captured_at"])
                    data["amount"] = money(data["amount"])
                    data["refunded_amount"] = money(data["refunded_amount"])
                    if data["refunded_amount"] > data["amount"] or data["amount"] == 0:
                        raise ValueError("invalid captured or refunded amount")
                    if data["disputed"].lower() not in ("true", "false"):
                        raise ValueError("disputed must be true or false")
                    data["disputed"] = data["disputed"].lower() == "true"
                else:
                    if not data["order_ref"] or not data["status"]:
                        raise ValueError("order_ref and status are required")
                    data["total"] = money(data["total"])
                    data["status"] = data["status"].lower().removeprefix("wc-")
            except ValueError as error:
                raise ValueError(f"{path.name} line {reader.line_num}: {error}") from error
            yield data


def audit(payments_path, orders_path, as_of, grace_hours):
    orders = list(read_rows(orders_path, ORDERS))
    payments = list(read_rows(payments_path, PAYMENTS))
    by_ref, by_payment = defaultdict(set), defaultdict(set)
    for pos, order in enumerate(orders):
        by_ref[order["order_ref"]].add(pos)
        if order["payment_id"]:
            by_payment[order["payment_id"]].add(pos)

    payment_ids = set()
    payment_refs = Counter()
    for payment in payments:
        refs = {orders[pos]["order_ref"] for pos in by_payment.get(payment["payment_id"], ())}
        if payment["order_ref"]:
            refs.add(payment["order_ref"])
        payment_refs.update(refs)
    counts, findings = Counter(), []
    cutoff = as_of - timedelta(hours=grace_hours)
    for payment in payments:
        pid, ref = payment["payment_id"], payment["order_ref"]
        if pid in payment_ids:
            raise ValueError("payment_id occurs twice; export one row per captured payment")
        payment_ids.add(pid)
        if payment["captured_at"] > as_of:
            raise ValueError("a captured payment is later than the snapshot time")
        candidates = by_ref.get(ref, set()) | by_payment.get(pid, set())
        order = orders[next(iter(candidates))] if len(candidates) == 1 else None
        outcome = classify(payment, ref, pid, candidates, order, payment_refs, cutoff)
        counts[outcome] += 1
        if outcome not in ("accepted_by_store", "within_grace_period"):
            findings.append({"payment_id": pid, "order_ref": ref or (order or {}).get("order_ref"),
                             "outcome": outcome, "order_status": order["status"] if order else None})
    return {"schema_version": 1, "as_of": as_of.isoformat(), "grace_hours": grace_hours,
            "payments_checked": len(payments), "orders_in_export": len(orders),
            "counts": dict(sorted(counts.items())), "findings": findings}


def classify(payment, ref, pid, candidates, order, payment_refs, cutoff):
    if payment["disputed"] or payment["refunded_amount"]:
        return "review_refund_or_dispute"
    if payment["captured_at"] > cutoff:
        return "within_grace_period"
    effective_ref = ref or (order["order_ref"] if order else "")
    if len(candidates) > 1 or (effective_ref and payment_refs[effective_ref] > 1):
        return "review_ambiguous_ids"
    if order is None:
        return "no_order_in_export" if ref else "review_missing_shared_reference"
    if ((ref and ref != order["order_ref"]) or
            (order["payment_id"] and order["payment_id"] != pid)):
        return "review_conflicting_ids"
    if payment["amount"] != order["total"] or payment["currency"] != order["currency"]:
        return "review_amount_or_currency"
    if order["status"] in ("cancelled", "canceled", "failed"):
        return "paid_order_cancelled_or_failed"
    if order["status"] in ("pending", "pending payment", "on-hold"):
        return "paid_order_still_pending"
    if order["status"] in ("processing", "completed"):
        return "accepted_by_store"
    return "review_order_status"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="audit bundled synthetic data")
    run = sub.add_parser("audit", help="audit one store using two local CSV exports")
    run.add_argument("--payments", type=Path, required=True)
    run.add_argument("--orders", type=Path, required=True)
    run.add_argument("--as-of", required=True, help="snapshot timestamp with UTC offset")
    run.add_argument("--grace-hours", type=int, default=24, help="hours allowed from capture")
    args = parser.parse_args()
    try:
        if args.command == "demo":
            result = audit(ASSETS / "payments.csv", ASSETS / "orders.csv", instant("2026-11-23T00:00:00Z"), 24)
        else:
            if args.grace_hours < 0:
                raise ValueError("--grace-hours must be nonnegative")
            result = audit(args.payments, args.orders, instant(args.as_of), args.grace_hours)
    except (OSError, ValueError, csv.Error, OverflowError) as error:
        parser.exit(2, f"Audit could not run: {error}\n")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
