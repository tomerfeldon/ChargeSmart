"""Generate the synthetic ChargeSmart dataset and write it to disk as CSV.

Run from backend/:  py scripts/generate_dataset.py

Writes data/sessions.csv and data/base_load.csv at the project root. The data/ folder is
git-ignored — it is regenerated deterministically from (count, seed), so it is never
committed. This is the "historical dataset stored in the database" of Book §2.3, produced
synthetically because real charging data is private (see docs/DATASET.md).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.dataset import (
    generate_base_load,
    generate_sessions,
    write_base_load_csv,
    write_sessions_csv,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

N_VEHICLES = 30
SEED = 42
HORIZON_MIN = 14 * 60  # 14 hours covers the latest departure plus buffer


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    sessions = generate_sessions(count=N_VEHICLES, seed=SEED)
    base_load = generate_base_load(horizon_min=HORIZON_MIN, step_min=5, seed=SEED)

    sessions_path = os.path.join(DATA_DIR, "sessions.csv")
    base_load_path = os.path.join(DATA_DIR, "base_load.csv")
    write_sessions_csv(sessions_path, sessions)
    write_base_load_csv(base_load_path, base_load)

    print(f"Wrote {len(sessions)} sessions  -> {sessions_path}")
    print(f"Wrote {len(base_load)} base-load points -> {base_load_path}")
    print(f"(deterministic: seed={SEED})")


if __name__ == "__main__":
    main()
