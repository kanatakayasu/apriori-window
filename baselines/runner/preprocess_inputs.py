from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def _read_lines(path: Path) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def _parse_flat(line: str) -> List[int]:
    return sorted({int(x) for x in line.split() if x})


def _parse_basket(line: str) -> List[int]:
    items = []
    for basket in line.split("|"):
        items.extend(basket.split())
    return sorted({int(x) for x in items if x})


def _parse_timestamped(line: str) -> Tuple[int, List[int]]:
    parts = line.split()
    ts = int(parts[0])
    items = sorted({int(x) for x in parts[1:] if x})
    return ts, items


def normalize(input_path: Path, input_format: str) -> List[Tuple[int, List[int]]]:
    rows = _read_lines(input_path)
    out: List[Tuple[int, List[int]]] = []

    if input_format == "flat":
        for idx, ln in enumerate(rows):
            out.append((idx, _parse_flat(ln)))
        return out

    if input_format == "basket":
        for idx, ln in enumerate(rows):
            out.append((idx, _parse_basket(ln)))
        return out

    if input_format == "timestamped":
        for ln in rows:
            out.append(_parse_timestamped(ln))
        return out

    raise ValueError(f"unknown input_format: {input_format}")


def write_outputs(rows: List[Tuple[int, List[int]]], out_dir: Path, stem: str) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p_flat = out_dir / f"{stem}.flat.txt"
    p_ts = out_dir / f"{stem}.timestamped.txt"
    p_lppm = out_dir / f"{stem}.lppm.txt"

    with open(p_flat, "w", encoding="utf-8") as f_flat, \
         open(p_ts, "w", encoding="utf-8") as f_ts, \
         open(p_lppm, "w", encoding="utf-8") as f_lppm:
        for ts, items in rows:
            f_flat.write(" ".join(str(x) for x in items) + "\n")
            f_ts.write(f"{ts} " + " ".join(str(x) for x in items) + "\n")
            f_lppm.write(" ".join(str(x) for x in items) + f" | {ts}\n")

    meta = {
        "n_transactions": len(rows),
        "n_unique_items": len({x for _, items in rows for x in items}),
        "min_ts": min((ts for ts, _ in rows), default=0),
        "max_ts": max((ts for ts, _ in rows), default=0),
    }
    p_meta = out_dir / f"{stem}.metadata.json"
    with open(p_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "flat": str(p_flat),
        "timestamped": str(p_ts),
        "lppm": str(p_lppm),
        "metadata": str(p_meta),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare comparative method inputs")
    parser.add_argument("--input", required=True)
    parser.add_argument("--input-format", choices=["flat", "basket", "timestamped"], required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--stem", default="dataset")
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = normalize(input_path=input_path, input_format=args.input_format)
    outputs = write_outputs(rows=rows, out_dir=Path(args.out_dir), stem=args.stem)

    print("[preprocess] generated files")
    for k, v in outputs.items():
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main()
