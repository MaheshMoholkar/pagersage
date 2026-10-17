# checkout-api

Builds the cart, prices it, reserves stock and starts the payment.

| | |
|---|---|
| Tier | 1 |
| Language | python |
| Owner | Checkout (`#checkout`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [payments-svc](../payments-svc/): 900 calls/min, p99 220 ms
- [inventory-svc](../inventory-svc/): 900 calls/min, p99 45 ms
- [pricing-svc](../pricing-svc/): 900 calls/min, p99 30 ms
- [redis-cache](../redis-cache/): 2400 calls/min, p99 4 ms
- [kafka](../kafka/): 900 calls/min, p99 12 ms

## Called by

- [api-gateway](../api-gateway/)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
