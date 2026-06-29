import argparse
import csv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview a CSV file.")
    parser.add_argument(
        "--file",
        default="/app/data.csv",
        help="CSV file path (default: /app/data.csv)",
    )
    parser.add_argument("--rows", type=int, default=10, help="Rows to print")
    args = parser.parse_args()

    csv_path = Path(args.file)
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return 1

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        print("Columns:")
        print(", ".join(header))
        print()
        print(f"First {args.rows} rows:")
        for idx, row in enumerate(reader):
            if idx >= args.rows:
                break
            print(f"{idx + 1}: {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
