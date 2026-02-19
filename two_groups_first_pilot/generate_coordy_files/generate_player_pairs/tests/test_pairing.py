import sys
sys.path.insert(0, "source")
import generate_pairing as gp

FIXED_TS = "2026-01-01T00:00:00.000Z"


def test_pairing_blocks_and_layouts(monkeypatch):
    # Freeze timestamps to make output deterministic
    monkeypatch.setattr(gp, "utc_now_iso_millis", lambda: FIXED_TS)

    players = ["A", "B", "C", "D", "E", "F"]

    pairing_json, team_map = gp.generate_pairing_json(
        player_ids=players,
        rounds=10,
        block_size=5,
        red_prop=0.5,
        seed=123,
        include_root_metadata=True,
        pair_status="pending",
        round_status="pending",
        experiment_type="realtime",
        pairing_mode="manual",
    )

    # Top-level fields
    assert pairing_json["experimentType"] == "realtime"
    assert pairing_json["pairingMode"] == "manual"
    assert pairing_json["lastUpdated"] == FIXED_TS
    assert "rounds" in pairing_json
    assert len(pairing_json["rounds"]) == 10

    # Team assignment counts
    assert set(team_map.keys()) == set(players)
    assert sum(1 for t in team_map.values() if t == "red") == 3
    assert sum(1 for t in team_map.values() if t == "blue") == 3

    # Helper to get round pairs as unordered sets (ignore player1/player2 order)
    def round_signature(round_obj):
        sig = set()
        for pair in round_obj["pairs"].values():
            sig.add(frozenset([pair["player1Id"], pair["player2Id"]]))
        return sig

    rounds = pairing_json["rounds"]

    # Round 1–5 identical pairing
    sig1 = round_signature(rounds["round1"])
    for r in range(2, 6):
        assert round_signature(rounds[f"round{r}"]) == sig1

    # Round 6–10 identical pairing
    sig6 = round_signature(rounds["round6"])
    for r in range(7, 11):
        assert round_signature(rounds[f"round{r}"]) == sig6

    # Block 2 differs from block 1 (when possible)
    assert sig6 != sig1

    # Validate each pair object schema + layout logic
    for r in range(1, 11):
        round_obj = rounds[f"round{r}"]
        assert round_obj["status"] == "pending"
        for pair_key, pair in round_obj["pairs"].items():
            assert pair_key.startswith("pair_")
            assert pair["createdAt"] == FIXED_TS
            assert pair["status"] == "pending"
            assert pair["layoutId"] in {"red_red", "red_blue", "blue_blue"}
            assert pair["position1"] == 1
            assert pair["position2"] == 2

            p1 = pair["player1Id"]
            p2 = pair["player2Id"]
            t1, t2 = team_map[p1], team_map[p2]

            if t1 == "red" and t2 == "red":
                assert pair["layoutId"] == "red_red"
            elif t1 == "blue" and t2 == "blue":
                assert pair["layoutId"] == "blue_blue"
            else:
                assert pair["layoutId"] == "red_blue"
                # ordering enforced: player1 is red, player2 is blue
                assert team_map[pair["player1Id"]] == "red"
                assert team_map[pair["player2Id"]] == "blue"
