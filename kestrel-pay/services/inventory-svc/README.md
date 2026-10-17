# inventory-svc

Reserves stock for carts and releases it when a checkout expires.

| | |
|---|---|
| Tier | 2 |
| Language | java |
| Owner | Checkout (`#checkout`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [inventory-db](../inventory-db/): 1400 calls/min, p99 18 ms
- [redis-cache](../redis-cache/): 900 calls/min, p99 3 ms
- [kafka](../kafka/): 300 calls/min, p99 10 ms

## Called by

- [checkout-api](../checkout-api/)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
