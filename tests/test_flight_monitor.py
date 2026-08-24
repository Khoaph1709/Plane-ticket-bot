import json
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from pathlib import Path

from trip_crawler import generate_trip_url, parse_trip_card, scrape_single_day
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
        self.assertEqual(route.depart_date, "2026-11-10")
        self.assertEqual(route.depart_end, "2026-11-18")

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

    def test_one_way_trip_url_has_no_return_date(self):
        url = generate_trip_url(
            {"origin": "DAD", "destination": "NRT"},
            "2026-11-14",
        )
        self.assertIn("triptype=ow", url)
        self.assertIn("ddate=2026-11-14", url)
        self.assertNotIn("rdate", url)
        self.assertIn("curr=VND", url)

    def test_parser_reads_tripcom_vnd_card(self):
        class Card:
            text = (
                "Đã có HK Express 21:05 DAD 8g 10p "
                "2g tại Hồng Kông 07:15 NRT +1 6.107.000₫ 6.312.000₫ Chọn"
            )

            def find_elements(self, _by, _selector):
                return []

        parsed = parse_trip_card(Card(), {"origin": "DAD", "destination": "NRT"}, "2026-11-14")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["price"], 6107000)
        self.assertEqual(parsed["currency"], "VND")
        self.assertEqual(parsed["time"], "21:05")
        self.assertEqual(parsed["code"], "N/A")

    def test_trip_crawler_reads_cards_when_wait_is_satisfied(self):
        class Ticket:
            def __init__(self, text, ticket_id):
                self.text = text
                self.id = ticket_id

            def get_attribute(self, _name):
                return self.text

            def find_elements(self, _by, _selector):
                return []

        class Driver:
            def set_page_load_timeout(self, _seconds):
                pass

            def get(self, _url):
                pass

            def find_elements(self, _by, _selector):
                return [
                    Ticket("Vietnam Airlines 00:30 DAD 05h05m Bay thẳng 07:35 NRT 15.387.000₫", "ticket-1"),
                    Ticket("Vietnam Airlines 01:30 DAD 05h00m Bay thẳng 08:30 NRT 15.387.000₫", "ticket-2"),
                ]

        class Wait:
            def until(self, _condition):
                return True

        route = {
            "origin": "DAD",
            "destination": "NRT",
            "return_date": None,
            "top_n": 5,
        }
        with patch("trip_crawler.WebDriverWait", return_value=Wait()), patch("trip_crawler.time.sleep"):
            result = scrape_single_day(Driver(), route, "2026-11-14")
        self.assertEqual(len(result), 2)

    def test_atomic_write_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
