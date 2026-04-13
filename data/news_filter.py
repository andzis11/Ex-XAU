"""
News Filter — Pause trading during high-impact economic events.
Supports XAU/USD (sensitive to USD news) and BTC/USD.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# High-impact USD events that affect XAU/USD
HIGH_IMPACT_EVENTS = [
    "NFP",           # Non-Farm Payrolls
    "CPI",           # Consumer Price Index
    "FOMC",          # Federal Open Market Committee
    "Fed Rate",      # Interest Rate Decision
    "PPI",           # Producer Price Index
    "Retail Sales",
    "ISM Manufacturing",
    "ISM Services",
    "GDP",
    "Unemployment Claims",
]

# Pause window: minutes before/after event
PAUSE_WINDOW_MINUTES = 30


class NewsFilter:
    """
    Checks for upcoming high-impact news events and signals
    when the bot should pause trading.
    """

    # Free economic calendar API (ForexFactory alternative)
    CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    def __init__(self):
        self._events_cache = []
        self._last_fetch = None
        self._is_in_blackout = False
        self._blackout_reason = ""

    def fetch_events(self, force_refresh: bool = False) -> list:
        """
        Fetch economic calendar events for this week.
        Returns list of dicts with event info.
        """
        # Cache for 1 hour
        if (
            not force_refresh
            and self._events_cache
            and self._last_fetch
            and datetime.now() - self._last_fetch < timedelta(hours=1)
        ):
            return self._events_cache

        try:
            resp = requests.get(self.CALENDAR_URL, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Calendar fetch failed: HTTP {resp.status_code}")
                return []

            # Parse XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)

            events = []
            for event in root.findall(".//event"):
                title = event.findtext("title", "")
                date_str = event.findtext("date", "")
                impact = event.findtext("impact", "")  # "High", "Medium", "Low"
                country = event.findtext("country", "")

                # Only high-impact USD events
                if impact == "High" and "USD" in country.upper():
                    try:
                        event_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue

                    events.append({
                        "title": title,
                        "date": event_date,
                        "impact": impact,
                        "country": country,
                    })

            self._events_cache = events
            self._last_fetch = datetime.now()
            logger.info(f"Fetched {len(events)} high-impact USD events")
            return events

        except Exception as e:
            logger.error(f"News filter error: {e}")
            return []

    def check_blackout(self, symbol: str = "XAUUSD") -> tuple:
        """
        Check if we're in a news blackout window.

        Args:
            symbol: Trading symbol to check

        Returns:
            (is_blackout, reason) tuple
        """
        events = self.fetch_events()
        now = datetime.now()

        for event in events:
            event_time = event["date"]
            time_diff = abs((event_time - now).total_seconds()) / 60  # minutes

            # Check if within pause window
            if time_diff <= PAUSE_WINDOW_MINUTES:
                # Check if event is relevant to symbol
                is_relevant = self._is_event_relevant(event, symbol)

                if is_relevant:
                    direction = "before" if event_time > now else "after"
                    reason = (
                        f"News blackout: {event['title']} "
                        f"({direction}, {time_diff:.0f} min)"
                    )
                    logger.warning(reason)
                    self._is_in_blackout = True
                    self._blackout_reason = reason
                    return True, reason

        self._is_in_blackout = False
        self._blackout_reason = ""
        return False, ""

    @staticmethod
    def _is_event_relevant(event: dict, symbol: str) -> bool:
        """Check if an event is relevant to a trading symbol."""
        title_upper = event["title"].upper()

        # Check if event title contains high-impact keywords
        for keyword in HIGH_IMPACT_EVENTS:
            if keyword.upper() in title_upper:
                return True

        return False

    @property
    def is_in_blackout(self) -> bool:
        return self._is_in_blackout

    @property
    def blackout_reason(self) -> str:
        return self._blackout_reason

    def get_upcoming_events(self, hours_ahead: int = 4) -> list:
        """Get events scheduled in the next N hours."""
        events = self.fetch_events()
        now = datetime.now()
        cutoff = now + timedelta(hours=hours_ahead)

        upcoming = []
        for event in events:
            if now <= event["date"] <= cutoff:
                upcoming.append(event)

        return upcoming
