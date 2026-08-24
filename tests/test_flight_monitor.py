import json
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from pathlib import Path

from atadi_crawler import parse_ticket_text, scrape_single_day
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

    def test_parser_reads_atadi_ticket_text(self):
        parsed = parse_ticket_text(
            "Vietnam Airlines VN318 00:30 DAD 05h05m Bay thẳng 07:35 NRT 15.387.000₫"
        )
        self.assertEqual(parsed["code"], "VN318")
        self.assertEqual(parsed["time"], "00:30")
        self.assertEqual(parsed["price"], 15387000)

    def test_old_skip_count_does_not_drop_all_cards(self):
        class Ticket:
            def __init__(self, text):
                self.text = text

            def get_attribute(self, _name):
                return self.text

        class Driver:
            def set_page_load_timeout(self, _seconds):
                pass

            def get(self, _url):
                pass

            def find_elements(self, _by, _selector):
                return [
                    Ticket("Vietnam Airlines VN318 00:30 DAD 05h05m 07:35 NRT 15.387.000₫"),
                    Ticket("Vietnam Airlines VN316 01:30 DAD 05h00m 08:30 NRT 15.387.000₫"),
                ]

        class Wait:
            def until(self, _condition):
                return True

        route = {
            "origin": "DAD",
            "destination": "NRT",
            "return_date": None,
            "skip_count": 3,
            "top_n": 5,
        }
        with patch("atadi_crawler.WebDriverWait", return_value=Wait()), patch("atadi_crawler.time.sleep"):
            result = scrape_single_day(Driver(), route, "2026-11-14")
        self.assertEqual(len(result), 2)

    def test_atomic_write_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
