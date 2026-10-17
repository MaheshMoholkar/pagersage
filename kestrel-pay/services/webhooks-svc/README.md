# webhooks-svc

Delivers payment events to merchant webhook endpoints, with retries.

| | |
|---|---|
| Tier | 2 |
| Language | go |
| Owner | Merchant Experience (`#merchant-exp`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [kafka](../kafka/): 1500 calls/min, p99 12 ms
- [redis-cache](../redis-cache/): 1500 calls/min, p99 3 ms

## Runbooks

- Scale webhooks-svc and drain the delivery backlog (`drain-webhooks-backlog`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
