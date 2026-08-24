from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atadi_crawler import crawl_route, init_driver
from flight_monitor import (
    atomic_write_json,
    build_user_message,
    load_config,
    read_json,
    route_to_atadi_config,
)
from telegram_notifier import send_from_environment


LOG = logging.getLogger("flight-monitor")


def route_state(previous_user: dict[str, Any], route_id: str) -> dict[str, Any]:
    return previous_user.get("routes", {}).get(route_id, {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl configured flight routes once and notify Telegram")
    parser.add_argument("--config", default="config/users.json")
    parser.add_argument("--state", default="state/latest.json")
    parser.add_argument("--dry-run", action="store_true", help="Do not send Telegram messages")
    args = parser.parse_args()

    _, users = load_config(args.config)
    old_state = read_json(args.state, {"users": {}})
    old_users = old_state.get("users", {})
    new_state: dict[str, Any] = {
        "schema_version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "users": {},
    }
    driver = None
    successful_routes = 0
    try:
        driver = init_driver()
        for user in users:
            if not user.enabled:
                continue
            old_user = old_users.get(user.id, {})
            new_state["users"][user.id] = {"name": user.name, "routes": {}}
            for route in user.routes:
                if not route.enabled:
                    continue
                LOG.info("Crawling %s / %s", user.id, route.id)
                current_data = crawl_route(driver, route_to_atadi_config(route))
                new_state["users"][user.id]["routes"][route.id] = {
                    "label": route.label,
                    "origin": route.origin,
                    "destination": route.destination,
                    "depart_date": route.depart_date,
                    "depart_end": route.depart_end,
                    "data": current_data,
                    "last_success_at": datetime.now(timezone.utc).isoformat(),
                }
                successful_routes += 1

                old_route = route_state(old_user, route.id)
                old_data = old_route.get("data", {})
                messages: list[str] = []
                for date_str, flights in current_data.items():
                    report_route = replace(route, depart_date=date_str, depart_end=date_str)
                    message, should_alert = build_user_message(
                        user,
                        report_route,
                        flights,
                        old_data.get(date_str) if isinstance(old_data, dict) else None,
                    )
                    if should_alert:
                        messages.append(message)
                if messages and not args.dry_run:
                    send_from_environment(user.telegram_token_env, user.chat_id_env, "\n\n".join(messages))
                elif messages:
                    LOG.info("DRY RUN for %s/%s:\n%s", user.id, route.id, "\n\n".join(messages))

        atomic_write_json(args.state, new_state)
        LOG.info("Completed %d route(s)", successful_routes)
        return 0
    except Exception:
        LOG.exception("The crawl run failed; previous state was left untouched")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
