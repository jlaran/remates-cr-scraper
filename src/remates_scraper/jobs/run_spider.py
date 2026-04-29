"""CLI entrypoint: python -m remates_scraper.jobs.run_spider <source>"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["bcr", "judicial"])
    args = parser.parse_args(argv)

    if args.source == "bcr":
        from remates_scraper.spiders.bcr.spider import run
    elif args.source == "judicial":
        # Will be implemented in Task 24 — not available yet
        print("ERROR: judicial spider not yet implemented (Task 24)", file=sys.stderr)
        return 2
    else:
        parser.error(f"unknown source {args.source}")
        return 2

    result = run()
    print(f"done: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
