#!/usr/bin/env python3
"""Offline snapshot of PLAMA's durable memory. Stop PLAMA before using."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup(data_dir: Path, dest_root: Path) -> Path:
    source_json = data_dir / "memory.json"
    source_db = data_dir / "memory.sqlite3"
    if not source_json.exists() or not source_db.exists():
        raise FileNotFoundError("Both memory.json and memory.sqlite3 must exist")
    # Fail closed on bad inputs instead of backing up a corrupted snapshot.
    json.loads(source_json.read_text(encoding="utf-8"))
    check = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    try:
        integrity = check.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    finally:
        check.close()

    target = dest_root / datetime.now(timezone.utc).strftime("plama-%Y%m%dT%H%M%S%fZ")
    target.mkdir(parents=True, exist_ok=False)
    json_copy = target / "memory.json"
    db_copy = target / "memory.sqlite3"
    shutil.copy2(source_json, json_copy)
    src = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(db_copy))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(data_dir.resolve()),
        "files": {path.name: sha256(path) for path in [json_copy, db_copy]},
        "note": "Stop PLAMA before backup for cross-file consistency. ChromaDB is a rebuildable index.",
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description="Back up PLAMA's personal memory offline")
    parser.add_argument("--data-dir", type=Path, default=Path("memory_data"))
    parser.add_argument("--dest", type=Path, default=Path("PLAMA_backups"))
    args = parser.parse_args()
    result = backup(args.data_dir, args.dest)
    print(f"Backup stored at: {result}")


if __name__ == "__main__":
    main()
