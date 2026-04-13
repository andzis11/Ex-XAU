"""
Layer 1 — Data Sources: News & sentiment feed.
Fetches economic calendar from Forex Factory and other sources.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import requests
import pandas as pd

from config import AppConfig

logger = logging.getLogger(__name__)


class NewsFeed:
    """Fetch economic calendar and news sentiment data."""

    # Impact level mapping
    IMPACT_MAP = {
        "High": 3,
        "Medium": 2,
        "Low": 1,
    }

    def __init__(self, config: AppConfig):
        self.config = config

    def get_forex_factory_calendar(
        self,
        days_ahead: int = 7
    ) -> pd.DataFrame:
        """
        Fetch Forex Factory economic calendar.
        Returns events filtered by impact level.
        """
        try:
            url = self.config.news.forex_factory_url
            response = requests.get(url, timeout=15)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            events = []

            for event in root.findall(".//event"):
                title_elem = event.find("title")
                country_elem = event.find("country")
                impact_elem = event.find("impact")
                date_elem = event.find("date")
                actual_elem = event.find("actual")
                forecast_elem = event.find("forecast")
                previous_elem = event.find("previous")

                impact = impact_elem.text if impact_elem is not None else "Low"

                # Filter high impact only if configured
                if self.config.news.high_impact_only and impact != "High":
                    continue

                events.append({
                    "title": title_elem.text if title_elem is not None else "",
                    "country": country_elem.text if country_elem is not None else "",
                    "impact": impact,
                    "impact_score": self.IMPACT_MAP.get(impact, 0),
                    "date": pd.to_datetime(date_elem.text) if date_elem is not None else None,
                    "actual": actual_elem.text if actual_elem is not None else None,
                    "forecast": forecast_elem.text if forecast_elem is not None else None,
                    "previous": previous_elem.text if previous_elem is not None else None,
                })

            df = pd.DataFrame(events)
            if df.empty:
                logger.info("No high-impact events found in calendar")
                return df

            # Sort by date
            df = df.sort_values("date").reset_index(drop=True)
            logger.info(f"Found {len(df)} high-impact economic events")
            return df

        except requests.RequestException as e:
            logger.error(f"Failed to fetch Forex Factory calendar: {e}")
            return pd.DataFrame()
        except ET.ParseError as e:
            logger.error(f"Failed to parse calendar XML: {e}")
            return pd.DataFrame()

    def get_upcoming_high_impact_events(
        self,
        hours_ahead: int = 24
    ) -> list:
        """
        Get high-impact events happening in the next N hours.
        Useful for avoiding trades around major news.
        """
        df = self.get_forex_factory_calendar()
        if df.empty:
            return []

        cutoff = datetime.utcnow() + timedelta(hours=hours_ahead)
        upcoming = df[df["date"] <= pd.Timestamp(cutoff)]

        events = []
        for _, row in upcoming.iterrows():
            events.append({
                "title": row["title"],
                "country": row["country"],
                "date": row["date"],
                "impact": row["impact"],
            })

        return events

    def is_news_blackout(self, hours_before: int = 1) -> tuple:
        """
        Check if we're in a news blackout period (1 hour before high-impact news).
        Returns (is_blackout, event_info).
        """
        upcoming = self.get_upcoming_high_impact_events(hours_ahead=hours_before + 1)

        for event in upcoming:
            event_time = event["date"]
            if isinstance(event_time, pd.Timestamp):
                event_time = event_time.to_pydatetime()

            time_diff = event_time - datetime.utcnow()
            if 0 < time_diff.total_seconds() < hours_before * 3600:
                return True, event

        return False, None

    def get_market_sentiment_summary(self) -> dict:
        """
        Generate a market sentiment summary based on upcoming news.
        Used for LLM context in Layer 2.
        """
        upcoming = self.get_upcoming_high_impact_events(hours_ahead=48)

        if not upcoming:
            return {
                "summary": "No high-impact economic events in the next 48 hours.",
                "risk_level": "low",
                "event_count": 0,
            }

        # Count by country
        country_counts = {}
        for event in upcoming:
            country = event.get("country", "Unknown")
            country_counts[country] = country_counts.get(country, 0) + 1

        # Build summary
        event_titles = [e["title"] for e in upcoming[:5]]  # Top 5 events
        risk_level = "high" if len(upcoming) > 5 else "medium"

        return {
            "summary": f"{len(upcoming)} high-impact events in 48h: {', '.join(event_titles)}",
            "events_by_country": country_counts,
            "risk_level": risk_level,
            "event_count": len(upcoming),
            "events": upcoming,
        }
