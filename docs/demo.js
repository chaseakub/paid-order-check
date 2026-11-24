"use strict";

const copy = {
  paid_order_cancelled_or_failed: {
    short: "Paid · cancelled",
    title: "The money matches. The order was cancelled.",
    next: "Check the order notes and any refund before the team decides how to help the customer."
  },
  no_order_in_export: {
    short: "Order missing",
    title: "The payment has no order in this export.",
    next: "Verify the store, dates and references in the original systems. An absent row alone cannot establish a lost sale."
  },
  review_refund_or_dispute: {
    short: "Refund to review",
    title: "The cancelled payment now shows a refund.",
    next: "Confirm the refund in the processor. This payment goes to human review instead of the paid-but-cancelled queue."
  },
  accepted_by_store: {
    short: "Store accepted",
    title: "The store has a matching, accepted order.",
    next: "The store recorded the order. Confirm shipment or delivery separately if needed."
  }
};
const scenario = document.querySelector("#scenario");
const rows = document.querySelector("#rows");
const evidence = document.querySelector("#evidence");
const summary = document.querySelector("#summary");
const formatAmount = payment => new Intl.NumberFormat("en-US", {
  style: "currency", currency: payment.currency
}).format(Number(payment.amount));

function node(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

function show(data, paymentId) {
  const {payments, orders, report} = data;
  rows.replaceChildren();
  for (const payment of payments) {
    const finding = report.findings.find(item => item.payment_id === payment.payment_id);
    const info = copy[finding ? finding.outcome : "accepted_by_store"];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "row";
    button.setAttribute("aria-pressed", String(payment.payment_id === paymentId));
    button.append(node("span", payment.order_ref, "id"), node("span", formatAmount(payment), "amount"),
      node("span", info.short, "status"));
    button.addEventListener("click", () => {
      show(data, payment.payment_id);
      rows.querySelector('[aria-pressed=true]').focus();
    });
    rows.append(button);
    if (payment.payment_id === paymentId) {
      const order = orders.find(item => item.order_ref === payment.order_ref);
      const amount = formatAmount(payment);
      const facts = ["Stripe captured " + amount + "."];
      if (order) facts.push("WooCommerce shows " + formatAmount({amount:order.total, currency:order.currency}) +
        " and status “" + order.status + "”.");
      else facts.push("The order reference is absent from the store file.");
      if (Number(payment.refunded_amount) > 0) facts.push("Stripe shows a full refund.");
      evidence.replaceChildren(node("div", payment.payment_id + " / " + payment.order_ref, "ref"),
        node("h3", info.title), node("p", facts.join(" ")), node("p", info.next));
    }
  }
  summary.textContent = "Synthetic data · " + report.payments_checked + " captures · " +
    report.findings.length + " to review · " + report.grace_hours + "h grace period";
}

fetch("./sample-audits.json").then(response => {
  if (!response.ok) throw Error("Sample unavailable");
  return response.json();
}).then(cases => {
  const render = () => show(cases[scenario.value],
    scenario.value === "order_found" ? "demo-pay-103" : "demo-pay-102");
  scenario.addEventListener("change", render);
  render();
}).catch(() => {
  scenario.disabled = true;
  evidence.replaceChildren(node("p", "The sample could not load. Open the inputs and CLI results below, or reload the page."));
});
