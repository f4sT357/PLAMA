# PLAMA retrieval benchmark

Run against an already running **local** PLAMA server. This benchmark does not upload user memories.

1. In PLAMA's Memory view, locate fact IDs for the relevant test questions. You can also use `GET /api/memory/facts`.
2. Create `benchmarks/my_cases.json`:

```json
[
  {
    "query": "現在使っている自転車のチェーンリングは何Tか",
    "expected_fact_ids": ["fact_replace_with_a_real_id"]
  },
  {
    "query": "過去に言及していない架空の所属は？",
    "unanswerable": true
  }
]
```

3. Run `python benchmarks/evaluate_retrieval.py benchmarks/my_cases.json -k 5`.

Measurements: Recall@k, MRR@k, empty-result rate on unanswerable cases,
and median API latency. These are **retrieval metrics**, not a measure of
LLM response correctness. Evaluate answer synthesis, exact user-intent fidelity,
temporal updates, and model-switch consistency separately with gold answers.
Never interpret a small synthetic dataset as proof of world-leading accuracy.

## Security
`my_cases.json` may contain private facts; keep such datasets out of Git.
This script only calls a locally configured API (127.0.0.1 by default).
