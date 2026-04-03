import { useState, useEffect, useCallback } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useApi } from "./hooks/useApi";
import { CandlestickChart } from "./components/CandlestickChart";
import { MetricsCards, EquityCurve } from "./components/EquityMetrics";
import { TradeHistory, PositionPanel } from "./components/TradePosition";
import { OrderPanel } from "./components/OrderPanel";
import type { PnLResponse, TradesResponse, EquityCurveResponse } from "./types/api";

const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/live`;

export default function App() {
  const { status, lastMessage } = useWebSocket(WS_URL);
  const { data: pnl, refetch: refetchPnl } = useApi<PnLResponse>("/pnl", 5000);
  const { data: trades, refetch: refetchTrades } = useApi<TradesResponse>("/trades", 5000);
  const { data: equity, refetch: refetchEquity } = useApi<EquityCurveResponse>("/equity-curve", 10000);

  const handleOrderPlaced = useCallback(() => {
    refetchPnl();
    refetchTrades();
    refetchEquity();
  }, [refetchPnl, refetchTrades, refetchEquity]);

  return (
    <div className="min-h-screen bg-surface">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold">VN30F Dashboard</h1>
          <span className="text-xs text-gray-500">Mock Exchange</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-500">
            WS: <span className={status === "connected" ? "text-accent-green" : "text-accent-red"}>{status}</span>
          </span>
          {pnl && (
            <span className="text-xs text-gray-500">
              Session: <span className="text-gray-300">{pnl.session_id}</span>
            </span>
          )}
        </div>
      </header>

      {/* Main layout */}
      <main className="p-4 grid grid-cols-12 gap-4">
        {/* Left: Chart + Equity */}
        <div className="col-span-8 space-y-4">
          <CandlestickChart lastMessage={lastMessage} />
          <EquityCurve data={equity} />
          <TradeHistory trades={trades?.trades ?? []} total={trades?.total ?? 0} />
        </div>

        {/* Right: Metrics + Position + Order */}
        <div className="col-span-4 space-y-4">
          <MetricsCards pnl={pnl} />
          <PositionPanel position={pnl?.active_position ?? null} />
          <OrderPanel
            hasPosition={!!pnl?.active_position}
            onOrderPlaced={handleOrderPlaced}
          />
        </div>
      </main>
    </div>
  );
}
