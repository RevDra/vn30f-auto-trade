"""Agent session isolation — each agent gets its own isolated trading session."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

from app.session import SessionManager
from app.engine import ReplayEngine
from app.constants import DEFAULT_INITIAL_BALANCE

logger = logging.getLogger("replay-engine.agents")


@dataclass
class AgentConfig:
    """Configuration for a trading agent."""
    agent_id: str
    name: str
    strategy: str = "ai"
    initial_balance: float = DEFAULT_INITIAL_BALANCE
    confidence_threshold: float = 0.6
    max_volume: int = 10
    strict_hours: bool = False
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "strategy": self.strategy,
            "initial_balance": self.initial_balance,
            "confidence_threshold": self.confidence_threshold,
            "max_volume": self.max_volume,
            "strict_hours": self.strict_hours,
            "enabled": self.enabled,
        }


class AgentManager:
    """Manages agent registration, isolation, and session mapping.

    Each agent gets its own ReplayEngine session via SessionManager,
    ensuring complete PnL isolation between agents.
    """

    def __init__(self, session_mgr: SessionManager):
        self._session_mgr = session_mgr
        self._agents: Dict[str, AgentConfig] = {}
        self._registered_at: Dict[str, datetime] = {}

    def register_agent(self, config: AgentConfig) -> ReplayEngine:
        """Register a new agent and create its isolated session."""
        if config.agent_id in self._agents:
            raise ValueError(f"Agent '{config.agent_id}' already registered")

        session_id = f"agent_{config.agent_id}"

        engine = self._session_mgr.create_session(
            session_id=session_id,
            strategy=config.strategy,
            initial_balance=config.initial_balance,
            strict_hours=config.strict_hours,
        )

        self._agents[config.agent_id] = config
        self._registered_at[config.agent_id] = datetime.now(timezone.utc)
        logger.info("Registered agent '%s' (%s) → session '%s'", config.agent_id, config.name, session_id)
        return engine

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent and its session."""
        if agent_id not in self._agents:
            return False
        session_id = f"agent_{agent_id}"
        self._session_mgr.delete_session(session_id)
        del self._agents[agent_id]
        self._registered_at.pop(agent_id, None)
        logger.info("Unregistered agent '%s'", agent_id)
        return True

    def get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        return self._agents.get(agent_id)

    def get_agent_engine(self, agent_id: str) -> Optional[ReplayEngine]:
        """Get the isolated engine for an agent."""
        if agent_id not in self._agents:
            return None
        return self._session_mgr.get_session(f"agent_{agent_id}")

    def list_agents(self) -> List[dict]:
        """List all registered agents with their current state."""
        result = []
        for agent_id, config in self._agents.items():
            engine = self.get_agent_engine(agent_id)
            info = config.to_dict()
            info["registered_at"] = self._registered_at.get(agent_id, datetime.now(timezone.utc)).isoformat()
            if engine:
                info["balance"] = round(engine.balance, 2)
                info["equity"] = round(engine.equity, 2)
                info["total_pnl"] = round(engine.total_pnl, 2)
                info["total_trades"] = len(engine.trade_history)
                info["has_position"] = engine.active_position is not None
            result.append(info)
        return result

    def get_agent_ids(self) -> List[str]:
        return list(self._agents.keys())

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def place_agent_order(self, agent_id: str, action: str, volume: int) -> dict:
        """Place an order for a specific agent."""
        config = self._agents.get(agent_id)
        if config is None:
            raise ValueError(f"Agent '{agent_id}' not registered")
        if not config.enabled:
            raise ValueError(f"Agent '{agent_id}' is disabled")

        volume = min(volume, config.max_volume)
        engine = self.get_agent_engine(agent_id)
        if engine is None:
            raise ValueError(f"No engine for agent '{agent_id}'")

        return engine.place_order(action, volume)
