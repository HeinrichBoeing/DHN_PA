"""Entry point for the DHN_PA district heating price analysis tool."""

import argparse
from pathlib import Path

from analysis import run_analysis
from scraper import load_or_scrape

DEFAULT_DATA_DIR = Path("data")
DEFAULT_CACHE_FILE = "waermepreise.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape and analyze German district heating prices from waermepreise.info"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-scrape even if cached CSV exists.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        metavar="DIR",
        help=f"Directory for cached CSV data (default: {DEFAULT_DATA_DIR}/).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cache_path = args.data_dir / DEFAULT_CACHE_FILE

    df = load_or_scrape(cache_path, refresh=args.refresh)
    run_analysis(df)


if __name__ == "__main__":
    main()
