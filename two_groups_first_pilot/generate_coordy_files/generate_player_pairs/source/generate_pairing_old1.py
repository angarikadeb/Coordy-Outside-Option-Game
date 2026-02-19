#!/usr/bin/env python3
"""
Generate pairing JSON for an experiment app. BY GPT!!

- Inputs: players file (JSON list OR txt lines)
- Automatic team assignment by proportion
- Layout selection based on (team1, team2) with consistent positions
- Pairing schedule: blocks of 5 rounds with fixed pairs; reshuffle each block
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# -----------------------------
# Helpers
# -----------------------------

def utc_now_iso_millis() -> str:
    # Example format: "2026-01-22T15:51:03.237Z"
    dt = datetime.now(timezone.utc)
    # isoformat(timespec="milliseconds") yields "+00:00", convert to "Z"
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_player_ids(path: Path) -> List[str]:
    """
    Accepts:
      - JSON file containing a list of strings: ["id1","id2",...]
      - TXT file: one ID per line (blank lines ignored)
    """
    if not path.exists():
        raise FileNotFoundError(f"Players file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try JSON first
    if path.suffix.lower() in {".json"}:
        data = json.loads(text)
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise ValueError("JSON players file must be a list of strings (player IDs).")
        return [x.strip() for x in data if x.strip()]

    # Otherwise treat as txt
    return [line.strip() for line in text.splitlines() if line.strip()]


def save_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


# -----------------------------
# Team + Layout logic
# -----------------------------

@dataclass(frozen=True)
class LayoutSpec:
    layout_id: str
    # positions are numeric slots in your app (you can change these defaults)
    position_red: int
    position_blue: int


def build_default_layouts() -> Dict[str, LayoutSpec]:
    """
    Default layout IDs are the same as their names:
      - "red_red"
      - "red_blue"
      - "blue_blue"

    Positions:
      - For red_blue: red -> position 1, blue -> position 2
      - For same-team layouts: still uses position 1/2, but both are same team.
    """
    return {
        "red_red": LayoutSpec(layout_id="red_red", position_red=1, position_blue=2),
        "red_blue": LayoutSpec(layout_id="red_blue", position_red=1, position_blue=2),
        "blue_blue": LayoutSpec(layout_id="blue_blue", position_red=1, position_blue=2),
    }


def assign_teams(
    player_ids: List[str],
    red_prop: float,
    rng: random.Random
) -> Dict[str, str]:
    """
    Returns dict: player_id -> "red" or "blue"
    """
    if not (0.0 <= red_prop <= 1.0):
        raise ValueError("--red-prop must be between 0 and 1.")

    players = player_ids[:]
    rng.shuffle(players)

    n = len(players)
    n_red = int(round(red_prop * n))
    n_red = max(0, min(n, n_red))

    team_map: Dict[str, str] = {}
    for i, pid in enumerate(players):
        team_map[pid] = "red" if i < n_red else "blue"
    return team_map


def pick_layout_and_positions(
    p1: str,
    p2: str,
    team_map: Dict[str, str],
    layouts: Dict[str, LayoutSpec],
) -> Tuple[str, str, int, int]:
    """
    Decide layoutId + (player1Id, player2Id) ordering + positions.

    Rule: for red_blue layout, player1 is the red team player, player2 is blue.
    For red_red / blue_blue, keep (p1,p2) ordering as given.
    """
    t1, t2 = team_map[p1], team_map[p2]

    # same-team
    if t1 == "red" and t2 == "red":
        spec = layouts["red_red"]
        return spec.layout_id, p1, p2, 1, 2
    if t1 == "blue" and t2 == "blue":
        spec = layouts["blue_blue"]
        return spec.layout_id, p1, p2, 1, 2

    # mixed
    spec = layouts["red_blue"]
    if t1 == "red" and t2 == "blue":
        # p1 is red, p2 is blue
        return spec.layout_id, p1, p2, spec.position_red, spec.position_blue
    else:
        # swap so player1 is red
        return spec.layout_id, p2, p1, spec.position_red, spec.position_blue


# -----------------------------
# Pairing schedule logic
# -----------------------------

def make_random_matching(player_ids: List[str], rng: random.Random) -> List[Tuple[str, str]]:
    """
    Returns a list of pairs. If odd number, last one is dropped (unpaired).
    """
    ids = player_ids[:]
    rng.shuffle(ids)
    pairs = []
    for i in range(0, len(ids) - 1, 2):
        pairs.append((ids[i], ids[i + 1]))
    return pairs


def pairs_signature(pairs: List[Tuple[str, str]]) -> set[frozenset[str]]:
    """
    Signature ignoring order: { {a,b}, {c,d}, ... }
    """
    return {frozenset((a, b)) for a, b in pairs}


def make_block_matching(
    player_ids: List[str],
    rng: random.Random,
    prev_block_sig: Optional[set[frozenset[str]]] = None,
    max_tries: int = 200,
) -> List[Tuple[str, str]]:
    """
    Create a random matching, trying to avoid repeating the exact same pairs
    as the previous block (if possible).
    """
    if prev_block_sig is None:
        return make_random_matching(player_ids, rng)

    best = None
    for _ in range(max_tries):
        pairs = make_random_matching(player_ids, rng)
        sig = pairs_signature(pairs)
        if sig != prev_block_sig:
            return pairs
        best = pairs

    # If we couldn't find a different matching (e.g., very small N), return best attempt.
    return best if best is not None else make_random_matching(player_ids, rng)


def generate_pairing_json(
    player_ids: List[str],
    rounds: int,
    block_size: int,
    red_prop: float,
    seed: Optional[int] = None,
    pair_status: str = "pending",
    round_status: str = "pending",
    include_root_metadata: bool = True,
    experiment_type: str = "realtime",
    pairing_mode: str = "manual",
    layouts_override: Optional[Dict[str, LayoutSpec]] = None,
) -> Tuple[dict, dict]:
    """
    Returns:
      - pairing_json (dict) with rounds -> pairs
      - team_assignment (dict) player_id -> team
    """
    if rounds < 1:
        raise ValueError("--rounds must be >= 1")
    if block_size < 1:
        raise ValueError("--block-size must be >= 1")
    if len(player_ids) < 2:
        raise ValueError("Need at least 2 players to create pairs.")

    rng = random.Random(seed)

    layouts = layouts_override or build_default_layouts()
    team_map = assign_teams(player_ids, red_prop=red_prop, rng=rng)

    created_at = utc_now_iso_millis()
    rounds_obj: Dict[str, dict] = {}

    prev_sig: Optional[set[frozenset[str]]] = None
    current_block_pairs: List[Tuple[str, str]] = []

    for r in range(1, rounds + 1):
        # Start a new block at 1, 1+block_size, 1+2*block_size, ...
        if (r - 1) % block_size == 0:
            current_block_pairs = make_block_matching(
                player_ids=player_ids,
                rng=rng,
                prev_block_sig=prev_sig,
            )
            prev_sig = pairs_signature(current_block_pairs)

        pairs_obj: Dict[str, dict] = {}
        for idx, (a, b) in enumerate(current_block_pairs):
            layout_id, p1, p2, pos1, pos2 = pick_layout_and_positions(
                a, b, team_map=team_map, layouts=layouts
            )
            pair_key = f"pair_{idx:03d}"
            pairs_obj[pair_key] = {
                "createdAt": created_at,
                "layoutId": layout_id,
                "player1Id": p1,
                "player2Id": p2,
                "position1": pos1,
                "position2": pos2,
                "status": pair_status,
            }

        rounds_obj[f"round{r}"] = {
            "pairs": pairs_obj,
            "status": round_status,
        }

    if include_root_metadata:
        pairing_json = {
            "experimentType": experiment_type,
            "lastUpdated": utc_now_iso_millis(),
            "pairingMode": pairing_mode,
            "rounds": rounds_obj,
        }
    else:
        pairing_json = {"rounds": rounds_obj}

    return pairing_json, team_map


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate pairing JSON for an experiment app.")
    ap.add_argument("--players", required=True, type=Path, help="Path to players file (JSON list or TXT).")
    ap.add_argument("--rounds", required=True, type=int, help="Number of rounds to generate.")
    ap.add_argument("--block-size", default=5, type=int, help="Rounds per fixed-opponent block (default: 5).")
    ap.add_argument("--red-prop", default=0.5, type=float, help="Proportion assigned to red team (default: 0.5).")
    ap.add_argument("--seed", default=None, type=int, help="Random seed for reproducibility.")
    ap.add_argument("--out", default=Path("pairing.json"), type=Path, help="Output pairing JSON path.")
    ap.add_argument("--teams-out", default=None, type=Path, help="Optional output teams JSON path.")
    ap.add_argument("--no-root-metadata", action="store_true", help="Only output {'rounds': ...}.")
    ap.add_argument("--pair-status", default="pending", type=str, help="Status for each pair (default: pending).")
    ap.add_argument("--round-status", default="pending", type=str, help="Status for each round (default: pending).")
    ap.add_argument("--experiment-type", default="realtime", type=str, help="Root experimentType (default: realtime).")
    ap.add_argument("--pairing-mode", default="manual", type=str, help="Root pairingMode (default: manual).")

    args = ap.parse_args()

    player_ids = load_player_ids(args.players)
    player_ids = list(dict.fromkeys(player_ids))  # de-dup, keep order
    if len(player_ids) < 2:
        raise SystemExit("Need at least 2 unique player IDs.")

    pairing_json, team_map = generate_pairing_json(
        player_ids=player_ids,
        rounds=args.rounds,
        block_size=args.block_size,
        red_prop=args.red_prop,
        seed=args.seed,
        pair_status=args.pair_status,
        round_status=args.round_status,
        include_root_metadata=not args.no_root_metadata,
        experiment_type=args.experiment_type,
        pairing_mode=args.pairing_mode,
    )

    save_json(args.out, pairing_json)
    print(f"Wrote pairing JSON: {args.out.resolve()}")

    if args.teams_out is not None:
        save_json(args.teams_out, team_map)
        print(f"Wrote team assignment JSON: {args.teams_out.resolve()}")


if __name__ == "__main__":
    main()
