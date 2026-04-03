"""Session manager for concurrent trading sessions."""

import logging
from typing import Dict, Optional, List
from app.engine import ReplayEngine
from app.constants import DEFAULT_INITIAL_BALANCE

logger = logging.getLogger("replay-engine")


class SessionManager:
    """Manages multiple concurrent ReplayEngine sessions."""

    def __init__(self):
        self._sessions: Dict[str, ReplayEngine] = {}
        self._active_id: Optional[str] = None

    def create_session(
        self,
        session_id: str = "default",
        strategy: str = "manual",
        initial_balance: float = DEFAULT_INITIAL_BALANCE,
        strict_hours: bool = False,
    ) -> ReplayEngine:
        """Create a new trading session."""
        if session_id in self._sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        engine = ReplayEngine(
            session_id=session_id,
            initial_balance=initial_balance,
            strategy=strategy,
            strict_hours=strict_hours,
        )
        self._sessions[session_id] = engine

        if self._active_id is None:
            self._active_id = session_id

        logger.info(f"Created session '{session_id}' (strategy={strategy})")
        return engine

    def get_session(self, session_id: str) -> Optional[ReplayEngine]:
        return self._sessions.get(session_id)

    def get_active_engine(self) -> Optional[ReplayEngine]:
        """Get the currently active engine."""
        if self._active_id is None:
            return None
        return self._sessions.get(self._active_id)

    def switch_session(self, session_id: str) -> ReplayEngine:
        """Switch to a different session."""
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' not found")
        self._active_id = session_id
        logger.info(f"Switched to session '{session_id}'")
        return self._sessions[session_id]

    def list_sessions(self) -> List[dict]:
        """Return summary of all sessions."""
        result = []
        for sid, engine in self._sessions.items():
            result.append(
                {
                    "session_id": sid,
                    "strategy": engine.strategy,
                    "balance": round(engine.balance, 2),
                    "equity": round(engine.equity, 2),
                    "total_pnl": round(engine.total_pnl, 2),
                    "total_trades": len(engine.trade_history),
                    "active": sid == self._active_id,
                    "has_position": engine.active_position is not None,
                }
            )
        return result

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        if self._active_id == session_id:
            self._active_id = next(iter(self._sessions), None)
        return True

    def broadcast_tick(self, timestamp: str, price: float, regime: str = "unknown"):
        """Send a tick to ALL sessions (used for tournament mode)."""
        for engine in self._sessions.values():
            engine.process_tick(timestamp, price, regime)
