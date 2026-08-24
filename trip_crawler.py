from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


LOG = logging.getLogger("trip-crawler")
PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+|\d{4,})\s*(?:₫|đ|VND)", re.IGNORECASE)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")
AIRPORT_RE = re.compile(r"\b[A-Z]{3}\b")
CODE_RE = re.compile(r"\b([A-Z]{2}\d{2,4})\b")

# Trip.com uses city codes for some destinations while the selected airport is
# represented separately. These values can be overridden per route in JSON.
AIRLINE_LOGO_MAP = {
    "vj": "VietJet Air",
    "vn": "Vietnam Airlines",
    "hx": "Hong Kong Airlines",
    "uo": "HK Express",
    "gk": "Jetstar Japan",
    "nh": "All Nippon Airways",
    "ci": "China Airlines",
    "tw": "T'Way Air",
    "jl": "Japan Airlines",
    "mm": "Peach Aviation",
    "sl": "Thai Lion Air",
}

CITY_CODE_MAP = {
    "NRT": "TYO",
    "HND": "TYO",
    "KIX": "OSA",
    "ITM": "OSA",
}


def init_driver() -> webdriver.Chrome:
    options = Options()
    options.page_load_strategy = "eager"
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
    return webdriver.Chrome(options=options)


def _date_yyyymmdd(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")


def generate_trip_url(route: dict[str, Any], depart_date: str) -> str:
    """Build a Trip.com one-way URL; no return date is sent."""
    origin = str(route["origin"]).upper()
    destination = str(route["destination"]).upper()
    departure_city = str(route.get("departure_city") or origin).lower()
    arrival_city = str(route.get("arrival_city") or CITY_CODE_MAP.get(destination, destination)).lower()
    params = {
        "dcity": departure_city,
        "acity": arrival_city,
        "ddate": _date_yyyymmdd(depart_date),
        "dairport": origin.lower(),
        "aairport": destination.lower(),
        "triptype": "ow",
        "class": str(route.get("service_class", "y")).lower(),
        "lowpricesource": "searchform",
        "quantity": str(route.get("quantity", 1)),
        "searchboxarg": "t",
        "nonstoponly": "on" if route.get("nonstop_only", False) else "off",
        "locale": str(route.get("locale", "vi-VN")),
        "curr": "VND",
    }
    return "https://vn.trip.com/flights/showfarefirst?" + urlencode(params)


def _find_cards(driver: webdriver.Chrome) -> list[Any]:
    selectors = (
        ".result-item.J_FlightItem",
        ".result-item-dep.J_FlightItem",
        "[data-testid='flight-card']",
    )
    seen: set[str] = set()
    cards: list[Any] = []
    for selector in selectors:
        for card in driver.find_elements(By.CSS_SELECTOR, selector):
            identity = card.id
            if identity not in seen:
                seen.add(identity)
                cards.append(card)
    return cards


def _first_text(element: Any, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        nodes = element.find_elements(By.CSS_SELECTOR, selector)
        for node in nodes:
            text = " ".join((node.text or "").split()).strip()
            if text:
                return text
    return ""


def _airline_from_logo(element: Any) -> str:
    for image in element.find_elements(By.CSS_SELECTOR, ".flt-card-airline-logo img, img.logo-img"):
        source = (image.get_attribute("src") or "").lower()
        match = re.search(r"/([a-z]{2})\.webp(?:$|[?#])", source)
        if match and match.group(1) in AIRLINE_LOGO_MAP:
            return AIRLINE_LOGO_MAP[match.group(1)]
    return ""


def _first_attribute(element: Any, selectors: tuple[str, ...], attribute: str) -> str:
    for selector in selectors:
        for node in element.find_elements(By.CSS_SELECTOR, selector):
            value = " ".join((node.get_attribute(attribute) or "").split()).strip()
            if value:
                return value
    return ""


def _all_text(element: Any, selectors: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for selector in selectors:
        for node in element.find_elements(By.CSS_SELECTOR, selector):
            text = " ".join((node.text or "").split()).strip()
            if text:
                values.append(text)
    return values


def _parse_price(text: str) -> int:
    matches = PRICE_RE.findall(text)
    if not matches:
        return 0
    # The first VND amount in a flight card is the current selling price;
    # later amounts can be crossed-out reference prices.
    return int(re.sub(r"\D", "", matches[0]))


def parse_trip_card(card: Any, route: dict[str, Any], date_str: str) -> dict[str, Any] | None:
    raw_text = " ".join((card.text or "").split())
    if not raw_text:
        return None

    airline = _first_text(card, (".flights-name", ".flight-info-airline", "[data-testid='flights-name']"))
    if not airline:
        airline = _first_attribute(
            card,
            (".flight-info-airline [role='region']", ".flight-info-airline__wrap [role='region']"),
            "aria-label",
        )
    if not airline:
        airline = _airline_from_logo(card)
    airline = airline.split(" Được vận hành bởi ", 1)[0].strip() or "N/A"
    code = _first_text(card, ("[data-testid='flight-number']", ".flight-number", ".flight-code"))
    if not code:
        code_match = CODE_RE.search(raw_text)
        code = code_match.group(1) if code_match else "N/A"

    times = TIME_RE.findall(raw_text)
    # TIME_RE has a capturing group for the hour; use a second full match for
    # stable extraction of HH:MM values.
    full_times = re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", raw_text)
    airports = [value for value in AIRPORT_RE.findall(raw_text) if value not in {"VND"}]
    stop_text = _first_text(card, (".flight-info-stop__text_3ee2", ".flight-info-stop__info-wrapper_c5e1"))
    duration = _first_text(card, (".flight-info-duration_576d", ".flight-info-stop__wrapper_1a3b"))
    price = _parse_price(raw_text)
    if not airline and price == 0:
        return None
    if price <= 0:
        LOG.warning("Card has no VND price: %s", raw_text[:250])
        return None

    return {
        "airline": airline,
        "code": code,
        "time": full_times[0] if full_times else (times[0] if times else "N/A"),
        "arrival_time": full_times[1] if len(full_times) > 1 else "N/A",
        "origin": airports[0] if airports else route["origin"],
        "destination": airports[1] if len(airports) > 1 else route["destination"],
        "duration": duration or "N/A",
        "stops": stop_text or ("Bay thẳng" if "Bay thẳng" in raw_text else "Có điểm dừng"),
        "price": price,
        "currency": "VND",
        "date": date_str,
        "route": f"{route['origin']}.{route['destination']}",
    }


def _save_diagnostics(driver: webdriver.Chrome, route: dict[str, Any], date_str: str) -> None:
    directory = Path(os.getenv("CRAWL_DEBUG_DIR", "debug_artifacts"))
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = f"{route['origin']}_{route['destination']}_{date_str}"
    try:
        (directory / f"{safe_name}.html").write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(directory / f"{safe_name}.png"))
        LOG.info("Saved Trip.com diagnostics to %s", directory)
    except Exception as exc:
        LOG.warning("Could not save diagnostics: %s", exc)


def date_range(start: str, end: str) -> list[str]:
    begin = datetime.strptime(start, "%Y-%m-%d").date()
    finish = datetime.strptime(end, "%Y-%m-%d").date()
    return [(begin + timedelta(days=i)).isoformat() for i in range((finish - begin).days + 1)]


def scrape_single_day(driver: webdriver.Chrome, route: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    url = generate_trip_url(route, date_str)
    LOG.info("Trip.com URL: %s", url)
    driver.set_page_load_timeout(45)
    try:
        driver.get(url)
    except TimeoutException:
        LOG.warning("Trip.com navigation timed out; continuing with loaded DOM")
        driver.execute_script("window.stop();")

    wait_seconds = int(route.get("wait_seconds", 35))
    try:
        WebDriverWait(driver, wait_seconds).until(lambda current: len(_find_cards(current)) > 0)
    except Exception:
        LOG.error("No Trip.com flight cards after %ss for %s", wait_seconds, date_str)
        _save_diagnostics(driver, route, date_str)
        return []
    time.sleep(3)

    cards = _find_cards(driver)
    LOG.info("Trip.com returned %d result card(s) for %s", len(cards), date_str)
    results: list[dict[str, Any]] = []
    for card in cards:
        try:
            parsed = parse_trip_card(card, route, date_str)
            if parsed:
                results.append(parsed)
        except Exception:
            LOG.exception("Failed to parse one Trip.com card")
    results.sort(key=lambda item: item["price"])
    return results[: int(route.get("top_n", 5))]


def crawl_route(driver: webdriver.Chrome, route: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        date_str: scrape_single_day(driver, route, date_str)
        for date_str in date_range(route["start"], route["end"])
    }
