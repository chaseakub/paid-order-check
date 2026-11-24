# Import native API exports

The local converter accepts Stripe Charges list pages and WooCommerce Orders v3 arrays. It makes no network requests. Use the official WooCommerce Stripe gateway, one live store per run, and complete exports. Every included capture must carry the matching Woo `site_url` in its Stripe metadata. If this metadata is absent, an operator can prepare the normalized CSVs after verifying the source store.

Supply all Stripe pages in API order, ending at `has_more: false`. The number of Woo rows across pages must equal the original query's `X-WP-Total`. Include cancelled, failed, pending and accepted orders and allow for orders created before payment. A count match cannot prove the dates or tenant were correct. Keep raw API exports outside the repository. They may include customer details. The two resulting CSV files contain only references, amounts, currencies, timestamp and statuses.

### Capture time and grace period

`Charge.created` can be the authorization time. The converter therefore uses **a verified upper bound** as the timestamp of every capture in the batch. For example, save last week's Stripe charges at 12:00 UTC, with their capture state present in that snapshot. Later export Woo orders at least the agreed grace interval after 12:00 UTC and reconfirm refund and dispute state before acting. Pass the Stripe snapshot time as `--captured-by` and the later snapshot time as `--as-of`. If your two snapshots were taken together, a positive grace period will conservatively defer every charge. For per-payment precision, map known capture event times into the normalized CSVs instead. Setting the bound to a historical cutoff requires evidence the charges were captured by then. The charge creation date alone cannot establish that.

### Run locally

From the installed skill directory, supply local paths and the two independently established timestamps. The parent of the new output directory must exist. The converter refuses to replace an existing directory.

```sh
python3 scripts/normalize_exports.py \
  --charges "$STRIPE_CHARGES_JSON" --orders "$WOO_ORDERS_JSON" \
  --site "$WOO_SITE_URL" --woo-total "$WOO_TOTAL" \
  --captured-by "$CAPTURES_CONFIRMED_BY" --out "$NEW_AUDIT_DIR"
python3 scripts/check_orders.py audit \
  --payments "$NEW_AUDIT_DIR/payments.csv" --orders "$NEW_AUDIT_DIR/orders.csv" \
  --as-of "$ORDER_SNAPSHOT_TIME" --grace-hours "$STORE_GRACE_HOURS"
```

The native adapter accepts USD, EUR, GBP, CAD, AUD, NZD and CHF in Stripe's minor units. Other currencies can be prepared explicitly in major units for the CSV checker. It uses the Woo order `number` and charge metadata `order_id` used by the official gateway, and reconciles Woo transaction or stored PaymentIntent identifiers to Stripe charge IDs when available. Webhook-only or partial records with missing refund/dispute evidence require operator review.

[Stripe Charge fields](https://docs.stripe.com/api/charges/object) · [WooCommerce Orders](https://woocommerce.github.io/woocommerce-rest-api-docs/#orders) · [Official gateway metadata](https://github.com/woocommerce/woocommerce-gateway-stripe/blob/develop/includes/abstracts/abstract-wc-stripe-payment-gateway.php)
