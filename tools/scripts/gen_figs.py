"""Generate paper figures from experiments/reports/ data.

Usage:
    python3 tools/scripts/gen_figs.py [--output paper/target/dsaa2025/figs/]
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Generate paper figures")
    parser.add_argument(
        "--output",
        default="paper/target/dsaa2025/figs/",
        help="Output directory for figures",
    )
    args = parser.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    # TODO: Add figure generation logic
    # Source data: experiments/reports/tables/*.csv
    print(f"Figure generation not yet implemented. Output dir: {output_dir}")


if __name__ == "__main__":
    main()
