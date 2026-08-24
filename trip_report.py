"""Trip.com report entry point.

The complete pipeline is implemented by ``run_once.py``. This alias is kept
for users who prefer a report-style command name.
"""
from run_once import main


if __name__ == "__main__":
    raise SystemExit(main())
