// ---------------------------------------------------------------------------
// Types — backend model mirrors
// ---------------------------------------------------------------------------

export type RiskLimits = {
  risk_per_trade: number;
  max_single_position_pct: number;
  max_total_exposure_pct: number;
  max_open_positions: number;
  daily_loss_limit_pct: number;
  max_drawdown_limit_pct: number;
  min_risk_reward: number;
  cooldown_after_losses: number;
  stop_loss_required: boolean;
};

export type SystemStatus = {
  trading_mode: "paper" | "testnet";
  trading_halted: boolean;
  halt_reason: string;
  worker_state: "safe_idle" | "halted";
  live_orders_enabled: boolean;
  ai_order_access: boolean;
  exchange_keys_configured: boolean;
  updated_at: string;
  risk_limits: RiskLimits;
};

// --- Market Data ---

export type MarketCandle = {
  symbol: string;
  interval: string;
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trade_count: number;
};

export type CandleSeriesResponse = {
  symbol: string;
  interval: string;
  source: string;
  candles: MarketCandle[];
};

export type MarketSymbol = {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  status: string;
  spot_trading_allowed: boolean;
};

export type MarketTicker = {
  symbol: string;
  price_change: number;
  price_change_percent: number;
  weighted_average_price: number;
  last_price: number;
  last_quantity: number;
  open_price: number;
  high_price: number;
  low_price: number;
  volume: number;
  quote_volume: number;
  trade_count: number;
};

export type MarketOverview = {
  source: string;
  quote_asset: string | null;
  total: number;
  tickers: MarketTicker[];
};

// --- Trading ---

export type TradingSignal = {
  symbol: string;
  side: "BUY" | "SELL" | "HOLD";
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  strategy: string;
  market_regime: string;
  timestamp: string;
  explanation: string;
};

export type RiskDecision = {
  approved: boolean;
  reason: string;
  position_quantity: number;
  notional_value: number;
};

export type PaperPosition = {
  id: string;
  symbol: string;
  quantity: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
  strategy: string;
};

export type PaperTrade = {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  opened_at: string;
  closed_at: string;
  exit_reason: string;
  strategy: string;
};

export type PaperPortfolio = {
  cash: number;
  equity: number;
  peak_equity: number;
  current_exposure: number;
  open_positions: PaperPosition[];
  closed_trades: PaperTrade[];
  daily_pnl: number;
  consecutive_losses: number;
};

export type AutomationState = {
  enabled: boolean;
  running: boolean;
  symbol: string;
  interval: string;
  last_cycle_at: string | null;
  last_action: string;
  last_reason: string;
};

export type TradingState = {
  automation: AutomationState;
  portfolio: PaperPortfolio;
};

export type TradingCycleResult = {
  action: string;
  reason: string;
  signal: TradingSignal | null;
  risk_decision: RiskDecision | null;
  portfolio: PaperPortfolio;
};

export type BacktestSummary = {
  symbol: string;
  interval: string;
  candles: number;
  signals: number;
  wins: number;
  losses: number;
  net_pnl: number;
  ending_equity: number;
};

// ---------------------------------------------------------------------------
// HTTP client
// ---------------------------------------------------------------------------

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    throw new Error(`API isteği başarısız oldu (${response.status})`);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// System endpoints
// ---------------------------------------------------------------------------

export function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/system/status");
}

export function enableEmergencyStop(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/system/emergency-stop", { method: "POST" });
}

export function resumePaperMode(): Promise<SystemStatus> {
  return request<SystemStatus>("/api/system/resume", { method: "POST" });
}

export type UpdateRiskLimitsRequest = Partial<RiskLimits>;

export function updateRiskLimits(limits: UpdateRiskLimitsRequest): Promise<SystemStatus> {
  return request<SystemStatus>("/api/system/risk-limits", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(limits)
  });
}

// ---------------------------------------------------------------------------
// Market data endpoints
// ---------------------------------------------------------------------------

export function getMarketCandles(symbol: string, interval: string, limit = 200): Promise<CandleSeriesResponse> {
  const params = new URLSearchParams({
    symbol,
    interval,
    limit: String(limit)
  });

  return request<CandleSeriesResponse>(`/api/market-data/candles?${params.toString()}`);
}

export function getMarketSymbols(quoteAsset?: string): Promise<MarketSymbol[]> {
  const params = new URLSearchParams();
  if (quoteAsset) {
    params.set("quote_asset", quoteAsset);
  }

  return request<MarketSymbol[]>(`/api/market-data/symbols${params.size ? `?${params.toString()}` : ""}`);
}

export function getMarketTickers(quoteAsset?: string): Promise<MarketOverview> {
  const params = new URLSearchParams();
  if (quoteAsset) {
    params.set("quote_asset", quoteAsset);
  }

  return request<MarketOverview>(`/api/market-data/tickers${params.size ? `?${params.toString()}` : ""}`);
}

// ---------------------------------------------------------------------------
// Trading endpoints
// ---------------------------------------------------------------------------

export function getTradingState(): Promise<TradingState> {
  return request<TradingState>("/api/trading/state");
}

export function runTradingStep(symbol: string, interval: string): Promise<TradingCycleResult> {
  const params = new URLSearchParams({ symbol, interval });
  return request<TradingCycleResult>(`/api/trading/step?${params.toString()}`, { method: "POST" });
}

export function startTradingAutomation(symbol: string, interval: string): Promise<AutomationState> {
  const params = new URLSearchParams({ symbol, interval });
  return request<AutomationState>(`/api/trading/automation/start?${params.toString()}`, { method: "POST" });
}

export function stopTradingAutomation(): Promise<AutomationState> {
  return request<AutomationState>("/api/trading/automation/stop", { method: "POST" });
}

export function resetPaperPortfolio(): Promise<PaperPortfolio> {
  return request<PaperPortfolio>("/api/trading/reset", { method: "POST" });
}

export function runBacktest(symbol: string, interval: string, limit = 300): Promise<BacktestSummary> {
  const params = new URLSearchParams({ symbol, interval, limit: String(limit) });
  return request<BacktestSummary>(`/api/trading/backtest?${params.toString()}`);
}
