"use client";

import { AdvancedRealTimeChart } from "react-ts-tradingview-widgets";

import { EmptyState, LoadingState } from "@/components/state-blocks";
import type { MarketCandle } from "@/lib/api";

type TradingChartProps = {
  symbol?: string;
  interval?: string;
  candles?: MarketCandle[];
  loading?: boolean;
  error?: string | null;
};

export function TradingChart({ symbol = "BTCUSDT", interval = "1h", loading = false, error }: TradingChartProps) {
  // Map standard intervals to TradingView widget intervals
  let tvInterval: any = "60";
  if (interval === "1m") tvInterval = "1";
  else if (interval === "3m") tvInterval = "3";
  else if (interval === "5m") tvInterval = "5";
  else if (interval === "15m") tvInterval = "15";
  else if (interval === "30m") tvInterval = "30";
  else if (interval === "1h") tvInterval = "60";
  else if (interval === "2h") tvInterval = "120";
  else if (interval === "4h") tvInterval = "240";
  else if (interval === "1d") tvInterval = "D";
  else if (interval === "1w") tvInterval = "W";

  // Clean symbol and prepend BINANCE for accurate public data
  const cleanSymbol = symbol.replace("-", "").toUpperCase();
  const widgetSymbol = `BINANCE:${cleanSymbol}`;

  return (
    <section className="relative min-h-[460px] w-full overflow-hidden rounded-md border border-line bg-[#101722] shadow-terminal">
      {/* We keep the container styled for dark theme */}
      <div className="absolute inset-0">
        <AdvancedRealTimeChart
          symbol={widgetSymbol}
          theme="dark"
          interval={tvInterval}
          container_id="tv_chart_container"
          width="100%"
          height="100%"
          allow_symbol_change={false}
          hide_side_toolbar={false}
          enable_publishing={false}
          hide_top_toolbar={false}
          save_image={false}
          backgroundColor="#101722"
        />
      </div>
      
      {/* Only show loader if we truly don't know the symbol yet, 
          but TV Widget has its own loader too. */}
      {loading && !symbol ? (
        <div className="absolute inset-0 bg-[#101722]/88 z-10">
          <LoadingState title="Piyasa verisi yükleniyor" detail="TradingView grafiği hazırlanıyor..." className="h-full" />
        </div>
      ) : null}
      {!loading && error ? (
        <div className="absolute inset-0 bg-[#101722]/88 z-10">
          <EmptyState title="Piyasa verisi alınamadı" detail={error} className="h-full" />
        </div>
      ) : null}
    </section>
  );
}
