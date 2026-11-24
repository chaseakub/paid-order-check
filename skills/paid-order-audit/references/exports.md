# Export contract

Prepare CSV files with a header row. Keep one live store, one processor account and one snapshot per run. Use a sufficiently wide order snapshot to include orders created before capture or after checkout. Compare UTC times with the store's actual delay. The default grace period is 24 hours. A header-only export is valid, but verify completeness before interpreting its results.

## Payments

Supply one row per successfully **captured** payment. Exclude authorizations, failed attempts and test payments. Use the gross amount captured, including any portion later refunded. The amount and refund columns use major currency units, plain decimal notation, and no thousands separators. Use the actual capture time. Do not use a checkout creation time for a delayed capture.

| Column | Value |
| --- | --- |
| payment_id | Unique processor reference. Retain the same ID format in the order export. |
| order_ref | Store order reference recorded by the processor, or empty if unavailable. Preserve leading zeroes and order-number prefixes. |
| captured_at | Timestamp with offset, such as 2026-11-17T10:00:00Z. |
| amount | Gross captured amount, such as 26.00 for USD 26. |
| currency | Three-letter currency code. |
| refunded_amount | Verified refunded amount in the same units and currency. Use 0 for a known zero. |
| disputed | true or false, per the processor. |

## Orders

Use one row per store order, including cancelled and pending orders. Line-item exports must first be aggregated by order. Duplicate order references are reviewed as ambiguous.

| Column | Value |
| --- | --- |
| order_ref | Stable store order reference in the same numbering scheme as the payment export. |
| payment_id | Exact processor reference if known. Empty is allowed. |
| total | Order total in major currency units. |
| currency | Three-letter currency code. |
| status | Store's status. Processing and completed count as accepted. Pending, pending payment and on-hold are checked after the grace period. Cancelled, canceled and failed are flagged for review. Other states are referred to the operator. |

Matching uses exact, case-sensitive identifiers after trimming surrounding spaces. An order can match by its reference or its payment ID. Conflicting keys, multiple captures against an order, currency differences, partial refunds and disputes require human review. Export only the fields above. Consistently pseudonymized identifiers work.

The report contains exception references and reasons. It is not a shipping confirmation or a calculation of lost revenue. The samples in the skill's assets directory contain invented data.
