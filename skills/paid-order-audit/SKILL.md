---
name: paid-order-audit
description: Reconcile captured Stripe payments with WooCommerce order exports to find missing orders, paid but cancelled or failed orders, and paid orders stuck pending. Run an offline audit and return exact references for human review.
license: MIT
---

# Paid order audit

Run the bundled Python 3.9+ checker relative to this skill directory. It uses the standard library and outputs JSON.

- For a demo, run `python3 scripts/check_orders.py demo`. The three records are synthetic.
- For a real audit, use local exports for the same store, processor account and snapshot. [Export fields and supported statuses](references/exports.md) lists the required columns. If working with native Stripe Charges and WooCommerce REST order JSON, see [normalizing API exports](references/native-exports.md).
- Run `python3 scripts/check_orders.py audit --payments payments.csv --orders orders.csv --as-of SNAPSHOT_TIME --grace-hours HOURS` with actual paths, the snapshot time including its UTC offset, and the store's normal time allowance. Missing fields or inconsistent inputs produce exit 2. Findings produce exit 0 and appear in the JSON.
- Report the audited counts, the payment or order reference for each exception and the next record the operator should check. A payment with no visible order is a candidate for review until the operator verifies account and export coverage. `accepted_by_store` does not establish delivery.
- Leave order and payment decisions to the merchant. If they want to share pilot feedback, ask for aggregate results and keep raw exports and customer details local.
