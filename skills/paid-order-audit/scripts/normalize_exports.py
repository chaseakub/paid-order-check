#!/usr/bin/env python3
"""Convert saved Stripe Charge and WooCommerce order pages into two local audit CSVs."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from check_orders import ORDERS, PAYMENTS, instant, money

TWO_DECIMAL = {"USD", "EUR", "GBP", "CAD", "AUD", "NZD", "CHF"}


def site_key(value):
    if not isinstance(value, str):
        raise ValueError("charge is missing site_url metadata")
    uri = urlsplit(value)
    if uri.scheme not in {"http", "https"} or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
        raise ValueError("site URL must identify the store's exact origin and path")
    return uri.scheme.lower(), uri.hostname.lower(), uri.port, uri.path.rstrip("/")


def required_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {field}")
    return value.strip()


def minor_amount(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative Stripe amount in minor units")
    return f"{value // 100}.{value % 100:02d}"


def stripe_rows(paths, site, captured_by):
    aliases, seen, payments = {}, set(), []
    for page_no, path in enumerate(paths, 1):
        page = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(page, dict) or page.get("object") != "list" or not isinstance(page.get("data"), list):
            raise ValueError("expected unmodified Stripe list pages from /v1/charges")
        if page.get("has_more") is not (page_no < len(paths)):
            raise ValueError("Stripe pagination is incomplete or pages are out of order")
        for charge in page["data"]:
            if not isinstance(charge, dict) or charge.get("object") != "charge" or charge.get("livemode") is not True:
                raise ValueError("expected only live Stripe Charge objects")
            pid = required_string(charge.get("id"), "charge.id")
            if pid in seen:
                raise ValueError("duplicate charge across input pages")
            seen.add(pid)
            if charge.get("status") not in ("succeeded", "failed", "pending") or type(charge.get("captured")) is not bool:
                raise ValueError("missing or invalid charge status or captured flag")
            if not charge["captured"] or charge["status"] != "succeeded":
                continue
            if charge.get("paid") is not True or type(charge.get("disputed")) is not bool:
                raise ValueError("cannot verify charge paid/disputed state")
            metadata = charge.get("metadata")
            if not isinstance(metadata, dict) or site_key(metadata.get("site_url")) != site:
                raise ValueError("charge lacks matching site_url metadata; supply a single verified store export")
            currency = required_string(charge.get("currency"), "charge.currency").upper()
            if currency not in TWO_DECIMAL:
                raise ValueError(f"native converter has no verified minor-unit mapping for {currency}")
            gross, refunded = charge.get("amount_captured"), charge.get("amount_refunded")
            gross_text, refund_text = minor_amount(gross), minor_amount(refunded)
            if not gross or refunded > gross:
                raise ValueError("inconsistent capture/refund amounts")
            created = charge.get("created")
            if type(created) is not int or datetime.fromtimestamp(created, timezone.utc) > captured_by:
                raise ValueError("charge creation exceeds the supplied capture bound or is invalid")
            pi = charge.get("payment_intent")
            if isinstance(pi, dict):
                pi = pi.get("id")
            if pi:
                pi = required_string(pi, "payment_intent")
                if pi in aliases:
                    raise ValueError("multiple captured charges for one PaymentIntent need manual mapping")
                aliases[pi] = pid
            order_ref = metadata.get("order_id", "")
            if not isinstance(order_ref, str):
                raise ValueError("invalid Stripe order_id metadata")
            payments.append((pid, order_ref, captured_by.isoformat(), gross_text, currency,
                             refund_text, str(charge["disputed"]).lower()))
    return payments, aliases


def woo_rows(paths, aliases):
    orders, seen = [], set()
    for path in paths:
        page = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(page, list):
            raise ValueError("expected an array from the WooCommerce orders API")
        for order in page:
            if not isinstance(order, dict) or type(order.get("id")) is not int or order["id"] <= 0 or order["id"] in seen:
                raise ValueError("missing or duplicate Woo order id")
            seen.add(order["id"])
            number = required_string(order.get("number"), "order.number")
            status = required_string(order.get("status"), "order.status")
            cur = required_string(order.get("currency"), "order.currency").upper()
            if len(cur) != 3 or not cur.isascii() or not cur.isalpha():
                raise ValueError("invalid Woo currency")
            total = required_string(order.get("total"), "order.total")
            money(total)
            txn = order.get("transaction_id")
            if not isinstance(txn, str):
                raise ValueError("invalid Woo transaction_id; retain blank strings in the export")
            ids = {aliases.get(txn, txn)} if txn else set()
            meta = order.get("meta_data", [])
            if not isinstance(meta, list) or any(not isinstance(item, dict) for item in meta):
                raise ValueError("invalid Woo meta_data")
            for item in meta:
                if item.get("key") == "_stripe_intent_id" and item.get("value"):
                    intent = required_string(item["value"], "_stripe_intent_id")
                    if intent in aliases or not txn:
                        ids.add(aliases.get(intent, intent))
            if len(ids) > 1:
                raise ValueError("Woo order transaction and captured PaymentIntent identify different payments; review these IDs")
            orders.append((number, next(iter(ids), ""), total, cur, status))
    return orders


def convert(charges, orders, site, captured_by, output, expected_orders):
    if output.exists() or output.is_symlink():
        raise ValueError("output directory already exists; use a new path")
    payments, aliases = stripe_rows(charges, site_key(site), instant(captured_by))
    store_orders = woo_rows(orders, aliases)
    if len(store_orders) != expected_orders:
        raise ValueError("Woo order count differs from --woo-total; check pagination")
    with TemporaryDirectory(dir=output.parent) as temp:
        files = []
        for filename, header, rows in (("payments.csv", PAYMENTS, payments), ("orders.csv", ORDERS, store_orders)):
            path = Path(temp) / filename
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(rows)
            files.append(path)
        output.mkdir(mode=0o700)  # Reserve exclusively, including against concurrent runs.
        moved = []
        try:
            for path in files:
                dest = output / path.name
                path.rename(dest)
                moved.append(dest)
        except OSError:
            for dest in moved:
                dest.unlink()
            output.rmdir()
            raise
    return len(payments), len(store_orders)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charges", type=Path, nargs="+", required=True)
    parser.add_argument("--orders", type=Path, nargs="+", required=True)
    parser.add_argument("--site", required=True, help="Woo site_url in the payment metadata")
    parser.add_argument("--woo-total", type=int, required=True, help="X-WP-Total for this exact orders query")
    parser.add_argument("--captured-by", required=True, help="verified latest time by which all listed captures had happened")
    parser.add_argument("--out", type=Path, required=True, help="new local output directory")
    args = parser.parse_args()
    try:
        n, m = convert(args.charges, args.orders, args.site, args.captured_by, args.out, args.woo_total)
    except (OSError, ValueError, OverflowError) as error:
        parser.exit(2, f"Conversion stopped: {error}\n")
    print(f"Prepared {n} captured payments and {m} orders.")


if __name__ == "__main__":
    main()
