# edge

Public TLS edge with WAF and rate limits in front of every shopper and merchant request.

| | |
|---|---|
| Tier | 1 |
| Language | envoy |
| Owner | Platform (`#platform`) |
| Config | [`config.yaml`](config.yaml) |

## Depends on

- [api-gateway](../api-gateway/): 3200 calls/min, p99 25 ms

<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->
