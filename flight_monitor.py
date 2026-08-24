"""Config, state and notification logic for the flight monitor.

The Selenium layer is deliberately kept separate so the comparison and
configuration code can be tested without launching a browser.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RouteConfig:
    id: str
    label: str
    origin: str
    destination: str
    depart_date: str
    depart_end: str
    return_date: str | None
    top_n: int
    skip_count: int
    enabled: bool
    max_price: int | None
    min_drop: int

    @property
    def key(self) -> str:
        return f"{self.origin}-{self.destination}-{self.depart_date}-{self.depart_end}-{self.return_date or 'oneway'}"


@dataclass(frozen=True)
class UserConfig:
    id: str
    name: str
    chat_id_env: str
    telegram_token_env: str
    enabled: bool
    routes: tuple[RouteConfig, ...]


def _require(value: Any, field: str) -> Any:
    if value is None or value == "":
        raise ValueError(f"Missing required field: {field}")
    return value


def _validate_date(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD: {value!r}") from exc
    return value


def load_config(path: str | Path) -> tuple[dict[str, Any], tuple[UserConfig, ...]]:
    """Load and validate a user-facing JSON configuration file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_users = payload.get("users")
    if not isinstance(raw_users, list) or not raw_users:
        raise ValueError("config must contain a non-empty users list")

    users: list[UserConfig] = []
    user_ids: set[str] = set()
    route_ids: set[tuple[str, str]] = set()
    defaults = payload.get("defaults", {})

    for raw_user in raw_users:
        user_id = str(_require(raw_user.get("id"), "users[].id"))
        if user_id in user_ids:
            raise ValueError(f"Duplicate user id: {user_id}")
        user_ids.add(user_id)
        raw_routes = raw_user.get("routes", [])
        routes: list[RouteConfig] = []
        for raw_route in raw_routes:
            route_id = str(_require(raw_route.get("id"), f"{user_id}.routes[].id"))
            route_identity = (user_id, route_id)
            if route_identity in route_ids:
                raise ValueError(f"Duplicate route id for {user_id}: {route_id}")
            route_ids.add(route_identity)
            origin = str(_require(raw_route.get("origin"), f"{route_id}.origin")).upper()
            destination = str(_require(raw_route.get("destination"), f"{route_id}.destination")).upper()
            if not re.fullmatch(r"[A-Z]{3}", origin) or not re.fullmatch(r"[A-Z]{3}", destination):
                raise ValueError(f"{route_id}: origin/destination must be IATA codes")
            depart_date = _validate_date(str(_require(raw_route.get("depart_date"), f"{route_id}.depart_date")), f"{route_id}.depart_date")
            depart_end = _validate_date(str(raw_route.get("depart_end", depart_date)), f"{route_id}.depart_end")
            if depart_end < depart_date:
                raise ValueError(f"{route_id}: depart_end must not be before depart_date")
            return_date = raw_route.get("return_date")
            if return_date is not None:
                return_date = _validate_date(str(return_date), f"{route_id}.return_date")
            top_n = int(raw_route.get("top_n", defaults.get("top_n", 5)))
            skip_count = int(raw_route.get("skip_count", defaults.get("skip_count", 3)))
            if top_n < 1 or skip_count < 0:
                raise ValueError(f"{route_id}: top_n must be positive and skip_count non-negative")
            max_price = raw_route.get("max_price")
            if max_price is not None:
                max_price = int(max_price)
                if max_price <= 0:
                    raise ValueError(f"{route_id}: max_price must be positive")
            routes.append(RouteConfig(
                id=route_id,
                label=str(raw_route.get("label", f"{origin} → {destination}")),
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                depart_end=depart_end,
                return_date=return_date,
                top_n=top_n,
                skip_count=skip_count,
                enabled=bool(raw_route.get("enabled", True)),
                max_price=max_price,
                min_drop=int(raw_route.get("min_drop", 0)),
            ))
        users.append(UserConfig(
            id=user_id,
            name=str(raw_user.get("name", user_id)),
            chat_id_env=str(_require(raw_user.get("chat_id_env"), f"{user_id}.chat_id_env")),
            telegram_token_env=str(raw_user.get("telegram_token_env", "TELEGRAM_BOT_TOKEN")),
            enabled=bool(raw_user.get("enabled", True)),
            routes=tuple(routes),
        ))
    return payload, tuple(users)


def route_to_atadi_config(route: RouteConfig) -> dict[str, Any]:
    """Return a browser-layer config without exposing Telegram credentials."""
    return {
        "id": route.id,
        "label": route.label,
        "route": f"{route.origin}.{route.destination}",
        "origin": route.origin,
        "destination": route.destination,
        "start": route.depart_date,
        "end": route.depart_end,
        "return_date": route.return_date,
        "top_n": route.top_n,
        "skip_count": route.skip_count,
        "enabled": route.enabled,
    }


def flight_key(flight: dict[str, Any]) -> str:
    return "|".join(str(flight.get(field, "Unknown")) for field in ("airline", "code", "time"))


def price_map(flights: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Use the lowest observed fare for a flight identity."""
    result: dict[str, int] = {}
    for flight in flights:
        try:
            price = int(flight["price"])
        except (KeyError, TypeError, ValueError):
            continue
        key = flight_key(flight)
        result[key] = min(price, result.get(key, price))
    return result


def compare_prices(previous: Iterable[dict[str, Any]], current: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    old = price_map(previous)
    new = price_map(current)
    events: dict[str, list[dict[str, Any]]] = {"new": [], "lower": [], "higher": [], "removed": []}
    for key, price in new.items():
        item = {"key": key, "price": price}
        if key not in old:
            events["new"].append(item)
        elif price < old[key]:
            events["lower"].append({**item, "old_price": old[key], "diff": price - old[key]})
        elif price > old[key]:
            events["higher"].append({**item, "old_price": old[key], "diff": price - old[key]})
    for key, price in old.items():
        if key not in new:
            events["removed"].append({"key": key, "old_price": price})
    return events


def best_price(flights: Iterable[dict[str, Any]]) -> int | None:
    prices = [int(f["price"]) for f in flights if f.get("price")]
    return min(prices) if prices else None


def format_vnd(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,}".replace(",", ".") + " đ"


def _event_lines(events: dict[str, list[dict[str, Any]]]) -> list[str]:
    lines: list[str] = []
    for label, key in (("Giá mới thấp hơn", "lower"), ("Chuyến/giá mới", "new"), ("Giá tăng", "higher"), ("Không còn thấy", "removed")):
        if events[key]:
            lines.append(f"{label}: {len(events[key])}")
            for item in events[key][:5]:
                suffix = ""
                if "old_price" in item:
                    suffix = f" ({format_vnd(item['old_price'])} → {format_vnd(item.get('price'))})"
                elif "price" in item:
                    suffix = f" ({format_vnd(item['price'])})"
                lines.append(f"• {item['key'].replace('|', ' · ')}{suffix}")
    return lines


def build_user_message(user: UserConfig, route: RouteConfig, current: list[dict[str, Any]], previous: list[dict[str, Any]] | None, now: datetime | None = None) -> tuple[str, bool]:
    events = compare_prices(previous or [], current)
    current_best = best_price(current)
    previous_best = best_price(previous or [])
    price_alert = route.max_price is not None and current_best is not None and current_best <= route.max_price
    drop_alert = previous_best is not None and current_best is not None and previous_best - current_best >= route.min_drop
    changed = any(events.values())
    should_alert = previous is None or changed or price_alert or drop_alert
    stamp = (now or datetime.now()).strftime("%H:%M %d/%m/%Y")
    date_label = route.depart_date if route.depart_date == route.depart_end else f"{route.depart_date} → {route.depart_end}"
    lines = [f"✈️ {route.label}", f"📅 Bay: {date_label}", f"🕒 Cập nhật: {stamp}"]
    if current_best is None:
        lines.append("⚠️ Không tìm thấy vé hoặc dữ liệu không hợp lệ.")
    else:
        lines.append(f"💰 Giá thấp nhất: {format_vnd(current_best)}")
        if route.max_price is not None:
            lines.append(f"🎯 Ngưỡng: {format_vnd(route.max_price)}")
        lines.append(f"📊 Đã lấy {len(current)} lựa chọn")
        if changed:
            lines.extend(_event_lines(events))
        else:
            lines.append("➖ Chưa có thay đổi so với lần crawl trước.")
    if price_alert:
        lines.append("🔥 Giá đã đạt ngưỡng bạn cài đặt.")
    return "\n".join(lines), should_alert


def read_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Write state safely so an interrupted run does not corrupt the snapshot."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
