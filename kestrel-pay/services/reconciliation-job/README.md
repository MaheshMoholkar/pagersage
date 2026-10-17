# reconciliation-job

Nightly match of acquirer settlement files against the ledger and payments.

| | |
|---|---|
| Tier | 2 |
| Language | python |
| Owner | Ledger (`#ledger`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [ledger-db](../ledger-db/): 200 calls/min, p99 40 ms
- [payments-db](../payments-db/): 200 calls/min, p99 35 ms
- [object-store](../object-store/): 20 calls/min, p99 150 ms
- [kafka](../kafka/): 30 calls/min, p99 10 ms

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
