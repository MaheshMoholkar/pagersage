# inventory-db

Postgres for stock levels and reservations.

| | |
|---|---|
| Tier | 2 |
| Language | postgres |
| Owner | Checkout (`#checkout`) |
| Config | [`config.yaml`](config.yaml) |

## Called by

- [inventory-svc](../inventory-svc/)

## Runbooks

- Kill runaway queries and restore the inventory-db index (`fix-inventory-db-slow-queries`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
