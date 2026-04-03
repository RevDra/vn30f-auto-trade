import type { Trade, ActivePosition } from "../types/api";

interface TradeHistoryProps {
  trades: Trade[];
  total: number;
}

export function TradeHistory({ trades, total }: TradeHistoryProps) {
  return (
    <div className="bg-surface-card rounded-lg border border-gray-800 p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-3">
        Trade History <span className="text-gray-600">({total})</span>
      </h2>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="text-gray-500 border-b border-gray-800">
            <tr>
              <th className="text-left py-2 px-1">Time</th>
              <th className="text-left py-2 px-1">Dir</th>
              <th className="text-right py-2 px-1">Vol</th>
              <th className="text-right py-2 px-1">Entry</th>
              <th className="text-right py-2 px-1">Exit</th>
              <th className="text-right py-2 px-1">Net PnL</th>
              <th className="text-right py-2 px-1">Fees</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-4 text-gray-600">No trades yet</td></tr>
            ) : (
              trades.map((t, i) => (
                <tr key={i} className="border-b border-gray-800/50 hover:bg-surface-hover">
                  <td className="py-1.5 px-1 text-gray-400">{formatTime(t.exit_time)}</td>
                  <td className={`py-1.5 px-1 font-medium ${t.type === "LONG" ? "text-accent-green" : "text-accent-red"}`}>
                    {t.type}
                  </td>
                  <td className="py-1.5 px-1 text-right">{t.volume}</td>
                  <td className="py-1.5 px-1 text-right">{t.entry_price.toFixed(1)}</td>
                  <td className="py-1.5 px-1 text-right">{t.exit_price.toFixed(1)}</td>
                  <td className={`py-1.5 px-1 text-right font-medium ${t.net_pnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {formatVND(t.net_pnl)}
                  </td>
                  <td className="py-1.5 px-1 text-right text-gray-500">{formatVND(t.commission + t.tax)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface PositionPanelProps {
  position: ActivePosition | null;
}

export function PositionPanel({ position }: PositionPanelProps) {
  return (
    <div className="bg-surface-card rounded-lg border border-gray-800 p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-3">Active Position</h2>
      {!position ? (
        <div className="text-center text-gray-600 py-4">No position</div>
      ) : (
        <div className="space-y-2">
          <div className="flex justify-between">
            <span className="text-gray-500">Direction</span>
            <span className={`font-semibold ${position.type === "LONG" ? "text-accent-green" : "text-accent-red"}`}>
              {position.type}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Volume</span>
            <span>{position.volume}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Entry</span>
            <span>{position.entry_price.toFixed(1)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Current</span>
            <span>{position.current_price.toFixed(1)}</span>
          </div>
          <div className="flex justify-between border-t border-gray-800 pt-2">
            <span className="text-gray-500">Unrealized PnL</span>
            <span className={`font-semibold ${position.unrealized_pnl >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {formatVND(position.unrealized_pnl)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function formatVND(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}
