# Billing, GST & Refund Policy (LSAI-LEGAL-18)

**Version:** 0.1 (DRAFT) · **Last updated:** 2026-06-23 · **Status: BILLING DISABLED**

## Current state
Paid self-serve billing is **deferred and NOT enabled** (per `CLAUDE.md §1`). The application has **no
active payment, checkout, or subscription endpoint**. The closed beta is free for the ~14 invited
advocates. This is guarded by `tests/test_billing_disabled.py` (fails if a billing/payment route is
added without updating this policy).

## When billing is enabled (future — requires its own review)
The following must be in place **before** any payment feature ships:
- **GST**: registered GSTIN, correct HSN/SAC code for SaaS, tax-inclusive invoicing, GST invoices to
  customers — **[MISSING / TO BE POPULATED]**.
- **Pricing & plan terms**: clear plan definitions, renewal, and cancellation in the Terms.
- **Refund/cancellation policy**: stated, India-consumer-law compliant — **[MISSING]**.
- **Payment processor**: a compliant Indian gateway (e.g. Razorpay/PayU); PCI handled by the gateway
  (we never store card data) — **[MISSING]**; added to the Subprocessor Register + Data Map.
- **Records**: invoices retained per tax law; billing data added to the retention schedule.

## Guardrail
Until this policy is completed and reviewed, no billing/payment code may be enabled.
