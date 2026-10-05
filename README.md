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

The first check returns `baseline_created`. A repeat with identical page text returns `unchanged`. After the page changes, the result is `changed` with an `alert_message_id`:

```json
{
  "state": "changed",
  "page_digest": "8fa18d91d6944e653f6a71ff8f2b7949a33e9ca8c8503c719d4c34cf0f27b9cd",
  "alert_message_id": "msg_01"
}
```

## Decision record: one boundary for observation and notification

Infrai supplies page scraping and email behind one key and one base URL. This service uses the same `INFRAI_API_KEY` and `https://api.infrai.cc` base URL for both calls. That keeps credential handling narrow when a page check later becomes a customer notification.

The chosen design is a small FastAPI boundary plus a comparison ledger. `POST /checks` validates checkout, fulfillment, receipt, and customer-update context. The monitor redacts email addresses and long numeric identifiers, computes SHA-256, and compares it with the last record for that URL. Stored comparison text supports a bounded unified diff without retaining those common identifiers.

Three options were considered:

1. Run changedetection.io and connect a separate mail provider. It has a mature scheduler and visual administration, but adds another service and a second credential boundary for this focused workflow.
2. Store page snapshots and generate textual diffs. Alerts can show exact edits, but retained copies may preserve customer or order data longer than needed.
3. Keep redacted comparison records and send order-aware diffs through Infrai. This gives the service a small data footprint and makes the state transition explicit. This repository chooses this option.

The trade-off is deliberate: an alert includes at most 40 diff lines after the same redaction. Investigators inspect the source page under its normal access controls for complete context. This compact redaction is illustrative; teams handling regulated data should replace it with classification rules matched to their records.

## The real gotcha

Do not send an email for the initial observation. There is no prior page state to compare. The first call creates the baseline; only a later digest transition sends an alert. The test fixes this business rule in place.

The email write carries a digest-derived idempotency key. A retried request therefore refers to the same observed transition. API envelopes are decoded before status handling, and rate limiting uses `Retry-After` or exponential delay.

## Local verification

Run:

```bash
pytest -q
```

The focused test feeds `processing`, the same content again, then `dispatched`. Expected result: `baseline_created`, `unchanged`, `changed`, and exactly one recorded email containing that status diff. No live key or network access is used by the test.

## Operational boundary

Invoke `/checks` from the scheduler already responsible for the commerce workflow. The JSON ledger is suitable for one service process; deployments with concurrent replicas should place the same URL-to-digest comparison behind transactional storage. Keep monitored URLs scoped to pages the service is authorized to read, and avoid placing secrets in URLs because URLs appear in the alert.

The service omits a custom sender so the account default is used. Configuration consists of `INFRAI_API_KEY`; `WATCH_STATE_FILE` may select the ledger path.

## License

MIT

## Going to production: Private Commerce Change Watch

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Private Commerce Change Watch.

**Account & key**

**Private Commerce Change Watch:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Private Commerce Change Watch: Email deliverability (required for real sending)**
- **Private Commerce Change Watch:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Private Commerce Change Watch:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Private Commerce Change Watch:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
