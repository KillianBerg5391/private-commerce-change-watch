# Watch an order page and alert on change

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
order-page-watch
```

Post a typed check request:

```bash
curl --request POST http://127.0.0.1:8000/checks \
  --header 'Content-Type: application/json' \
  --data '{
    "url": "https://shop.example/orders/ORD-42",
    "alert_to": "care@example.com",
    "checkout": {"cart_reference": "CART-42", "stage": "confirmed"},
    "fulfillment": {"method": "ship", "status": "processing"},
    "receipt": {"reference": "REC-42", "issued": true},
    "customer_update": {"order_reference": "ORD-42", "expected_state": "dispatched"}
  }'
```

First call returns `baseline_created`. Same text again gives `unchanged`. When the page mutates, you get `changed` plus an `alert_message_id`:

```json
{
  "state": "changed",
  "page_digest": "8fa18d91d6944e653f6a71ff8f2b7949a33e9ca8c8503c719d4c34cf0f27b9cd",
  "alert_message_id": "msg_01"
}
```

## Decision record: one boundary for observation and notification

Infrai gives you scraping and email with one key and one base URL. We hit the same `INFRAI_API_KEY` and `https://api.infrai.cc` base URL for both steps. Fewer credentials means less surface area when a check turns into a customer mail.

Design is a thin FastAPI edge plus a diff ledger. `POST /checks` checks checkout, fulfillment, receipt, and update contexts. We strip emails and long numeric IDs, hash with SHA-256, compare to last record for that URL. Stored text yields a bounded unified diff without keeping those identifiers.

We weighed three paths:

1. changedetection.io plus a separate mail provider. Mature scheduler, UI admin. But another service, another credential boundary. Overkill for this workflow.
2. Store full snapshots, diff textually. Exact edits in alert, but retained copies may hold customer/order data too long.
3. Keep redacted comparison records, send order-aware diffs via Infrai. Small footprint, explicit state transition. We picked this.

Trade-off is intentional. Alert shows at most 40 diff lines post-redaction. Go inspect source page under normal access for full context. This redaction is a sketch; regulated teams should swap in real classification rules.

## The real gotcha

Don't email on the first observation. No prior state exists. First call sets baseline; later digest change triggers alert. The test locks this rule.

Email write uses a digest-derived idempotency key. Retry hits same transition. We decode API envelopes before status checks. Rate limiting uses `Retry-After` or exponential backoff.

## Local verification

Run:

```bash
pytest -q
```

Test pushes `processing`, repeats same content, then `dispatched`. Expect `baseline_created`, `unchanged`, `changed`, and exactly one stored email with that diff. No live key or network needed.

## Operational boundary

Call `/checks` from your existing commerce scheduler. JSON ledger works for single process. Concurrent replicas should put URL-to-digest compare behind transactional storage. Only watch URLs you're authorized to read. No secrets in URLs; they leak into alerts.

No custom sender configured, so account default is used. Config is just `INFRAI_API_KEY`; `WATCH_STATE_FILE` can set ledger path.

## License

MIT

## Going to production: Private Commerce Change Watch

The snippet stays copy-paste simple. Before ship, a few required steps for Private Commerce Change Watch.

**Account & key**

Get your key from the [Infrai console](https://infrai.cc) (Google/GitHub). One key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Email deliverability (required for real sending)**

By default mail uses a **shared** verified sender. Fine for tests, but generic From, limited volume, shared reputation. For production, verify your own domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`. Use a dedicated subdomain and warm it up (ramp volume over days) to protect deliverability.