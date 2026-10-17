# payments-db

Primary Postgres for payment intents and charges, behind a server-side connection pool.

| | |
|---|---|
| Tier | 1 |
| Language | postgres |
| Owner | Payments (`#payments`) |
| Config | [`config.yaml`](config.yaml) |

## Called by

- [payments-svc](../payments-svc/)
- [reconciliation-job](../reconciliation-job/)

## Runbooks

- Raise pool + restart payments-svc (`raise-payments-db-pool`)
- Fail over payments-db to the standby (`failover-payments-db`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
