# PLAMA: release, backup, and recovery runbook

## Before trying this branch
1. **Stop PLAMA and LM Studio integrations** so nothing is writing to the database.
2. Copy the entire `memory_data/` directory to a safe location outside Git.
3. Verify your active Python version (3.10+). The branch includes Python unit tests for 3.10, 3.11 and 3.13.
4. Start PLAMA with `start_plama.bat`. The backend now binds to `127.0.0.1` by default.
5. The first start imports legacy JSON short-term messages and session logs into `memory_data/memory.sqlite3`. The previous JSON is kept as `memory.json.bak` when migration rewrites metadata.

## Local backup
With PLAMA stopped, from the repository root:
```bash
python scripts/backup_memory.py --data-dir memory_data --dest PLAMA_backups
```
The utility checks JSON validity, checks SQLite integrity, copies metadata, and uses SQLite's backup API. Keep backups private. ChromaDB is a rebuildable search index; for a full byte-for-byte environment snapshot, archive the entire `memory_data/` directory while the application is stopped.

## Recovery
If `memory.json` is invalid, PLAMA now **refuses to overwrite it**.
Stop the app. Restore a known-good pair of `memory.json` and `memory.sqlite3` from the **same snapshot**. Never restore only JSON over a newer SQLite event log without checking data consistency. Rebuild the ChromaDB index from the Memory page after recovery, if necessary.

## Quality gates
- `python -m pytest -q tests` (lightweight mocks; no download of a local LLM)
- `python -m compileall -q main.py memory_manager.py model_router.py models.py`
- `npm ci && npx tsc --noEmit`
- Manual LM Studio test: create sessions in two tabs; reload; consolidate; switch models; verify no context loss.
- Label a private retrieval dataset and run `benchmarks/evaluate_retrieval.py`.

## Known limitations
- Only **raw messages** are stored in SQLite; derived facts, consolidation cursors and profiles remain in atomically replaced JSON. Cross-file snapshots therefore require quiescence.
- Automatic natural-language contradiction resolution remains conservative: possible conflicting numbers are flagged for review, not silently overwritten.
- Model-derived assertions without a verifiable user quote are marked unknown; do not treat them as verified user preferences.
- The original model routing system primarily targets LM Studio. Cloud-provider adapters and real 4B quality measurements remain separate tasks.
- Memory indexing uses the local embedding model; first start may download model files if not already cached.
- Backups contain sensitive data; store and delete them explicitly.
