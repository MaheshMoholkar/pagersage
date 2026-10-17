# Kestrel Pay company files

Hand-written source of truth for the fictional company. PagerSage ingests these at seed time;
the formats and cross-checks are defined in `backend/pagersage/contracts/seed.py`
(see `docs/contracts.md`). Plan: [`../PLAN.md`](../PLAN.md).

| File | Task | Status |
|---|---|---|
| `topology.yaml` | K1 | done |
| `org.yaml` | K2 | done |
| `runbooks.yaml` | K3 | done |
| `policies.yaml` | K3 | done |

Validate a directory:

```bash
cd backend && uv run python -c "from pathlib import Path; from pagersage.contracts.seed import load_seed_dir; print(load_seed_dir(Path('../kestrel-pay/company')))"
```
