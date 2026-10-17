# ledger-svc

Double-entry ledger of every money movement, fed by payment events from kafka.

| | |
|---|---|
| Tier | 1 |
| Language | kotlin |
| Owner | Ledger (`#ledger`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [ledger-db](../ledger-db/): 1500 calls/min, p99 20 ms
- [kafka](../kafka/): 1500 calls/min, p99 10 ms

## Called by

- [payouts-svc](../payouts-svc/)

## Runbooks

- Replay missed payment events into ledger-svc (`replay-ledger-events`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
