"""
News Filter + Session Filter — Pause trading during high-impact events
and outside trading hours.
Supports XAU/USD (sensitive to USD news) and BTC/USD.
"""

import logging
from datetime import datetime, timedelta, timezone
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

# Trading sessions (UTC)
TRADING_SESSIONS = {
    "london_open":   (7, 9),    # 07:00-09:00 UTC
    "london_ny":     (12, 16),  # 12:00-16:00 UTC (overlap)
    "ny_close":      (20, 22),  # 20:00-22:00 UTC
}


class NewsFilter:
    """
    Checks for upcoming high-impact news events and trading sessions.
    Signals when the bot should pause trading.
    """

    CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    def __init__(
        self,
        session_filter_enabled: bool = True,
        session_start_utc: int = 7,
        session_end_utc: int = 22,
    ):
        self.session_filter_enabled = session_filter_enabled
        self.session_start = session_start_utc
        self.session_end = session_end_utc
        self._events_cache = []
        self._last_fetch = None
        self._is_in_blackout = False
        self._blackout_reason = ""

    def fetch_events(self, force_refresh: bool = False) -> list:
        """Fetch economic calendar events for this week."""
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

            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)

            events = []
            for event in root.findall(".//event"):
                title = event.findtext("title", "")
                date_str = event.findtext("date", "")
                impact = event.findtext("impact", "")
                country = event.findtext("country", "")

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
        Check if we're in a news blackout or outside trading hours.

        Returns:
            (is_blackout, reason) tuple
        """
        # ── Session filter ──
        if self.session_filter_enabled:
            now_utc = datetime.now(timezone.utc)
            current_hour = now_utc.hour

            if current_hour < self.session_start or current_hour >= self.session_end:
                reason = (
                    f"Outside trading hours ({self.session_start}:00-{self.session_end}:00 UTC). "
                    f"Current: {current_hour}:00 UTC"
                )
                logger.info(f"SESSION FILTER: {reason}")
                self._is_in_blackout = True
                self._blackout_reason = reason
                return True, reason

        # ── News blackout ──
        events = self.fetch_events()
        now = datetime.now()

        for event in events:
            event_time = event["date"]
            time_diff = abs((event_time - now).total_seconds()) / 60

            if time_diff <= PAUSE_WINDOW_MINUTES:
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

    def is_within_session(self) -> bool:
        """Check if current time is within trading session."""
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        return self.session_start <= current_hour < self.session_end

    def get_session_name(self) -> str:
        """Get current trading session name."""
        now_utc = datetime.now(timezone.utc).hour
        if 7 <= now_utc < 9:
            return "London Open"
        elif 12 <= now_utc < 16:
            return "London-NY Overlap"
        elif 20 <= now_utc < 22:
            return "NY Close"
        else:
            return "Off Hours"

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
