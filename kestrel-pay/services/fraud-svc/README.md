# fraud-svc

Scores every charge for fraud risk before it reaches the card network.

| | |
|---|---|
| Tier | 1 |
| Language | python |
| Owner | Risk & Identity (`#risk`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [redis-cache](../redis-cache/): 1800 calls/min, p99 3 ms
- [kafka](../kafka/): 900 calls/min, p99 10 ms

## Called by

- [payments-svc](../payments-svc/)

## Runbooks

- Switch fraud scoring to the rules-only fallback (`fraud-rules-fallback`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
