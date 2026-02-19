#!/usr/bin/env python3
"""
Generate coordination-game outcome JSONs (blue_blue, red_red, red_blue)
from an existing outcomes JSON by harvesting the prepared historyImage URLs.

Rules:
- Choices x,y in {1..9}
- Success if x + y <= 10  -> pointsOne=x, pointsTwo=y
- Failure if x + y > 10   -> pointsOne=default_p1, pointsTwo=default_p2
- feedback.text:
    Success: "Success! One player chose XX and the other YY."
    Failure: "Coordination Failed. One player chose XX and the other YY. Players get their default points."
- historyImage assignment:
    P1 view uses URL containing "P1_X_P2_Y"
    P2 view uses URL containing "P1_Y_P2_X"
- Redundant keys required:
    both "P1_X_P2_Y" and "P2_Y_P1_X" must exist (same payload).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Tuple, Any, List

PAIR_RE = re.compile(r"P1_([1-9])_P2_([1-9])\.png")


def load_image_map(existing_json_path: Path) -> Tuple[Dict[Tuple[int, int], str], List[str]]:
    """
    Scan all historyImage* URLs and build a map (x,y) -> url where url contains P1_x_P2_y.png
    Returns:
      - image_map: dict mapping (x,y) to URL
      - all_links: list of all historyImage links found (deduped, in encounter order)
    """
    data = json.loads(existing_json_path.read_text(encoding="utf-8"))

    image_map: Dict[Tuple[int, int], str] = {}
    all_links: List[str] = []
    seen_links = set()

    def consider(url: str) -> None:
        if not url or not isinstance(url, str):
            return
        if url not in seen_links:
            all_links.append(url)
            seen_links.add(url)

        m = PAIR_RE.search(url)
        if not m:
            return
        x, y = int(m.group(1)), int(m.group(2))
        # If duplicates exist, keep the first seen (stable).
        image_map.setdefault((x, y), url)

    for _, entry in data.items():
        fb = (entry or {}).get("feedback", {})
        consider(fb.get("historyImage1", ""))
        consider(fb.get("historyImage2", ""))

    return image_map, all_links


def build_outcomes(
    image_map: Dict[Tuple[int, int], str],
    default_p1: int,
    default_p2: int,
) -> Dict[str, Any]:
    """
    Build full 9x9 outcomes with redundant keys.
    Each value has shape: {"feedback": {...}} matching your existing schema.
    """
    missing: List[Tuple[int, int]] = []
    for x in range(1, 10):
        for y in range(1, 10):
            if (x, y) not in image_map:
                missing.append((x, y))
            if (y, x) not in image_map:
                missing.append((y, x))

    if missing:
        missing_unique = sorted(set(missing))
        msg = (
            "Missing history image URLs for these pairs (need both (x,y) and swapped (y,x) "
            "because P2 view uses swapped image):\n"
            + ", ".join([f"({x},{y})" for x, y in missing_unique])
        )
        raise ValueError(msg)

    out: Dict[str, Any] = {}

    for x in range(1, 10):
        for y in range(1, 10):
            success = (x + y) <= 10

            if success:
                text = f"Success! One player chose {x} and the other {y}."
                p1_points = x
                p2_points = y
            else:
                text = (
                    f"Coordination Failed. One player chose {x} and the other {y}. "
                    f"Players get their default points."
                )
                p1_points = default_p1
                p2_points = default_p2

            payload = {
                "feedback": {
                    "text": text,
                    "pointsOne": p1_points,  # always P1
                    "pointsTwo": p2_points,  # always P2
                    "historyImage1": image_map[(x, y)],  # what P1 should see
                    "historyImage2": image_map[(y, x)],  # what P2 should see
                }
            }

            # Redundant keys (same payload)
            key_a = f"P1_{x}_P2_{y}"
            key_b = f"P2_{y}_P1_{x}"
            out[key_a] = payload
            out[key_b] = payload

    return out


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Existing outcomes JSON to harvest historyImage URLs from.",
    )
    ap.add_argument("--outdir", type=Path, default=Path("."), help="Output directory.")
    ap.add_argument("--blue-default", type=int, required=True, help="Default points for blue team on failure.")
    ap.add_argument("--red-default", type=int, required=True, help="Default points for red team on failure.")
    ap.add_argument(
        "--dump-links",
        action="store_true",
        help="Also write a text file with all harvested historyImage links.",
    )
    args = ap.parse_args()

    image_map, links = load_image_map(args.input)

    args.outdir.mkdir(parents=True, exist_ok=True)

    # blue_blue: P1 blue, P2 blue
    blue_blue = build_outcomes(image_map, default_p1=args.blue_default, default_p2=args.blue_default)
    write_json(args.outdir / f"outcomes-blue_blue_{args.blue_default}.json", blue_blue)

    # red_red: P1 red, P2 red
    red_red = build_outcomes(image_map, default_p1=args.red_default, default_p2=args.red_default)
    write_json(args.outdir / f"outcomes-red_red_{args.red_default}.json", red_red)

    # red_blue: P1 red, P2 blue
    red_blue = build_outcomes(image_map, default_p1=args.red_default, default_p2=args.blue_default)
    write_json(args.outdir / f"outcomes-red_blue_R{args.red_default}_B{args.blue_default}.json", red_blue)

    if args.dump_links:
        (args.outdir / "historyImage_links.txt").write_text("\n".join(links) + "\n", encoding="utf-8")

    print("Done.")
    print(f"Harvested {len(links)} historyImage links.")
    print(f"Unique (x,y) images found: {len(image_map)} (expected 81).")


if __name__ == "__main__":
    main()
