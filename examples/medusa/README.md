# Check a captured Stripe payment against Medusa orders

These three captured payments and two orders are invented. The CSVs are already mapped to Paid Order Check's input columns. Run from the repository root with Python 3.9 or newer.

```sh
python3 skills/paid-order-audit/scripts/check_orders.py audit \
  --payments examples/medusa/payments.csv --orders examples/medusa/orders.csv \
  --as-of 2026-11-23T00:00:00Z --grace-hours 24
```

| Capture reference | What the sample shows | Checker result |
| --- | --- | --- |
| medusa-pay-01 | The order is cancelled and the payment export shows a capture with zero refunded. | paid_order_cancelled_or_failed |
| medusa-pay-02 | The expected order reference is absent from the supplied order export. | no_order_in_export |
| medusa-pay-03 | The order is in Medusa's pending order state. The data does not establish fulfillment. | review_order_status |

For a merchant pilot, start from verified captures for one live store. Use a stable processor payment or charge reference shared with the order, or an order reference attached to the payment. A cart ID needs a verified cart-to-order mapping. When there's no shared key, keep the order reference blank and let the checker refer the record to a human. Amount and time alone cannot identify an order.

Medusa keeps order, payment, and fulfillment statuses separately. Preserve its generic pending order state as a custom value such as `medusa_pending` so the checker returns `review_order_status`. In the example, a known cancelled order maps to `cancelled`. If you need to verify shipment, check the fulfillment record. The bundled native JSON importer handles Stripe and WooCommerce. Medusa users prepare the normalized CSVs, including capture time, refund and dispute information from their processor.

[Export fields](../../skills/paid-order-audit/references/exports.md) · [Medusa order states](https://docs.medusajs.com/resources/references/order/types/order.OrderStatus)
