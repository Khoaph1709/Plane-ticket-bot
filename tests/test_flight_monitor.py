import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from flight_monitor import (
    atomic_write_json,
    build_user_message,
    compare_prices,
    load_config,
)


class FlightMonitorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_config_supports_multiple_users_and_date_range(self):
        _, users = load_config(self.root / "config" / "users.example.json")
        self.assertEqual(len(users), 2)
        route = users[0].routes[0]
        self.assertEqual(route.origin, "DAD")
        self.assertEqual(route.destination, "NRT")
        self.assertEqual(route.depart_end, "2026-11-14")

    def test_compare_prices_uses_lowest_duplicate_fare(self):
        previous = [{"airline": "Vietjet Air", "code": "VJ123", "time": "08:00", "price": 4000000}]
        current = [
            {"airline": "Vietjet Air", "code": "VJ123", "time": "08:00", "price": 3900000},
            {"airline": "Vietjet Air", "code": "VJ123", "time": "08:00", "price": 3800000},
        ]
        events = compare_prices(previous, current)
        self.assertEqual(events["lower"][0]["price"], 3800000)
        self.assertEqual(events["lower"][0]["old_price"], 4000000)

    def test_threshold_causes_alert_when_price_does_not_change(self):
        _, users = load_config(self.root / "config" / "users.example.json")
        route = users[0].routes[0]
        flights = [{"airline": "Vietjet Air", "code": "VJ123", "time": "08:00", "price": 3000000}]
        _, should_alert = build_user_message(users[0], route, flights, flights, datetime(2026, 8, 24, 8, 0))
        self.assertTrue(should_alert)

    def test_atomic_write_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
