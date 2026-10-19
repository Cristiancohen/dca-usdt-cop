#!/usr/bin/env python3
"""Añade una ejecución sanitizada al historial público del monitor (máximo 50)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone


def publish(run_path: Path, history_path: Path, limit: int = 50) -> int:
    event = json.loads(run_path.read_text(encoding="utf-8"))
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {"entries": []}
    entries = history.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Formato inválido: monitor/log.json debe contener entries como lista")
    entries.insert(0, event)
    history = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries[:max(1, limit)],
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = history_path.with_suffix(history_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, history_path)
    print(f"Historial guardado: {len(history['entries'])} ejecuciones; estado más reciente: {event.get('status')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=Path("monitor/run.json"))
    parser.add_argument("--history", type=Path, default=Path("monitor/log.json"))
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    return publish(args.run, args.history, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
