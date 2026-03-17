import argparse
from pathlib import Path

import pairing_lib as lib


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate pairing.json from players file with group.color assignments")
    ap.add_argument("--players", required=True, type=Path, help="Players JSON with group.color set to red/blue.")
    ap.add_argument("--rounds", required=True, type=int)
    ap.add_argument("--block-size", default=5, type=int)
    ap.add_argument("--seed", default=None, type=int)

    ap.add_argument("--pair-status", default="pending")
    ap.add_argument("--round-status", default="pending")
    ap.add_argument("--experiment-type", default="realtime")
    ap.add_argument("--pairing-mode", default="manual")

    ap.add_argument("--outdir", default=Path("."), type=Path)
    ap.add_argument("--file-prefix", default="", type=str)
    ap.add_argument("--no-timestamp-prefix", action="store_true")

    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    ts = lib.utc_now_for_filename()

    def outpath(name: str) -> Path:
        return (args.outdir / name) if args.no_timestamp_prefix else (args.outdir / lib.with_ts_prefix(ts, name, args.file_prefix))

    pairing_out_path = outpath("pairing.json")
    meta_out_path = outpath("metadata_generate_pairs.json")

    players = lib.load_players_input(args.players)
    player_ids = lib.extract_player_ids(players)
    team_map = lib.get_team_map_from_players(players)

    pairing_json = lib.generate_pairing_json(
        player_ids=player_ids,
        team_map=team_map,
        rounds=args.rounds,
        block_size=args.block_size,
        seed=args.seed,
        pair_status=args.pair_status,
        round_status=args.round_status,
        experiment_type=args.experiment_type,
        pairing_mode=args.pairing_mode,
    )
    lib.save_json(pairing_out_path, pairing_json)

    meta = {
        "generatedAt": lib.utc_now_iso_millis(),
        "inputs": {"players": str(args.players)},
        "outputs": {"pairingOut": str(pairing_out_path), "metadataOut": str(meta_out_path)},
        "parameters": {
            "rounds": args.rounds,
            "blockSize": args.block_size,
            "seed": args.seed,
            "pairStatus": args.pair_status,
            "roundStatus": args.round_status,
            "experimentType": args.experiment_type,
            "pairingMode": args.pairing_mode,
        },
        "counts": {"nPlayers": len(player_ids)},
    }
    lib.save_json(meta_out_path, meta)

    print(pairing_out_path.resolve())
    print(meta_out_path.resolve())


if __name__ == "__main__":
    main()