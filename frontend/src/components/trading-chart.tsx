"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type CandlestickData,
  type LineData,
  type IChartApi,
  type UTCTimestamp
} from "lightweight-charts";

import { EmptyState, LoadingState } from "@/components/state-blocks";
import type { MarketCandle } from "@/lib/api";

type TradingChartProps = {
  candles: MarketCandle[];
  loading?: boolean;
  error?: string | null;
};

export function TradingChart({ candles, loading = false, error }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart: IChartApi = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#101722" },
        textColor: "#94a3b8"
      },
      grid: {
        horzLines: { color: "#202b3a" },
        vertLines: { color: "#202b3a" }
      },
      rightPriceScale: {
        borderColor: "#263241"
      },
      timeScale: {
        borderColor: "#263241",
        timeVisible: true
      },
      crosshair: {
        mode: 1
      }
    });

    const series = chart.addCandlestickSeries({
      upColor: "#2dd4bf",
      borderUpColor: "#2dd4bf",
      wickUpColor: "#2dd4bf",
      downColor: "#f43f5e",
      borderDownColor: "#f43f5e",
      wickDownColor: "#f43f5e"
    });

    const chartData: CandlestickData[] = candles.map((candle) => ({
      time: Math.floor(candle.open_time / 1000) as UTCTimestamp,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close
    }));

    series.setData(chartData);

    // Calculate Bollinger Bands
    const period = 20;
    const upperData: LineData[] = [];
    const lowerData: LineData[] = [];
    const middleData: LineData[] = [];

    for (let i = 0; i < chartData.length; i++) {
      if (i < period - 1) continue;
      
      const slice = chartData.slice(i - period + 1, i + 1);
      const mean = slice.reduce((acc, val) => acc + val.close, 0) / period;
      const variance = slice.reduce((acc, val) => acc + Math.pow(val.close - mean, 2), 0) / period;
      const stdDev = Math.sqrt(variance);
      
      const time = chartData[i].time;
      middleData.push({ time, value: mean });
      upperData.push({ time, value: mean + 2 * stdDev });
      lowerData.push({ time, value: mean - 2 * stdDev });
    }

    const upperSeries = chart.addLineSeries({
      color: "rgba(59, 130, 246, 0.4)",
      lineWidth: 1,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
    });
    const middleSeries = chart.addLineSeries({
      color: "rgba(234, 179, 8, 0.6)",
      lineWidth: 1,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
    });
    const lowerSeries = chart.addLineSeries({
      color: "rgba(59, 130, 246, 0.4)",
      lineWidth: 1,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
    });

    upperSeries.setData(upperData);
    middleSeries.setData(middleData);
    lowerSeries.setData(lowerData);

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [candles]);

  return (
    <section className="relative min-h-[360px] overflow-hidden rounded-md border border-line bg-[#101722] shadow-terminal">
      <div ref={containerRef} className="absolute inset-0" />
      {loading ? (
        <div className="absolute inset-0 bg-[#101722]/88">
          <LoadingState title="Piyasa verisi yükleniyor" detail="Binance public candles okunuyor." className="h-full" />
        </div>
      ) : null}
      {!loading && error ? (
        <div className="absolute inset-0 bg-[#101722]/88">
          <EmptyState title="Piyasa verisi alınamadı" detail={error} className="h-full" />
        </div>
      ) : null}
      {!loading && !error && candles.length === 0 ? (
        <div className="absolute inset-0 bg-[#101722]/88">
          <EmptyState
            title="Henüz piyasa verisi yok"
            detail="Sembol veya zaman aralığını yenileyerek tekrar deneyin."
            className="h-full"
          />
        </div>
      ) : null}
    </section>
  );
}
