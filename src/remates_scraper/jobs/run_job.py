"""CLI: python -m remates_scraper.jobs.run_job <job>"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job", choices=["promote", "geocode", "images", "reconcile"])
    args = p.parse_args(argv)
    mod = __import__(f"remates_scraper.jobs.{args.job}", fromlist=["run"])
    print(mod.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
