# user-api

Merchant, shop and customer profiles.

| | |
|---|---|
| Tier | 2 |
| Language | python |
| Owner | Merchant Experience (`#merchant-exp`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [user-db](../user-db/): 800 calls/min, p99 10 ms
- [redis-cache](../redis-cache/): 900 calls/min, p99 3 ms
- [kafka](../kafka/): 120 calls/min, p99 10 ms

## Called by

- [api-gateway](../api-gateway/)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
