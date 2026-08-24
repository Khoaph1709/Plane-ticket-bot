"""Backward-compatible entry point.

Use ``python run_once.py`` for the complete crawl + compare + Telegram flow.
This wrapper keeps the old command name working without storing credentials.
"""
from run_once import main


if __name__ == "__main__":
    raise SystemExit(main())
