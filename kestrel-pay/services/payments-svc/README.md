# payments-svc

Charges cards and records payment intents; the only writer to payments-db.

| | |
|---|---|
| Tier | 1 |
| Language | go |
| Owner | Payments (`#payments`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [payments-db](../payments-db/): 2400 calls/min, p99 35 ms
- [fraud-svc](../fraud-svc/): 900 calls/min, p99 60 ms
- [acquirer-gateway](../acquirer-gateway/): 900 calls/min, p99 180 ms
- [kafka](../kafka/): 1800 calls/min, p99 12 ms

## Called by

- [checkout-api](../checkout-api/)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
