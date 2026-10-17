# Scripts

One-off and diagnostic scripts. Run them from `backend/` with `uv run python ../scripts/<name>.py`.

| Script | What |
|---|---|
| `smoke_algos.py` | `make smoke`: calls every FalkorDB procedure the plan uses on a throwaway toy graph and prints what it found (G01). `tests/test_falkordb.py::test_smoke_algos` runs the same checks in CI. |
| `cypher_catalogue.py` | `make catalogue`: writes `docs/cypher.md`, every query in `backend/queries/` with what it answers, the algorithm or index it uses and the function that runs it (G19). `tests/test_cypher_catalogue.py` fails when it is stale. |
