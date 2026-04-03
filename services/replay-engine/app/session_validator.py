"""Trading session hour validation for VN30F."""

from datetime import datetime, time
from typing import Optional
from app.constants import TRADING_SESSIONS


class TradingSessionValidator:
    """Validates whether a given time falls within VN30F trading hours."""

    def __init__(self, strict: bool = True):
        """
        Args:
            strict: If True, reject orders outside trading hours.
                    If False, only log warnings.
        """
        self.strict = strict
        self._sessions = self._build_sessions()

    def _build_sessions(self) -> list:
        result = []
        for name, hours in TRADING_SESSIONS.items():
            start = time(hours["start"][0], hours["start"][1])
            end = time(hours["end"][0], hours["end"][1])
            result.append((name, start, end))
        return result

    def get_session_name(self, dt: datetime) -> Optional[str]:
        """Return the session name for a given datetime, or None if outside hours."""
        t = dt.time()
        for name, start, end in self._sessions:
            if start <= t < end:
                return name
        return None

    def is_trading_hour(self, dt: datetime) -> bool:
        """Check if the given datetime falls within any trading session."""
        return self.get_session_name(dt) is not None

    def validate_order_time(self, dt: datetime) -> tuple:
        """Validate order timing.

        Returns:
            (allowed: bool, session_name: Optional[str], message: str)
        """
        session = self.get_session_name(dt)
        if session:
            return True, session, f"Order in {session} session"
        if not self.strict:
            return True, None, "Outside trading hours (relaxed mode)"
        return False, None, f"Order rejected: outside trading hours at {dt.time()}"
