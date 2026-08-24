"""Backward-compatible report entry point.

The upgraded pipeline performs crawl, comparison and Telegram delivery in one
idempotent run. Use ``python run_once.py`` directly for new deployments.
"""
from run_once import main


if __name__ == "__main__":
    raise SystemExit(main())
