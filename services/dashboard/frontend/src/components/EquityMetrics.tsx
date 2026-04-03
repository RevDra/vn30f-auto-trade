import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import type { PnLResponse, EquityCurveResponse } from "../types/api";

interface MetricsCardsProps {
  pnl: PnLResponse | null;
}

export function MetricsCards({ pnl }: MetricsCardsProps) {
  if (!pnl) return <MetricsSkeleton />;
  const s = pnl.session_summary;
  const cards = [
    { label: "Win Rate", value: `${(s.win_rate * 100).toFixed(1)}%`, color: s.win_rate >= 0.5 ? "text-accent-green" : "text-accent-red" },
    { label: "Total PnL", value: formatVND(s.pnl_vnd), color: s.pnl_vnd >= 0 ? "text-accent-green" : "text-accent-red" },
    { label: "Max Drawdown", value: `${s.max_drawdown_percent.toFixed(2)}%`, color: "text-accent-yellow" },
    { label: "Sharpe Ratio", value: s.sharpe_ratio.toFixed(3), color: s.sharpe_ratio >= 1 ? "text-accent-green" : "text-gray-300" },
    { label: "Balance", value: formatVND(pnl.balance), color: "text-accent-blue" },
    { label: "Equity", value: formatVND(pnl.equity), color: "text-accent-blue" },
  ];

  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="bg-surface-card rounded-lg border border-gray-800 p-3">
          <div className="text-xs text-gray-500">{c.label}</div>
          <div className={`text-lg font-semibold ${c.color}`}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}

interface EquityCurveProps {
  data: EquityCurveResponse | null;
}

export function EquityCurve({ data }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#161a25" }, textColor: "#9ca3af" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true },
      width: containerRef.current.clientWidth,
      height: 200,
    });

    const series = chart.addAreaSeries({
      lineColor: "#3b82f6",
      topColor: "#3b82f620",
      bottomColor: "#3b82f605",
      lineWidth: 2,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => containerRef.current && chart.applyOptions({ width: containerRef.current.clientWidth });
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.remove(); };
  }, []);

  useEffect(() => {
    if (!data?.timeseries?.length || !seriesRef.current) return;
    const points = data.timeseries.map((p, i) => ({
      time: (p.time ? new Date(p.time).getTime() / 1000 : i) as Time,
      value: p.equity,
    }));
    seriesRef.current.setData(points);
  }, [data]);

  return (
    <div className="bg-surface-card rounded-lg border border-gray-800 p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-2">Equity Curve</h2>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}

function MetricsSkeleton() {
  return (
    <div className="grid grid-cols-3 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="bg-surface-card rounded-lg border border-gray-800 p-3 animate-pulse">
          <div className="h-3 bg-gray-700 rounded w-16 mb-2" />
          <div className="h-5 bg-gray-700 rounded w-24" />
        </div>
      ))}
    </div>
  );
}

function formatVND(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}
