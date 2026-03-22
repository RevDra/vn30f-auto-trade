from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List, Optional

class XAIEvaluation(BaseModel):
    reason: str
    metrics: Dict[str, Any]

class AdjudicatorResponse(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str = "VN30F1M"
    adjudicator_action: str
    final_position: str
    xai_explanation: XAIEvaluation

class SessionSummary(BaseModel):
    total_trades: int
    win_rate: float
    pnl_points: float
    pnl_vnd: int
    max_drawdown_percent: float
    margin_ratio_current: float

class ActivePosition(BaseModel):
    type: str
    volume: int
    entry_price: float
    current_price: float
    unrealized_pnl: float

class TimeseriesPnL(BaseModel):
    time: str
    pnl: float
    regime: str

class DashboardPnL(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str = "VN30F1M"
    session_summary: SessionSummary
    active_position: Optional[ActivePosition]
    timeseries_data: List[TimeseriesPnL]
