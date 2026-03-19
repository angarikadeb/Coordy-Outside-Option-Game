from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Time helpers
# -----------------------------

def utc_now_iso_millis() -> str:
    dt = datetime.now(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def with_ts_prefix(ts: str, name: str, prefix: str = "") -> str:
    prefix_part = f"{prefix}_" if prefix else ""
    return f"{ts}_{prefix_part}{name}"


# -----------------------------
# JSON helpers
# -----------------------------

def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


# -----------------------------
# Players format
# -----------------------------

def load_players_input(path: Path) -> Dict[str, dict]:
    data = read_json(path)
    if not isinstance(data, dict) or not all(isinstance(k, str) for k in data.keys()):
        raise ValueError("Players JSON must be an object whose keys are player IDs.")
    if not all(isinstance(v, dict) for v in data.values()):
        raise ValueError("Players JSON values must be objects (player info dicts).")
    return data


def extract_player_ids(players: Dict[str, dict]) -> List[str]:
    return list(players.keys())


def get_team_map_from_players(players: Dict[str, dict]) -> Dict[str, str]:
    """
    Reads team assignment from players[*].group.color ("red"/"blue").
    """
    team_map: Dict[str, str] = {}
    for pid, info in players.items():
        group = info.get("group", {}) or {}
        color = (group.get("color") or "").strip().lower()
        if color not in {"red", "blue"}:
            raise ValueError(f"Player {pid} missing valid group.color ('red'/'blue'). Got: {color!r}")
        team_map[pid] = color
    return team_map


def write_players_output(
    players_input: Dict[str, dict],
    team_map: Dict[str, str],
    red_group_name: str = "Group A",
    blue_group_name: str = "Group B",
) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for pid, info in players_input.items():
        if pid not in team_map:
            raise ValueError(f"Player id {pid} missing from team_map.")
        team = team_map[pid]
        group_name = red_group_name if team == "red" else blue_group_name
        group_color = team

        new_info = dict(info)
        existing_group = info.get("group", {}) or {}
        if not isinstance(existing_group, dict):
            existing_group = {}

        new_info["group"] = {
            **existing_group,
            "allowedRole": "",      # required
            "name": group_name,
            "color": group_color,
        }
        out[pid] = new_info
    return out


# -----------------------------
# Team assignment
# -----------------------------

def assign_teams(player_ids: List[str], red_prop: float, rng: random.Random) -> Dict[str, str]:
    if not (0.0 <= red_prop <= 1.0):
        raise ValueError("red_prop must be between 0 and 1.")

    ids = player_ids[:]
    rng.shuffle(ids)

    n = len(ids)
    n_red = int(round(red_prop * n))
    n_red = max(0, min(n, n_red))

    team_map: Dict[str, str] = {}
    for i, pid in enumerate(ids):
        team_map[pid] = "red" if i < n_red else "blue"
    return team_map


# -----------------------------
# Layout + pairing
# -----------------------------

@dataclass(frozen=True)
class LayoutSpec:
    base_id: str
    position_red: int
    position_blue: int


def build_default_layouts() -> Dict[str, LayoutSpec]:
    # base ids only; we append _1/_2 globally by round
    return {
        "red_red": LayoutSpec(base_id="red_red", position_red=1, position_blue=2),
        "red_blue": LayoutSpec(base_id="red_blue", position_red=1, position_blue=2),
        "blue_blue": LayoutSpec(base_id="blue_blue", position_red=1, position_blue=2),
    }


def pick_base_layout_and_positions(
    a: str, b: str, team_map: Dict[str, str], layouts: Dict[str, LayoutSpec]
) -> Tuple[str, str, str, int, int]:
    t1, t2 = team_map[a], team_map[b]

    if t1 == "red" and t2 == "red":
        spec = layouts["red_red"]
        return spec.base_id, a, b, 1, 2

    if t1 == "blue" and t2 == "blue":
        spec = layouts["blue_blue"]
        return spec.base_id, a, b, 1, 2

    spec = layouts["red_blue"]
    # enforce player1=red, player2=blue
    if t1 == "red" and t2 == "blue":
        return spec.base_id, a, b, spec.position_red, spec.position_blue
    else:
        return spec.base_id, b, a, spec.position_red, spec.position_blue


def make_random_matching(player_ids: List[str], rng: random.Random) -> List[Tuple[str, str]]:
    ids = player_ids[:]
    rng.shuffle(ids)
    return [(ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2)]


def pairs_signature(pairs: List[Tuple[str, str]]) -> set[frozenset[str]]:
    return {frozenset((x, y)) for x, y in pairs}


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
    team_map: Dict[str, str],
    rounds: int,          # number of PLAYING rounds (excludes intro + change_partner)
    intro_rounds: int,    # number of instruction rounds at the very beginning
    block_size: int,
    seed: Optional[int],
    pair_status: str = "pending",
    round_status: str = "pending",
    experiment_type: str = "realtime",
    pairing_mode: str = "manual",
) -> dict:
    if rounds < 1:
        raise ValueError("rounds must be >= 1")
    if intro_rounds < 0:
        raise ValueError("intro_rounds must be >= 0")
    if block_size < 1:
        raise ValueError("block_size must be >= 1")

    rng = random.Random(seed)
    layouts = build_default_layouts()

    created_at = utc_now_iso_millis()
    rounds_obj: Dict[str, dict] = {}

    prev_sig: Optional[set[frozenset[str]]] = None
    current_block_pairs: List[Tuple[str, str]] = []

    round_num = 0            # counts ALL emitted rounds (intro + change_partner + playing)
    playing_round_index = 0  # counts ONLY playing rounds (for _1/_2 alternation)

    def emit_round(pairs_obj: Dict[str, dict]) -> None:
        nonlocal round_num
        round_num += 1
        rounds_obj[f"round{round_num}"] = {
            "pairs": pairs_obj,
            "waitingPlayers": [],
            "unpairedPlayers": [],
            "status": round_status,
        }

    def build_pairs_obj(
        layout_id_override: Optional[str],
        pairs_for_round: List[Tuple[str, str]],
    ) -> Dict[str, dict]:
        """
        If layout_id_override is provided -> use that layoutId for all pairs.
        If None -> it's a playing round and we use alternating _1/_2 + _big_buttons.
        """
        nonlocal playing_round_index

        suffix = None
        if layout_id_override is None:
            playing_round_index += 1
            suffix = 1 if (playing_round_index % 2 == 1) else 2

        pairs_obj: Dict[str, dict] = {}
        for idx, (a, b) in enumerate(pairs_for_round):
            base_layout, p1, p2, pos1, pos2 = pick_base_layout_and_positions(
                a, b, team_map=team_map, layouts=layouts
            )

            if layout_id_override is not None:
                layout_id = layout_id_override
            else:
                layout_id = f"{base_layout}_{suffix}_big_buttons"

            pairs_obj[f"pair_{idx:03d}"] = {
                "createdAt": created_at,
                "layoutId": layout_id,
                "player1Id": p1,
                "player2Id": p2,
                "position1": pos1,
                "position2": pos2,
                "status": pair_status,
            }

        return pairs_obj

    # --- First block pairs (used for intro rounds and the first change_partner) ---
    current_block_pairs = make_block_matching(player_ids, rng, prev_block_sig=None)
    prev_sig = pairs_signature(current_block_pairs)

    # --- Intro rounds: Instruction_1..Instruction_intro_rounds (shown to both players in each pair) ---
    for i in range(1, intro_rounds + 1):
        emit_round(build_pairs_obj(layout_id_override=f"Instruction_{i}", pairs_for_round=current_block_pairs))

    # --- Playing rounds, grouped in blocks; each block begins with change_partner ---
    playing_done = 0
    block_index = 0

    while playing_done < rounds:
        if block_index > 0:
            emit_round(build_pairs_obj(layout_id_override="change_partner", pairs_for_round=current_block_pairs))

        n_in_block = min(block_size, rounds - playing_done)
        for _ in range(n_in_block):
            emit_round(build_pairs_obj(layout_id_override=None, pairs_for_round=current_block_pairs))
            playing_done += 1

        if playing_done < rounds:
            current_block_pairs = make_block_matching(player_ids, rng, prev_block_sig=prev_sig)
            prev_sig = pairs_signature(current_block_pairs)

        block_index += 1

    # Final closing screen (shown to both players in each last-block pair)
    emit_round(build_pairs_obj(layout_id_override="thank_you", pairs_for_round=current_block_pairs))

    return {
        "experimentType": experiment_type,
        "pairingMode": pairing_mode,
        "lastUpdated": utc_now_iso_millis(),
        "rounds": rounds_obj,
    }