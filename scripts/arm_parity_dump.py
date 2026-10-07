# SPDX-License-Identifier: MPL-2.0
"""Dump raw engine outputs on the money benchmark positions for cross-arch diffing.

Writes one JSON file per level with, for every checker decision, the top-5
candidate boards + cubeful equities, and for every cube decision ND/DT/DP and
the action. `arm_parity_compare.py` diffs two such dumps.

    python scripts/arm_parity_dump.py --levels 1ply 2ply --out logs/parity
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from benchmark_money import DEFAULT_DATASET, _read_dataset  # noqa: E402
from bgsage import batch_checker_play, batch_cube_action  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", nargs="+", default=["1ply", "2ply"])
    ap.add_argument("--out", type=Path, default=_PROJECT_ROOT / "logs" / "parity")
    ap.add_argument("--limit", type=int, default=None, help="First N positions only")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    decisions = _read_dataset(DEFAULT_DATASET)["decisions"][: args.limit]
    checker = [d for d in decisions if d["kind"] == "checker"]
    cube = [d for d in decisions if d["kind"] == "cube"]
    print(f"{platform.machine()}: {len(checker)} checker, {len(cube)} cube positions")

    for level in args.levels:
        t0 = time.perf_counter()
        cp = batch_checker_play(
            [{"board": d["board"], "die1": d["dice"][0], "die2": d["dice"][1],
              "cube_value": d["cube_value"], "cube_owner": d["cube_owner"]} for d in checker],
            eval_level=level)
        t_cp = time.perf_counter() - t0
        t0 = time.perf_counter()
        cb = batch_cube_action(
            [{"board": d["board"], "cube_value": d["cube_value"], "cube_owner": d["cube_owner"]}
             for d in cube],
            eval_level=level)
        t_cb = time.perf_counter() - t0
        out = {
            "machine": platform.machine(), "level": level,
            "seconds": {"checker": t_cp, "cube": t_cb},
            "checker": [[[list(m.board), m.equity] for m in r.moves[:5]] for r in cp],
            "cube": [[c.equity_nd, c.equity_dt, c.equity_dp, c.optimal_action] for c in cb],
        }
        (args.out / f"dump_{level}.json").write_text(json.dumps(out))
        print(f"  {level}: checker {t_cp:.1f}s, cube {t_cb:.1f}s")


if __name__ == "__main__":
    main()
