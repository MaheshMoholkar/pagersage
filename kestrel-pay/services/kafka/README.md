# kafka

Event bus for payment, ledger, webhook and notification events.

| | |
|---|---|
| Tier | 1 |
| Language | kafka |
| Owner | Platform (`#platform`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [kafka-controller](../kafka-controller/): 300 calls/min, p99 5 ms
- [schema-registry](../schema-registry/): 900 calls/min, p99 6 ms
- [object-store](../object-store/): 60 calls/min, p99 120 ms

## Called by

- [auth-svc](../auth-svc/)
- [checkout-api](../checkout-api/)
- [fraud-svc](../fraud-svc/)
- [inventory-svc](../inventory-svc/)
- [ledger-svc](../ledger-svc/)
- [notifications-svc](../notifications-svc/)
- [payments-svc](../payments-svc/)
- [payouts-svc](../payouts-svc/)
- [reconciliation-job](../reconciliation-job/)
- [user-api](../user-api/)
- [webhooks-svc](../webhooks-svc/)

## Runbooks

- Move partitions off a full Kafka broker (`reassign-kafka-partitions`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
