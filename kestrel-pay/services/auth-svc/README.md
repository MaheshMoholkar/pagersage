# auth-svc

API keys, OAuth tokens and merchant dashboard sessions.

| | |
|---|---|
| Tier | 1 |
| Language | go |
| Owner | Risk & Identity (`#risk`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [user-db](../user-db/): 1900 calls/min, p99 8 ms
- [redis-cache](../redis-cache/): 3000 calls/min, p99 3 ms
- [kafka](../kafka/): 250 calls/min, p99 10 ms

## Called by

- [api-gateway](../api-gateway/)

## Runbooks

- Rotate the auth-svc token signing key (`rotate-auth-signing-key`)

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
