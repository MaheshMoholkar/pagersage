# api-gateway

Authenticates and routes every public API call to the service behind it.

| | |
|---|---|
| Tier | 1 |
| Language | go |
| Owner | Platform (`#platform`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [auth-svc](../auth-svc/): 3000 calls/min, p99 12 ms
- [checkout-api](../checkout-api/): 1200 calls/min, p99 140 ms
- [user-api](../user-api/): 600 calls/min, p99 60 ms
- [search-api](../search-api/): 300 calls/min, p99 80 ms
- [payouts-svc](../payouts-svc/): 50 calls/min, p99 120 ms

## Called by

- [edge](../edge/)

## Runbooks

- Restore api-gateway upstream timeouts (`raise-api-gateway-timeouts`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
