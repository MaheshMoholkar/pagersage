# Named Cypher queries

Every agent tool runs named queries from this folder (build-plan.md section 4).
[`docs/cypher.md`](../../docs/cypher.md) is generated from these files (`make catalogue`), so
keep the headers readable: the first sentence after the task tag is the catalogue's summary.

Rules:

- One statement per file: `<name>.cypher`, lowercase with underscores (`suspect_changes.cypher`).
  Multi-step tools use several files, e.g. `record_decision_create.cypher`,
  `record_decision_evidence.cypher`, `record_decision_precedent.cypher`.
- Parameters are always `$params`. Never build Cypher with string formatting.
- Start each file with `//` comment lines: what it answers, its parameters, what it returns.
  FalkorDB 6.0.2 accepts `//` comments (tested in `tests/test_falkordb.py`).
- Read-only queries run with `graph.ro_query`; writes only through the write tools in
  `pagersage/contracts/tools.py`.
- Load with `pagersage.queries.load("<name>")`.
- Every query gets a golden test against the seeded graph.
- `seed_*.cypher` and `count_*.cypher` are the seed loader's writes and checks (G03) and
  `batch_*.cypher` the batch algorithms (G05, G18); the catalogue lists them in their own
  sections. Every file must be run by some function in `pagersage/` (tested).
