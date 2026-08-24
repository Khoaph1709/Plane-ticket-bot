from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


AIRLINE_MAP = {
    "VJ": "Vietjet Air",
    "VN": "Vietnam Airlines",
    "QH": "Bamboo Airways",
    "VU": "Vietravel Airlines",
    "JQ": "Jetstar Pacific",
}


def init_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=vi-VN")
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    chrome_path = os.getenv("CHROME_BIN")
    if chrome_path:
        options.binary_location = chrome_path
    # Selenium Manager resolves a compatible driver on current Selenium versions.
    return webdriver.Chrome(options=options)


def parse_ticket_text(raw_text: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "airline": "Unknown",
        "code": "Unknown",
        "time": "Unknown",
        "price": 0,
    }
    code_match = re.search(r"\b([A-Z]{2}\d{3,4})\b", raw_text)
    if code_match:
        info["code"] = code_match.group(1)
        info["airline"] = AIRLINE_MAP.get(info["code"][:2], "Hãng khác")
    time_matches = re.findall(r"\b(\d{2}:\d{2})\b", raw_text)
    if time_matches:
        info["time"] = time_matches[0]
    price_match = re.search(r"([\d.]+)\s*[₫đ]", raw_text, flags=re.IGNORECASE)
    if price_match:
        info["price"] = int(price_match.group(1).replace(".", ""))
    return info


def date_range(start: str, end: str) -> list[str]:
    begin = datetime.strptime(start, "%Y-%m-%d").date()
    finish = datetime.strptime(end, "%Y-%m-%d").date()
    return [(begin + timedelta(days=i)).isoformat() for i in range((finish - begin).days + 1)]


def generate_atadi_url(origin: str, destination: str, depart_date: str, return_date: str | None = None) -> str:
    """Build a URL for one configured route.

    Atadi's current URL shape contains two dates. For an independent one-way
    watch, the same date is sent twice and `leg=0` is retained, matching the
    legacy crawler's contract while avoiding an invented +3-day return.
    """
    dep = datetime.strptime(depart_date, "%Y-%m-%d").strftime("%Y%m%d")
    ret = datetime.strptime(return_date or depart_date, "%Y-%m-%d").strftime("%Y%m%d")
    params = {
        "ap": f"{origin}.{destination}",
        "dt": f"{dep}.{ret}",
        "ps": "1.0.0",
        "leg": "0",
    }
    return "https://atadi.vn/tim-ve-may-bay?" + urlencode(params)


def scrape_single_day(driver: webdriver.Chrome, route: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    url = generate_atadi_url(route["origin"], route["destination"], date_str, route.get("return_date"))
    driver.set_page_load_timeout(35)
    try:
        driver.get(url)
    except TimeoutException:
        driver.execute_script("window.stop();")

    try:
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".flightTicket"))
        )
        time.sleep(4)
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    tickets = driver.find_elements(By.CSS_SELECTOR, ".flightTicket")
    requested_skip = int(route.get("skip_count", 0))
    # Atadi currently returns a small set of visible flight cards. If an old
    # configuration asks to skip all cards, fall back to zero rather than
    # silently producing an empty result.
    skip_count = requested_skip if requested_skip < len(tickets) else 0
    top_n = int(route.get("top_n", 5))
    for ticket in tickets[skip_count:]:
        try:
            raw_text = ticket.text or ticket.get_attribute("innerText") or ""
            data = parse_ticket_text(raw_text)
            data["date"] = date_str
            data["route"] = f"{route['origin']}.{route['destination']}"
            if data["price"] > 0:
                results.append(data)
        except Exception:
            continue
    results.sort(key=lambda item: item["price"])
    return results[:top_n]


def crawl_route(driver: webdriver.Chrome, route: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        date_str: scrape_single_day(driver, route, date_str)
        for date_str in date_range(route["start"], route["end"])
    }
