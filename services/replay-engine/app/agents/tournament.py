"""Tournament mode — multiple agents trade same market data simultaneously."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from enum import Enum

from app.session import SessionManager
from app.agents.agent_manager import AgentManager, AgentConfig
from app.agents.leaderboard import LeaderboardCalculator, SortMetric

logger = logging.getLogger("replay-engine.tournament")


class TournamentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TournamentConfig:
    """Tournament configuration."""
    name: str
    initial_balance: float = 500_000_000.0
    strict_hours: bool = False
    max_agents: int = 20


class TournamentManager:
    """Orchestrates tournaments where agents compete on the same market data."""

    def __init__(self, session_mgr: SessionManager):
        self._session_mgr = session_mgr
        self._agent_mgr = AgentManager(session_mgr)
        self._leaderboard = LeaderboardCalculator(self._agent_mgr)
        self._config: Optional[TournamentConfig] = None
        self._status = TournamentStatus.PENDING
        self._started_at: Optional[datetime] = None
        self._ended_at: Optional[datetime] = None
        self._tick_count: int = 0

    @property
    def agent_manager(self) -> AgentManager:
        return self._agent_mgr

    @property
    def leaderboard(self) -> LeaderboardCalculator:
        return self._leaderboard

    @property
    def status(self) -> TournamentStatus:
        return self._status

    def create_tournament(self, config: TournamentConfig):
        """Initialize a new tournament."""
        if self._status == TournamentStatus.RUNNING:
            raise ValueError("A tournament is already running — stop it first")

        self._config = config
        self._status = TournamentStatus.PENDING
        self._started_at = None
        self._ended_at = None
        self._tick_count = 0
        logger.info("Tournament '%s' created", config.name)

    def add_agent(self, config: AgentConfig) -> dict:
        """Add an agent to the tournament."""
        if self._config is None:
            raise ValueError("No tournament created — call create_tournament first")

        if len(self._agent_mgr.get_agent_ids()) >= self._config.max_agents:
            raise ValueError(f"Tournament full (max {self._config.max_agents} agents)")

        # Override balance with tournament balance
        config.initial_balance = self._config.initial_balance
        config.strict_hours = self._config.strict_hours

        engine = self._agent_mgr.register_agent(config)
        return {
            "agent_id": config.agent_id,
            "session_id": engine.session_id,
            "initial_balance": config.initial_balance,
        }

    def remove_agent(self, agent_id: str) -> bool:
        return self._agent_mgr.unregister_agent(agent_id)

    def start(self):
        """Start the tournament."""
        if self._config is None:
            raise ValueError("No tournament created")
        if not self._agent_mgr.get_agent_ids():
            raise ValueError("No agents registered")
        if self._status == TournamentStatus.RUNNING:
            raise ValueError("Tournament already running")

        self._status = TournamentStatus.RUNNING
        self._started_at = datetime.now(timezone.utc)
        logger.info("Tournament '%s' started with %d agents",
                     self._config.name, len(self._agent_mgr.get_agent_ids()))

    def pause(self):
        if self._status != TournamentStatus.RUNNING:
            raise ValueError("Tournament not running")
        self._status = TournamentStatus.PAUSED
        logger.info("Tournament paused")

    def resume(self):
        if self._status != TournamentStatus.PAUSED:
            raise ValueError("Tournament not paused")
        self._status = TournamentStatus.RUNNING
        logger.info("Tournament resumed")

    def stop(self):
        """End the tournament and freeze results."""
        if self._status not in (TournamentStatus.RUNNING, TournamentStatus.PAUSED):
            raise ValueError("Tournament not active")
        self._status = TournamentStatus.COMPLETED
        self._ended_at = datetime.now(timezone.utc)
        logger.info("Tournament '%s' completed after %d ticks", self._config.name, self._tick_count)

    def cancel(self):
        self._status = TournamentStatus.CANCELLED
        self._ended_at = datetime.now(timezone.utc)
        logger.info("Tournament cancelled")

    def process_tick(self, timestamp: str, price: float, regime: str = "unknown"):
        """Feed a tick to ALL tournament agents simultaneously."""
        if self._status != TournamentStatus.RUNNING:
            return

        self._tick_count += 1
        for agent_id in self._agent_mgr.get_agent_ids():
            engine = self._agent_mgr.get_agent_engine(agent_id)
            if engine:
                engine.process_tick(timestamp, price, regime)

    def get_standings(self, sort_by: SortMetric = SortMetric.PNL) -> dict:
        """Get current tournament standings."""
        return {
            "tournament": self._config.name if self._config else None,
            "status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "tick_count": self._tick_count,
            "agent_count": len(self._agent_mgr.get_agent_ids()),
            "leaderboard": self._leaderboard.get_leaderboard(sort_by=sort_by),
        }

    def get_state(self) -> dict:
        """Full tournament state snapshot."""
        return {
            "config": {
                "name": self._config.name,
                "initial_balance": self._config.initial_balance,
                "max_agents": self._config.max_agents,
            } if self._config else None,
            "status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "tick_count": self._tick_count,
            "agents": self._agent_mgr.list_agents(),
        }
