/** TypeScript types for Dashboard API responses. */

export interface SessionSummary {
  total_trades: number;
  win_rate: number;
  pnl_vnd: number;
  max_drawdown_percent: number;
  sharpe_ratio: number;
  total_commission: number;
  total_tax: number;
}

export interface ActivePosition {
  type: "LONG" | "SHORT";
  volume: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
}

export interface PnLResponse {
  timestamp: string;
  symbol: string;
  session_id: string;
  balance: number;
  equity: number;
  session_summary: SessionSummary;
  active_position: ActivePosition | null;
}

export interface Trade {
  entry_time: string;
  exit_time: string;
  type: "LONG" | "SHORT";
  volume: number;
  entry_price: number;
  exit_price: number;
  gross_pnl: number;
  commission: number;
  tax: number;
  net_pnl: number;
}

export interface TradesResponse {
  total: number;
  page: number;
  page_size: number;
  trades: Trade[];
}

export interface EquityCurveResponse {
  session_id: string;
  initial_balance: number;
  points: number;
  equity_curve: number[];
  timeseries: Array<{ time: string; equity: number; pnl: number; regime: string }>;
}

export interface SessionInfo {
  session_id: string;
  strategy: string;
  balance: number;
  equity: number;
  total_pnl: number;
  total_trades: number;
  active: boolean;
  has_position: boolean;
}

export interface WSMessage {
  channel: string;
  data: Record<string, unknown>;
}

export interface MarketTick {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}
