# payouts-svc

Schedules and sends merchant payouts from ledger balances.

| | |
|---|---|
| Tier | 2 |
| Language | go |
| Owner | Ledger (`#ledger`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [ledger-svc](../ledger-svc/): 60 calls/min, p99 80 ms
- [kafka](../kafka/): 60 calls/min, p99 10 ms

## Called by

- [api-gateway](../api-gateway/)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
