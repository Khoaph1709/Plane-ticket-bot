"""Trip.com crawler entry point.

Use ``python trip_scan.py`` or ``python run_once.py`` for the complete
one-way crawl, price comparison, state update and optional Telegram flow.
"""
from run_once import main


if __name__ == "__main__":
    raise SystemExit(main())
