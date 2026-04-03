import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickData, Time } from "lightweight-charts";
import type { WSMessage, MarketTick } from "../types/api";

interface Props {
  lastMessage: WSMessage | null;
}

export function CandlestickChart({ lastMessage }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#161a25" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 400,
    });

    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });

    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
 
    chartRef.current = chart;
    seriesRef.current = series;
    volumeRef.current = volume;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Process incoming market data
  useEffect(() => {
    if (!lastMessage || lastMessage.channel !== "market_data_vn30f1m") return;
    const tick = lastMessage.data as unknown as MarketTick;
    if (!tick.timestamp || !tick.close) return;

    const time = (new Date(tick.timestamp).getTime() / 1000) as Time;

    const candle: CandlestickData = {
      time,
      open: tick.open || tick.close,
      high: tick.high || tick.close,
      low: tick.low || tick.close,
      close: tick.close,
    };

    seriesRef.current?.update(candle);

    if (tick.volume !== undefined) {
      volumeRef.current?.update({
        time,
        value: tick.volume,
        color: tick.close >= (tick.open || tick.close) ? "#22c55e40" : "#ef444440",
      });
    }
  }, [lastMessage]);

  return (
    <div className="bg-surface-card rounded-lg border border-gray-800 p-4">
      <h2 className="text-sm font-medium text-gray-400 mb-2">VN30F1M — Live Chart</h2>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
