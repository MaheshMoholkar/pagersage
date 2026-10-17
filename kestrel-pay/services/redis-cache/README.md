# redis-cache

Shared Redis for sessions, idempotency keys, rate limits and hot caches.

| | |
|---|---|
| Tier | 1 |
| Language | redis |
| Owner | Platform (`#platform`) |
| Config | [`config.yaml`](config.yaml) |

## Called by

- [auth-svc](../auth-svc/)
- [checkout-api](../checkout-api/)
- [fraud-svc](../fraud-svc/)
- [inventory-svc](../inventory-svc/)
- [pricing-svc](../pricing-svc/)
- [user-api](../user-api/)
- [webhooks-svc](../webhooks-svc/)

## Runbooks

- Restore redis-cache maxmemory and eviction policy (`restore-redis-maxmemory`)
- Promote the redis-cache replica (`failover-redis-cache`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
