import argparse
import random
from pathlib import Path

import pairing_lib as lib


def main() -> None:
    ap = argparse.ArgumentParser(description="Assign players to red/blue teams and write players_output.json")
    ap.add_argument("--players-input", required=True, type=Path)
    ap.add_argument("--red-prop", default=0.5, type=float)
    ap.add_argument("--seed", default=None, type=int)
    ap.add_argument("--red-group-name", default="Group A")
    ap.add_argument("--blue-group-name", default="Group B")

    ap.add_argument("--outdir", default=Path("."), type=Path)
    ap.add_argument("--file-prefix", default="", type=str)
    ap.add_argument("--no-timestamp-prefix", action="store_true")

    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    ts = lib.utc_now_for_filename()

    def outpath(name: str) -> Path:
        return (args.outdir / name) if args.no_timestamp_prefix else (args.outdir / lib.with_ts_prefix(ts, name, args.file_prefix))

    players_output_path = outpath("players_output.json")
    meta_out_path = outpath("metadata_assign_teams.json")

    players_input = lib.load_players_input(args.players_input)
    player_ids = lib.extract_player_ids(players_input)

    rng = random.Random(args.seed)
    team_map = lib.assign_teams(player_ids, red_prop=args.red_prop, rng=rng)

    players_output = lib.write_players_output(
        players_input, team_map, red_group_name=args.red_group_name, blue_group_name=args.blue_group_name
    )
    lib.save_json(players_output_path, players_output)

    meta = {
        "generatedAt": lib.utc_now_iso_millis(),
        "inputs": {"playersInput": str(args.players_input)},
        "outputs": {"playersOutput": str(players_output_path), "metadataOut": str(meta_out_path)},
        "parameters": {
            "redProp": args.red_prop,
            "seed": args.seed,
            "redGroupName": args.red_group_name,
            "blueGroupName": args.blue_group_name,
        },
        "counts": {
            "nPlayers": len(player_ids),
            "nRed": sum(1 for t in team_map.values() if t == "red"),
            "nBlue": sum(1 for t in team_map.values() if t == "blue"),
        },
    }
    lib.save_json(meta_out_path, meta)

    print(players_output_path.resolve())
    print(meta_out_path.resolve())


if __name__ == "__main__":
    main()