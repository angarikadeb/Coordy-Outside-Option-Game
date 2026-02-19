from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# -----------------------------
# Time + JSON helpers
# -----------------------------

def utc_now_iso_millis() -> str:
    dt = datetime.now(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def utc_now_for_filename() -> str:
    """
    Filename-safe UTC timestamp like: 2026-02-19T153500Z
    """
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H%M%SZ")


def with_ts_prefix(ts: str, name: str, prefix: str = "") -> str:
    """
    Build: <ts>_<prefix_>name
    """
    prefix_part = f"{prefix}_" if prefix else ""
    return f"{ts}_{prefix_part}{name}"


# -----------------------------
# Players input/output format
# -----------------------------

def load_players_input(path: Path) -> Dict[str, dict]:
    """
    players_input.json format:
      {
        "<playerId>": { ... , "group": { "allowedRole": "...", "name": "...", "color": "..." }, ... },
        ...
      }
    """
    data = read_json(path)
    if not isinstance(data, dict) or not all(isinstance(k, str) for k in data.keys()):
        raise ValueError("players_input.json must be a JSON object whose keys are player IDs.")
    if not all(isinstance(v, dict) for v in data.values()):
        raise ValueError("players_input.json values must be objects (player info dicts).")
    return data


def extract_player_ids(players_input: Dict[str, dict]) -> List[str]:
    return list(players_input.keys())


def write_players_output(
    players_input: Dict[str, dict],
    team_map: Dict[str, str],
    red_group_name: str = "Group A",
    blue_group_name: str = "Group B",
) -> Dict[str, dict]:
    """
    Returns an edited copy where ONLY player['group'] is modified:
      - allowedRole -> ""
      - name/color -> based on assigned team
    """
    out: Dict[str, dict] = {}

    for pid, info in players_input.items():
        if pid not in team_map:
            raise ValueError(f"Player id {pid} missing from team_map.")

        team = team_map[pid]  # "red" or "blue"
        group_name = red_group_name if team == "red" else blue_group_name
        group_color = "red" if team == "red" else "blue"

        # shallow copy player dict (so we don't mutate input)
        new_info = dict(info)

        # group dict: overwrite only group entry in the player object
        existing_group = info.get("group", {})
        if existing_group is None:
            existing_group = {}
        if not isinstance(existing_group, dict):
            existing_group = {}

        new_info["group"] = {
            **existing_group,          # keep any extra fields if they exist
            "allowedRole": "",         # REQUIRED change
            "name": group_name,        # assigned group name
            "color": group_color,      # assigned group color
        }

        out[pid] = new_info

    return out


# -----------------------------
# Layout + pairing logic
# -----------------------------

@dataclass(frozen=True)
class LayoutSpec:
    layout_id: str
    position_red: int
    position_blue: int


def build_default_layouts() -> Dict[str, LayoutSpec]:
    # Base names only; we’ll append _1/_2 at generation time
    return {
        "red_red": LayoutSpec(layout_id="red_red", position_red=1, position_blue=2),
        "red_blue": LayoutSpec(layout_id="red_blue", position_red=1, position_blue=2),
        "blue_blue": LayoutSpec(layout_id="blue_blue", position_red=1, position_blue=2),
    }



def assign_teams(player_ids: List[str], red_prop: float, rng: random.Random) -> Dict[str, str]:
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


def pick_base_layout_and_positions(
    p1: str,
    p2: str,
    team_map: Dict[str, str],
    layouts: Dict[str, LayoutSpec],
) -> Tuple[str, str, int, int]:
    t1, t2 = team_map[p1], team_map[p2]

    if t1 == "red" and t2 == "red":
        spec = layouts["red_red"]
        return spec.layout_id, p1, p2, 1, 2

    if t1 == "blue" and t2 == "blue":
        spec = layouts["blue_blue"]
        return spec.layout_id, p1, p2, 1, 2

    spec = layouts["red_blue"]
    if t1 == "red" and t2 == "blue":
        return spec.layout_id, p1, p2, spec.position_red, spec.position_blue
    else:
        return spec.layout_id, p2, p1, spec.position_red, spec.position_blue


def make_random_matching(player_ids: List[str], rng: random.Random) -> List[Tuple[str, str]]:
    ids = player_ids[:]
    rng.shuffle(ids)
    return [(ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2)]  # drops last if odd


def pairs_signature(pairs: List[Tuple[str, str]]) -> set[frozenset[str]]:
    return {frozenset((a, b)) for a, b in pairs}


def make_block_matching(
    player_ids: List[str],
    rng: random.Random,
    prev_block_sig: Optional[set[frozenset[str]]] = None,
    max_tries: int = 200,
) -> List[Tuple[str, str]]:
    if prev_block_sig is None:
        return make_random_matching(player_ids, rng)

    best = None
    for _ in range(max_tries):
        pairs = make_random_matching(player_ids, rng)
        if pairs_signature(pairs) != prev_block_sig:
            return pairs
        best = pairs

    return best if best is not None else make_random_matching(player_ids, rng)


def generate_pairing_json(
    player_ids: List[str],
    rounds: int,
    block_size: int,
    team_map: Dict[str, str],
    seed: Optional[int] = None,
    pair_status: str = "pending",
    round_status: str = "pending",
    include_root_metadata: bool = True,
    experiment_type: str = "realtime",
    pairing_mode: str = "manual",
    layouts_override: Optional[Dict[str, LayoutSpec]] = None,
) -> dict:
    if rounds < 1:
        raise ValueError("--rounds must be >= 1")
    if block_size < 1:
        raise ValueError("--block-size must be >= 1")
    if len(player_ids) < 2:
        raise ValueError("Need at least 2 players to create pairs.")
    if set(player_ids) != set(team_map.keys()):
        # team_map can have same keys but in different order; ensure coverage
        missing = set(player_ids) - set(team_map.keys())
        extra = set(team_map.keys()) - set(player_ids)
        if missing:
            raise ValueError(f"team_map missing players: {sorted(missing)}")
        if extra:
            raise ValueError(f"team_map has unknown players: {sorted(extra)}")

    rng = random.Random(seed)
    layouts = layouts_override or build_default_layouts()

    created_at = utc_now_iso_millis()
    rounds_obj: Dict[str, dict] = {}

    prev_sig: Optional[set[frozenset[str]]] = None
    current_block_pairs: List[Tuple[str, str]] = []

    for r in range(1, rounds + 1):
        if (r - 1) % block_size == 0:
            current_block_pairs = make_block_matching(
                player_ids=player_ids,
                rng=rng,
                prev_block_sig=prev_sig,
            )
            prev_sig = pairs_signature(current_block_pairs)

        pairs_obj: Dict[str, dict] = {}
        for idx, (a, b) in enumerate(current_block_pairs):
            suffix = 1 if (r % 2 == 1) else 2

            base_layout, p1, p2, pos1, pos2 = pick_base_layout_and_positions(
                a, b, team_map=team_map, layouts=layouts
            )
            layout_id = f"{base_layout}_{suffix}"

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
        return {
            "experimentType": experiment_type,
            "pairingMode": pairing_mode,
            "lastUpdated": utc_now_iso_millis(),
            "rounds": rounds_obj,
        }
    return {"rounds": rounds_obj}


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate pairing JSON + players_output.json + metadata.json")

    ap.add_argument("--players-input", required=True, type=Path,
                    help="Input JSON where keys are player IDs and values contain player info (including group).")
    ap.add_argument("--pairing-out", default=Path("pairing.json"), type=Path,
                    help="Output pairing JSON path (default: pairing.json).")
    ap.add_argument("--meta-out", default=Path("metadata.json"), type=Path,
                    help="Output metadata JSON path (default: metadata.json).")
    
    ap.add_argument("--outdir", default=Path("."), type=Path,
                help="Directory for output files (default: current directory).")
    ap.add_argument("--file-prefix", default="", type=str,
                    help="Optional extra prefix after timestamp (e.g. 'pilot1').")
    ap.add_argument("--no-timestamp-prefix", action="store_true",
                    help="Disable timestamp prefix in output filenames.")


    ap.add_argument("--rounds", required=True, type=int, help="Number of rounds to generate.")
    ap.add_argument("--block-size", default=5, type=int, help="Rounds per fixed-opponent block (default: 5).")
    ap.add_argument("--red-prop", default=0.5, type=float, help="Proportion assigned to red team (default: 0.5).")
    ap.add_argument("--seed", default=None, type=int, help="Random seed for reproducibility.")

    ap.add_argument("--pair-status", default="pending", type=str, help="Status for each pair (default: pending).")
    ap.add_argument("--round-status", default="pending", type=str, help="Status for each round (default: pending).")
    ap.add_argument("--experiment-type", default="realtime", type=str, help="Root experimentType (default: realtime).")
    ap.add_argument("--pairing-mode", default="manual", type=str, help="Root pairingMode (default: manual).")

    ap.add_argument("--red-group-name", default="Group A", type=str, help="Group name for red team (default: Group A).")
    ap.add_argument("--blue-group-name", default="Group B", type=str, help="Group name for blue team (default: Group B).")

    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    ts_file = utc_now_for_filename()

    def outpath(default_name: str) -> Path:
        if args.no_timestamp_prefix:
            return args.outdir / default_name
        return args.outdir / with_ts_prefix(ts_file, default_name, args.file_prefix)

    players_output_path = outpath("players_output.json")
    pairing_out_path = outpath("pairing.json")
    meta_out_path = outpath("metadata.json")

    generated_at = utc_now_iso_millis()

    players_input = load_players_input(args.players_input)
    player_ids = extract_player_ids(players_input)
    player_ids = list(dict.fromkeys(player_ids))
    if len(player_ids) < 2:
        raise SystemExit("Need at least 2 unique players.")

    rng_for_teams = random.Random(args.seed)
    team_map = assign_teams(player_ids, red_prop=args.red_prop, rng=rng_for_teams)

    players_output = write_players_output(
        players_input=players_input,
        team_map=team_map,
        red_group_name=args.red_group_name,
        blue_group_name=args.blue_group_name,
    )
    save_json(players_output_path, players_output)


    pairing_json = generate_pairing_json(
        player_ids=player_ids,
        rounds=args.rounds,
        block_size=args.block_size,
        team_map=team_map,
        seed=args.seed,
        pair_status=args.pair_status,
        round_status=args.round_status,
        include_root_metadata=True,
        experiment_type=args.experiment_type,
        pairing_mode=args.pairing_mode,
    )
    save_json(pairing_out_path, pairing_json)

    meta = {
        "generatedAt": generated_at,
        "inputs": {
            "playersInput": str(args.players_input),
        },
        "outputs": {
            "playersOutput": str(players_output_path),
            "pairingOut": str(pairing_out_path),
            "metadataOut": str(meta_out_path),
        },

        "parameters": {
            "rounds": args.rounds,
            "blockSize": args.block_size,
            "redProp": args.red_prop,
            "seed": args.seed,
            "pairStatus": args.pair_status,
            "roundStatus": args.round_status,
            "experimentType": args.experiment_type,
            "pairingMode": args.pairing_mode,
            "redGroupName": args.red_group_name,
            "blueGroupName": args.blue_group_name,
        },
        "counts": {
            "nPlayers": len(player_ids),
            "nRed": sum(1 for t in team_map.values() if t == "red"),
            "nBlue": sum(1 for t in team_map.values() if t == "blue"),
        },
    }
    save_json(meta_out_path, meta)

    print(f"Wrote players output: {players_output_path.resolve()}")
    print(f"Wrote pairing JSON:   {pairing_out_path.resolve()}")
    print(f"Wrote metadata JSON:  {meta_out_path.resolve()}")



if __name__ == "__main__":
    main()
