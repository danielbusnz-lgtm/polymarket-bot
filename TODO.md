# TODO

## Test 3 — Live order test
- Get a real token_id from a live market via the Python funnel
- Send a real order through the full pipeline (Python → gRPC → Rust → Polymarket)
- Use minimal size ($1-2) to minimize risk
- Verify EIP-712 signing, tick size snapping, and neg_risk contract selection work against the real exchange
