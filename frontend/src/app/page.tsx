"use client";

import { useCallback, useEffect, useState, type ComponentType, type ReactNode } from "react";
import {
  Activity,
  AlertOctagon,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  CandlestickChart,
  CheckCircle2,
  Cpu,
  Database,
  Gauge,
  LineChart,
  ListChecks,
  LockKeyhole,
  PanelLeft,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ScrollText,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Wallet,
  Wifi,
  WifiOff,
  X
} from "lucide-react";

import { EmptyState, LoadingState } from "@/components/state-blocks";
import { TradingChart } from "@/components/trading-chart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  enableEmergencyStop,
  getActivationValidation,
  getMarketCandles,
  getMarketSymbols,
  getMarketTickers,
  getSystemStatus,
  getTradingState,
  resetPaperPortfolio,
  resumePaperMode,
  updateRiskLimits,
  runBacktest,
  runTradingStep,
  startTradingAutomation,
  stopTradingAutomation,
  type ActivationValidationSummary,
  type AutomationState,
  type BacktestSummary,
  type MarketCandle,
  type MarketSymbol,
  type MarketTicker,
  type PaperPortfolio,
  type RiskDecision,
  type RiskLimits,
  type SystemStatus,
  type TradingSignal,
  getToken,
  clearToken,
  getCurrentUser,
  type UserResponse
} from "@/lib/api";
import { useRouter } from "next/navigation";
import { ChangePasswordForm, UserManagement } from "@/components/user-management";

type NavigationId =
  | "dashboard"
  | "markets"
  | "ai-trader"
  | "strategies"
  | "backtest"
  | "paper-trading"
  | "portfolio"
  | "orders"
  | "risk"
  | "logs"
  | "settings";

type NavigationItem = {
  id: NavigationId;
  label: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
};

type AuditEvent = {
  id: string;
  time: string;
  source: string;
  message: string;
  tone: "paper" | "neutral" | "warning" | "danger";
};

const navigation: NavigationItem[] = [
  { id: "dashboard", label: "Kontrol Paneli", icon: Gauge },
  { id: "markets", label: "Piyasalar", icon: CandlestickChart },
  { id: "ai-trader", label: "Yapay Zeka İşlemci", icon: Bot },
  { id: "strategies", label: "Stratejiler", icon: SlidersHorizontal },
  { id: "backtest", label: "Geri Test", icon: BarChart3 },
  { id: "paper-trading", label: "Kağıt İşlem", icon: Activity },
  { id: "portfolio", label: "Portföy", icon: BriefcaseBusiness },
  { id: "orders", label: "Emirler", icon: ListChecks },
  { id: "risk", label: "Risk Merkezi", icon: ShieldCheck },
  { id: "logs", label: "Kayıtlar", icon: ScrollText },
  { id: "settings", label: "Ayarlar", icon: Settings }
];

const fallbackMarketSymbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"];
const marketIntervals = ["1m", "5m", "15m", "1h", "4h", "1d"];
const quoteAssets = ["USDT", "FDUSD", "USDC", "BTC", "ETH", "BNB", "TRY", "EUR"];
const exchangeLabels: Record<string, string> = {
  all: "Binance + OKX",
  binance: "Binance",
  okx: "OKX"
};

const orderPolicies = [
  ["Long spot emir", "Paper mode dışında engelli"],
  ["Short / futures", "Kalıcı olarak engelli"],
  ["Stop-loss olmayan emir", "Reddedilir"],
  ["Risk limitini aşan emir", "Reddedilir"],
  ["AI tarafından doğrudan emir", "Reddedilir"]
] as const;

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    }
  }, [router]);

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  const [activeSection, setActiveSection] = useState<NavigationId>("dashboard");
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [systemLoading, setSystemLoading] = useState(true);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [updatingControl, setUpdatingControl] = useState(false);
  const [marketSymbol, setMarketSymbol] = useState("BTCUSDT");
  const [marketExchange, setMarketExchange] = useState("all");
  const [marketInterval, setMarketInterval] = useState("1h");
  const [quoteAsset, setQuoteAsset] = useState("USDT");
  const [marketSearch, setMarketSearch] = useState("");
  const [marketCandles, setMarketCandles] = useState<MarketCandle[]>([]);
  const [marketSymbols, setMarketSymbols] = useState<MarketSymbol[]>([]);
  const [marketTickers, setMarketTickers] = useState<MarketTicker[]>([]);
  const [marketLoading, setMarketLoading] = useState(true);
  const [marketListLoading, setMarketListLoading] = useState(true);
  const [marketError, setMarketError] = useState<string | null>(null);
  const [marketListError, setMarketListError] = useState<string | null>(null);
  const [marketDataSource, setMarketDataSource] = useState<string | null>(null);
  const [marketListSource, setMarketListSource] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<PaperPortfolio | null>(null);
  const [automation, setAutomation] = useState<AutomationState | null>(null);
  const [activationValidation, setActivationValidation] = useState<ActivationValidationSummary | null>(null);
  const [activationValidationLoading, setActivationValidationLoading] = useState(true);
  const [activationValidationError, setActivationValidationError] = useState<string | null>(null);
  const [tradingLoading, setTradingLoading] = useState(true);
  const [lastTradingAction, setLastTradingAction] = useState<string>("IDLE");
  const [lastTradingReason, setLastTradingReason] = useState<string>("Bot başlatılmadı.");
  const [lastSignalSide, setLastSignalSide] = useState<string>("-");
  const [lastSignal, setLastSignal] = useState<TradingSignal | null>(null);
  const [lastRiskDecision, setLastRiskDecision] = useState<RiskDecision | null>(null);
  const [backtestSummary, setBacktestSummary] = useState<BacktestSummary | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestSymbol, setBacktestSymbol] = useState("BTC/USDT");
  const [backtestWindow, setBacktestWindow] = useState("90 gün");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([
    {
      id: "boot",
      time: new Date().toISOString(),
      source: "Frontend",
      message: "Terminal oturumu açıldı.",
      tone: "neutral"
    }
  ]);

  const appendAuditEvent = useCallback((event: Omit<AuditEvent, "id" | "time">) => {
    setAuditEvents((current) => [
      {
        id: `${Date.now()}-${event.source}`,
        time: new Date().toISOString(),
        ...event
      },
      ...current
    ].slice(0, 16));
  }, []);

  const loadUser = useCallback(async () => {
    if (getToken()) {
      try {
        const user = await getCurrentUser();
        setCurrentUser(user);
      } catch (e) {
        console.error("Failed to fetch user", e);
      }
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const loadStatus = useCallback(async () => {
    try {
      const nextStatus = await getSystemStatus();
      setStatus((current) => {
        if (current && current.trading_halted !== nextStatus.trading_halted) {
          appendAuditEvent({
            source: "Kontrol",
            message: nextStatus.trading_halted
              ? "Kill switch etkinleşti, paper işlem motoru durduruldu."
              : "Paper mode güvenli bekleme durumuna alındı.",
            tone: nextStatus.trading_halted ? "danger" : "paper"
          });
        }
        return nextStatus;
      });
      setSystemError(null);
    } catch (requestError) {
      setSystemError(requestError instanceof Error ? requestError.message : "API bağlantısı kurulamadı.");
    } finally {
      setSystemLoading(false);
    }
  }, [appendAuditEvent]);

  const loadMarketData = useCallback(async () => {
    setMarketLoading(true);
    setMarketError(null);
    try {
      const series = await getMarketCandles(marketSymbol, marketInterval, 200, marketExchange);
      setMarketCandles(series.candles);
      setMarketDataSource(series.source);
      appendAuditEvent({
        source: "Market Data",
        message: `${series.symbol} ${series.interval} mum verisi yüklendi (${formatMarketSource(series.source)}).`,
        tone: "paper"
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Piyasa verisi alınamadı.";
      setMarketCandles([]);
      setMarketDataSource(null);
      setMarketError(message);
      appendAuditEvent({
        source: "Market Data",
        message,
        tone: "warning"
      });
    } finally {
      setMarketLoading(false);
    }
  }, [appendAuditEvent, marketExchange, marketInterval, marketSymbol]);

  const loadMarketListings = useCallback(async () => {
    setMarketListLoading(true);
    setMarketListError(null);
    try {
      const [symbols, overview] = await Promise.all([
        getMarketSymbols(quoteAsset),
        getMarketTickers(quoteAsset)
      ]);
      setMarketSymbols(symbols);
      setMarketTickers(overview.tickers);
      setMarketListSource(overview.source);
      appendAuditEvent({
        source: "Market List",
        message: `${overview.total} ${quoteAsset} marketi yüklendi (${formatMarketSource(overview.source)}).`,
        tone: "paper"
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Market listesi alınamadı.";
      setMarketListError(message);
      setMarketListSource(null);
      appendAuditEvent({
        source: "Market List",
        message,
        tone: "warning"
      });
    } finally {
      setMarketListLoading(false);
    }
  }, [appendAuditEvent, quoteAsset]);

  const loadTradingState = useCallback(async () => {
    setTradingLoading(true);
    try {
      const state = await getTradingState();
      setPortfolio(state.portfolio);
      setAutomation(state.automation);
      setLastTradingAction(state.automation.last_action);
      setLastTradingReason(state.automation.last_reason);
      setLastSignal(state.automation.last_signal);
      setLastRiskDecision(state.automation.last_risk_decision);
    } catch (requestError) {
      appendAuditEvent({
        source: "Trading",
        message: requestError instanceof Error ? requestError.message : "Trading state alınamadı.",
        tone: "warning"
      });
    } finally {
      setTradingLoading(false);
    }
  }, [appendAuditEvent]);

  const loadActivationValidation = useCallback(async () => {
    setActivationValidationLoading(true);
    try {
      const validation = await getActivationValidation(marketSymbol, marketInterval, marketExchange);
      setActivationValidation(validation);
      setActivationValidationError(null);
      appendAuditEvent({
        source: "Validation",
        message: validation.ready
          ? "Paper bot aktivasyon doğrulaması tamamlandı."
          : "Paper bot aktivasyon doğrulaması bekliyor.",
        tone: validation.ready ? "paper" : "warning"
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Aktivasyon doğrulaması alınamadı.";
      setActivationValidation(null);
      setActivationValidationError(message);
      appendAuditEvent({
        source: "Validation",
        message,
        tone: "warning"
      });
    } finally {
      setActivationValidationLoading(false);
    }
  }, [appendAuditEvent, marketExchange, marketInterval, marketSymbol]);

  useEffect(() => {
    const initialRequestId = window.setTimeout(() => void loadStatus(), 0);
    const pollingId = window.setInterval(() => void loadStatus(), 5000);
    return () => {
      window.clearTimeout(initialRequestId);
      window.clearInterval(pollingId);
    };
  }, [loadStatus]);

  useEffect(() => {
    const requestId = window.setTimeout(() => void loadMarketData(), 0);
    return () => window.clearTimeout(requestId);
  }, [loadMarketData]);

  useEffect(() => {
    const requestId = window.setTimeout(() => void loadMarketListings(), 0);
    return () => window.clearTimeout(requestId);
  }, [loadMarketListings]);

  useEffect(() => {
    const requestId = window.setTimeout(() => void loadTradingState(), 0);
    const pollingId = window.setInterval(() => void loadTradingState(), 5000);
    return () => {
      window.clearTimeout(requestId);
      window.clearInterval(pollingId);
    };
  }, [loadTradingState]);

  useEffect(() => {
    const requestId = window.setTimeout(() => void loadActivationValidation(), 0);
    return () => window.clearTimeout(requestId);
  }, [loadActivationValidation]);

  const selectSection = (id: NavigationId) => {
    setActiveSection(id);
    setMobileNavigationOpen(false);
    appendAuditEvent({
      source: "Menü",
      message: `${navigation.find((item) => item.id === id)?.label ?? "Bölüm"} ekranı açıldı.`,
      tone: "neutral"
    });
  };

  const refreshAll = async () => {
    setSystemLoading(true);
    await Promise.all([loadStatus(), loadMarketData(), loadMarketListings(), loadTradingState(), loadActivationValidation()]);
    appendAuditEvent({
      source: "API",
      message: "Sistem ve piyasa verisi elle yenilendi.",
      tone: "neutral"
    });
  };

  const toggleTradingControl = async () => {
    if (!status) {
      await loadStatus();
      return;
    }

    setUpdatingControl(true);
    setSystemError(null);
    try {
      const nextStatus = status.trading_halted
        ? await resumePaperMode()
        : await enableEmergencyStop();
      setStatus(nextStatus);
      appendAuditEvent({
        source: "Kontrol",
        message: nextStatus.trading_halted
          ? "Acil durdurma komutu backend tarafından onaylandı."
          : "Paper mode yeniden güvenli beklemeye döndü.",
        tone: nextStatus.trading_halted ? "danger" : "paper"
      });
    } catch (requestError) {
      setSystemError(requestError instanceof Error ? requestError.message : "Sistem durumu değiştirilemedi.");
    } finally {
      setUpdatingControl(false);
    }
  };

  const runOneTradingCycle = async () => {
    setTradingLoading(true);
    try {
      const result = await runTradingStep(marketSymbol, marketInterval, marketExchange);
      setPortfolio(result.portfolio);
      setLastTradingAction(result.action);
      setLastTradingReason(result.reason);
      setLastSignalSide(result.signal?.side ?? "-");
      setLastSignal(result.signal);
      setLastRiskDecision(result.risk_decision);
      appendAuditEvent({
        source: "Trading",
        message: `${result.action}: ${result.reason}`,
        tone: result.action.includes("REJECTED") ? "warning" : "paper"
      });
      await loadMarketData();
    } catch (requestError) {
      appendAuditEvent({
        source: "Trading",
        message: requestError instanceof Error ? requestError.message : "Trading döngüsü çalışmadı.",
        tone: "warning"
      });
    } finally {
      setTradingLoading(false);
    }
  };

  const toggleAutomation = async () => {
    setTradingLoading(true);
    try {
      const nextAutomation = automation?.running
        ? await stopTradingAutomation()
        : await startTradingAutomation(marketSymbol, marketInterval, marketExchange);
      setAutomation(nextAutomation);
      setLastTradingAction(nextAutomation.last_action);
      setLastTradingReason(nextAutomation.last_reason);
      appendAuditEvent({
        source: "Trading",
        message: nextAutomation.last_reason,
        tone: nextAutomation.running ? "paper" : "neutral"
      });
    } catch (requestError) {
      appendAuditEvent({
        source: "Trading",
        message: requestError instanceof Error ? requestError.message : "Otomasyon durumu değiştirilemedi.",
        tone: "warning"
      });
    } finally {
      setTradingLoading(false);
    }
  };

  const resetPortfolio = async () => {
    setTradingLoading(true);
    try {
      const nextPortfolio = await resetPaperPortfolio();
      setPortfolio(nextPortfolio);
      setLastTradingAction("RESET");
      setLastTradingReason("Paper portföy sıfırlandı.");
      setLastSignal(null);
      setLastRiskDecision(null);
      appendAuditEvent({
        source: "Trading",
        message: "Paper portföy sıfırlandı.",
        tone: "neutral"
      });
    } finally {
      setTradingLoading(false);
    }
  };

  const runBacktestNow = async () => {
    setBacktestLoading(true);
    try {
      const summary = await runBacktest(backtestSymbol.replace("/", ""), marketInterval, 300, marketExchange);
      setBacktestSummary(summary);
      appendAuditEvent({
        source: "Backtest",
        message: `${summary.symbol} backtest tamamlandı. Net PnL: ${formatMoney(summary.net_pnl)}`,
        tone: summary.net_pnl >= 0 ? "paper" : "warning"
      });
    } finally {
      setBacktestLoading(false);
    }
  };

  const activeItem = navigation.find((item) => item.id === activeSection) ?? navigation[0];
  const marketSourceLabel = marketDataSource?.startsWith("offline_paper")
    ? "PAPER DATA"
    : "MARKET DATA";
  const selectMarket = (symbol: string, exchange = marketExchange) => {
    setMarketSymbol(symbol);
    setMarketExchange(exchange);
  };

  return (
    <main className="min-h-screen text-textPrimary">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 shrink-0 border-r border-line bg-[#0c1118]/95 px-4 py-5 lg:block">
          <Brand />
          <Navigation activeSection={activeSection} onSelect={selectSection} />
        </aside>

        {mobileNavigationOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/65"
              aria-label="Menüyü kapat"
              onClick={() => setMobileNavigationOpen(false)}
            />
            <aside className="relative h-full w-[min(18rem,88vw)] border-r border-line bg-[#0c1118] px-4 py-5 shadow-terminal">
              <div className="flex items-center justify-between gap-3">
                <Brand />
                <Button variant="ghost" className="h-10 w-10 px-0" aria-label="Menüyü kapat" onClick={() => setMobileNavigationOpen(false)}>
                  <X className="h-5 w-5" aria-hidden="true" />
                </Button>
              </div>
              <Navigation activeSection={activeSection} onSelect={selectSection} />
            </aside>
          </div>
        ) : null}

        <section className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b border-line bg-[#0b0f14]/95 backdrop-blur">
            <div className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-6">
              <div className="flex min-w-0 items-center gap-3">
                <Button
                  variant="ghost"
                  className="h-10 w-10 px-0 lg:hidden"
                  aria-label="Menüyü aç"
                  onClick={() => setMobileNavigationOpen(true)}
                >
                  <PanelLeft className="h-5 w-5" aria-hidden="true" />
                </Button>
                <div className="min-w-0">
                  <h1 className="truncate text-lg font-black tracking-normal md:text-2xl">NEXUS AI TRADER</h1>
                  <p className="truncate text-xs text-textMuted md:text-sm">{activeItem.label}</p>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-end gap-2">
                {currentUser && (
                  <Badge tone="neutral">
                    {currentUser.username} {currentUser.is_admin ? "(Admin)" : ""}
                  </Badge>
                )}
                <Button variant="ghost" onClick={handleLogout} className="mr-2 text-rose-100 hover:text-rose-200">
                  Çıkış
                </Button>
                <ConnectionBadge status={status} error={systemError} loading={systemLoading} />
                <Badge tone={marketError ? "warning" : "paper"}>{marketError ? "PİYASA VERİSİ YOK" : marketSourceLabel}</Badge>
                <Button variant="secondary" disabled={systemLoading || marketLoading} onClick={() => void refreshAll()} aria-label="Sistemi yenile">
                  <RefreshCw className={`h-4 w-4 ${systemLoading || marketLoading ? "animate-spin" : ""}`} aria-hidden="true" />
                  Yenile
                </Button>
              </div>
            </div>
          </header>

          <div className="px-4 py-5 lg:px-6">
            {systemError ? (
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger/50 bg-danger/10 px-4 py-3">
                <div className="flex items-center gap-3 text-sm text-rose-100">
                  <WifiOff className="h-5 w-5 shrink-0" aria-hidden="true" />
                  <span>{systemError}</span>
                </div>
                <Button variant="secondary" disabled={systemLoading} onClick={() => void refreshAll()}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Yeniden Dene
                </Button>
              </div>
            ) : null}

            {systemLoading && !status ? (
              <LoadingState title="Sistem durumu yükleniyor" detail="Güvenli paper-mode API bağlantısı kuruluyor." className="min-h-[60vh]" />
            ) : (
              <TerminalSection
                activeSection={activeSection}
                currentUser={currentUser}
                status={status}
                updatingControl={updatingControl}
                auditEvents={auditEvents}
                marketSymbol={marketSymbol}
                marketExchange={marketExchange}
                marketInterval={marketInterval}
                marketCandles={marketCandles}
                marketSymbols={marketSymbols}
                marketTickers={marketTickers}
                marketLoading={marketLoading}
                marketListLoading={marketListLoading}
                marketError={marketError}
                marketListError={marketListError}
                marketListSource={marketListSource}
                quoteAsset={quoteAsset}
                marketSearch={marketSearch}
                portfolio={portfolio}
                automation={automation}
                activationValidation={activationValidation}
                activationValidationLoading={activationValidationLoading}
                activationValidationError={activationValidationError}
                tradingLoading={tradingLoading}
                lastTradingAction={lastTradingAction}
                lastTradingReason={lastTradingReason}
                lastSignalSide={lastSignalSide}
                lastSignal={lastSignal}
                lastRiskDecision={lastRiskDecision}
                backtestSummary={backtestSummary}
                backtestLoading={backtestLoading}
                backtestSymbol={backtestSymbol}
                backtestWindow={backtestWindow}
                onRefreshAll={refreshAll}
                onRefreshMarket={loadMarketData}
                onRefreshMarketList={loadMarketListings}
                onRunTradingCycle={runOneTradingCycle}
                onToggleAutomation={toggleAutomation}
                onResetPortfolio={resetPortfolio}
                onRunBacktest={runBacktestNow}
                onToggleTradingControl={toggleTradingControl}
                onMarketSymbolChange={selectMarket}
                onMarketIntervalChange={setMarketInterval}
                onQuoteAssetChange={setQuoteAsset}
                onMarketSearchChange={setMarketSearch}
                onBacktestSymbolChange={setBacktestSymbol}
                onBacktestWindowChange={setBacktestWindow}
                onSystemStatusChange={setStatus}
              />
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function TerminalSection(props: {
  activeSection: NavigationId;
  currentUser: UserResponse | null;
  status: SystemStatus | null;
  updatingControl: boolean;
  auditEvents: AuditEvent[];
  marketSymbol: string;
  marketExchange: string;
  marketInterval: string;
  marketCandles: MarketCandle[];
  marketSymbols: MarketSymbol[];
  marketTickers: MarketTicker[];
  marketLoading: boolean;
  marketListLoading: boolean;
  marketError: string | null;
  marketListError: string | null;
  marketListSource: string | null;
  quoteAsset: string;
  marketSearch: string;
  portfolio: PaperPortfolio | null;
  automation: AutomationState | null;
  activationValidation: ActivationValidationSummary | null;
  activationValidationLoading: boolean;
  activationValidationError: string | null;
  tradingLoading: boolean;
  lastTradingAction: string;
  lastTradingReason: string;
  lastSignalSide: string;
  lastSignal: TradingSignal | null;
  lastRiskDecision: RiskDecision | null;
  backtestSummary: BacktestSummary | null;
  backtestLoading: boolean;
  backtestSymbol: string;
  backtestWindow: string;
  onRefreshAll: () => Promise<void>;
  onRefreshMarket: () => Promise<void>;
  onRefreshMarketList: () => Promise<void>;
  onRunTradingCycle: () => Promise<void>;
  onToggleAutomation: () => Promise<void>;
  onResetPortfolio: () => Promise<void>;
  onRunBacktest: () => Promise<void>;
  onToggleTradingControl: () => Promise<void>;
  onMarketSymbolChange: (symbol: string, exchange?: string) => void;
  onMarketIntervalChange: (value: string) => void;
  onQuoteAssetChange: (value: string) => void;
  onMarketSearchChange: (value: string) => void;
  onBacktestSymbolChange: (value: string) => void;
  onBacktestWindowChange: (value: string) => void;
  onSystemStatusChange: (value: SystemStatus) => void;
}) {
  switch (props.activeSection) {
    case "markets":
      return <MarketsSection {...props} />;
    case "ai-trader":
      return <AiTraderSection status={props.status} marketCandles={props.marketCandles} />;
    case "strategies":
      return (
        <StrategiesSection
          status={props.status}
          marketCandles={props.marketCandles}
          activationValidation={props.activationValidation}
          activationValidationLoading={props.activationValidationLoading}
          activationValidationError={props.activationValidationError}
        />
      );
    case "backtest":
      return <BacktestSection {...props} />;
    case "paper-trading":
      return <PaperTradingSection {...props} />;
    case "portfolio":
      return <PortfolioSection status={props.status} portfolio={props.portfolio} />;
    case "orders":
      return <OrdersSection status={props.status} portfolio={props.portfolio} />;
    case "risk":
      return <RiskSection status={props.status} onSystemStatusChange={props.onSystemStatusChange} />;
    case "logs":
      return <LogsSection events={props.auditEvents} onRefresh={props.onRefreshAll} loading={props.marketLoading} />;
    case "settings":
      return <SettingsSection {...props} />;
    case "dashboard":
    default:
      return <Dashboard {...props} />;
  }
}

function Brand() {
  return (
    <div className="flex h-14 items-center gap-3 px-2">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-accent/35 bg-accent/12">
        <LineChart className="h-5 w-5 text-accent" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="truncate text-sm font-black tracking-normal">NEXUS AI TRADER</p>
        <p className="truncate text-xs text-textMuted">Kağıt işlem terminali</p>
      </div>
    </div>
  );
}

function Navigation({ activeSection, onSelect }: { activeSection: NavigationId; onSelect: (id: NavigationId) => void }) {
  return (
    <nav className="mt-6 space-y-1" aria-label="Ana menü">
      {navigation.map((item) => {
        const active = item.id === activeSection;
        return (
          <button
            key={item.id}
            type="button"
            aria-current={active ? "page" : undefined}
            onClick={() => onSelect(item.id)}
            className={`flex h-11 w-full items-center gap-3 rounded-md px-3 text-left text-sm font-semibold transition ${
              active
                ? "border border-accent/35 bg-accent/12 text-teal-100"
                : "border border-transparent text-textMuted hover:bg-panelMuted hover:text-textPrimary"
            }`}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden={true} />
            <span className="truncate">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

function Dashboard({
  status,
  marketSymbol,
  marketExchange,
  marketInterval,
  marketCandles,
  marketSymbols,
  marketLoading,
  marketError,
  portfolio,
  automation,
  activationValidation,
  activationValidationLoading,
  activationValidationError,
  lastTradingAction,
  lastSignalSide,
  onRefreshMarket,
  onMarketSymbolChange,
  onMarketIntervalChange,
  onSystemStatusChange
}: {
  status: SystemStatus | null;
  marketSymbol: string;
  marketExchange: string;
  marketInterval: string;
  marketCandles: MarketCandle[];
  marketSymbols: MarketSymbol[];
  marketLoading: boolean;
  marketError: string | null;
  portfolio: PaperPortfolio | null;
  automation: AutomationState | null;
  activationValidation: ActivationValidationSummary | null;
  activationValidationLoading: boolean;
  activationValidationError: string | null;
  lastTradingAction: string;
  lastSignalSide: string;
  onRefreshMarket: () => Promise<void>;
  onMarketSymbolChange: (symbol: string, exchange?: string) => void;
  onMarketIntervalChange: (value: string) => void;
  onSystemStatusChange: (value: SystemStatus) => void;
}) {
  const latest = marketCandles.at(-1);
  const previous = marketCandles.at(-2);
  const changePct = latest && previous ? (latest.close - previous.close) / previous.close : undefined;

  return (
    <div className="space-y-5">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric label="Sembol" value={marketSymbol} helper={`${formatExchange(marketExchange)} / ${marketInterval}`} tone="paper" />
        <Metric label="Son Fiyat" value={latest ? formatPrice(latest.close) : "-"} helper="Public market data" tone="paper" />
        <Metric label="Son Mum" value={formatSignedPercent(changePct)} helper="Önceki muma göre" tone={changePct && changePct < 0 ? "danger" : "paper"} />
        <Metric label="Paper Equity" value={portfolio ? formatMoney(portfolio.equity) : "-"} helper="Simülasyon bakiyesi" tone="paper" />
        <Metric label="Açık Pozisyon" value={portfolio ? String(portfolio.open_positions.length) : "0"} helper={automation?.running ? "Bot çalışıyor" : "Bot kapalı"} tone={automation?.running ? "paper" : "neutral"} />
        <Metric label="Son Sinyal" value={lastSignalSide} helper={lastTradingAction} tone={lastSignalSide === "BUY" ? "paper" : "neutral"} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <MarketToolbar
            symbol={marketSymbol}
            interval={marketInterval}
            symbols={marketSymbols}
            loading={marketLoading}
            onSymbolChange={onMarketSymbolChange}
            onIntervalChange={onMarketIntervalChange}
            onRefresh={onRefreshMarket}
          />
          <TradingChart candles={marketCandles} loading={marketLoading} error={marketError} />
        </div>
        <div className="grid gap-5">
          <BotStatus status={status} automation={automation} />
          <RiskPanel status={status} onSystemStatusChange={onSystemStatusChange} />
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <StrategiesTable
          validation={activationValidation}
          loading={activationValidationLoading}
          error={activationValidationError}
        />
        <PlatformStatus status={status} marketCandles={marketCandles} marketError={marketError} />
      </section>
    </div>
  );
}

function MarketsSection({
  marketSymbol,
  marketExchange,
  marketInterval,
  marketCandles,
  marketSymbols,
  marketTickers,
  marketLoading,
  marketListLoading,
  marketError,
  marketListError,
  marketListSource,
  quoteAsset,
  marketSearch,
  onRefreshMarket,
  onRefreshMarketList,
  onMarketSymbolChange,
  onMarketIntervalChange,
  onQuoteAssetChange,
  onMarketSearchChange
}: {
  marketSymbol: string;
  marketExchange: string;
  marketInterval: string;
  marketCandles: MarketCandle[];
  marketSymbols: MarketSymbol[];
  marketTickers: MarketTicker[];
  marketLoading: boolean;
  marketListLoading: boolean;
  marketError: string | null;
  marketListError: string | null;
  marketListSource: string | null;
  quoteAsset: string;
  marketSearch: string;
  onRefreshMarket: () => Promise<void>;
  onRefreshMarketList: () => Promise<void>;
  onMarketSymbolChange: (symbol: string, exchange?: string) => void;
  onMarketIntervalChange: (value: string) => void;
  onQuoteAssetChange: (value: string) => void;
  onMarketSearchChange: (value: string) => void;
}) {
  const latest = marketCandles.at(-1);

  return (
    <div className="space-y-5">
      <SectionHeader icon={CandlestickChart} title="Piyasalar" description="Binance ve OKX spot marketleri" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-3">
          <MarketToolbar
            symbol={marketSymbol}
            interval={marketInterval}
            symbols={marketSymbols}
            loading={marketLoading}
            onSymbolChange={onMarketSymbolChange}
            onIntervalChange={onMarketIntervalChange}
            onRefresh={onRefreshMarket}
          />
          <TradingChart candles={marketCandles} loading={marketLoading} error={marketError} />
        </div>
        <div className="grid gap-5">
          <InfoCard icon={Database} title="Public Candles" badge={marketError ? "Hata" : "Bağlı"} badgeTone={marketError ? "warning" : "paper"}>
            <div className="grid gap-3 text-sm">
              <StatusLine label="Borsa" value={formatExchange(marketExchange)} />
              <StatusLine label="Sembol" value={marketSymbol} />
              <StatusLine label="Aralık" value={marketInterval} />
              <StatusLine label="Mum sayısı" value={String(marketCandles.length)} />
              <StatusLine label="Son fiyat" value={latest ? formatPrice(latest.close) : "-"} />
            </div>
          </InfoCard>
          <InfoCard
            icon={Database}
            title="Market Listesi"
            badge={marketListError ? "Hata" : marketListSource?.startsWith("offline_paper") ? "Paper" : "Aktif"}
            badgeTone={marketListError ? "warning" : "paper"}
          >
            <div className="grid gap-3 text-sm">
              <StatusLine label="Kaynak" value={marketListSource ? formatMarketSource(marketListSource) : "-"} />
              <StatusLine label="Quote filtresi" value={quoteAsset} />
              <StatusLine label="Spot sembol" value={String(marketSymbols.length)} />
              <StatusLine label="Ticker" value={String(marketTickers.length)} />
              <StatusLine label="Yetki" value="Read-only" />
            </div>
          </InfoCard>
        </div>
      </div>
      <MarketListTable
        symbols={marketSymbols}
        tickers={marketTickers}
        loading={marketListLoading}
        error={marketListError}
        quoteAsset={quoteAsset}
        search={marketSearch}
        onQuoteAssetChange={onQuoteAssetChange}
        onSearchChange={onMarketSearchChange}
        onRefresh={onRefreshMarketList}
        onSelectSymbol={onMarketSymbolChange}
      />
      <CandleTable candles={marketCandles} />
    </div>
  );
}

function AiTraderSection({ status, marketCandles }: { status: SystemStatus | null; marketCandles: MarketCandle[] }) {
  const halted = status?.trading_halted ?? true;
  return (
    <div className="space-y-5">
      <SectionHeader icon={Bot} title="Yapay Zeka İşlemci" description="AI açıklama üretir; emir yetkisi deterministik motorlardadır" />
      <div className="grid gap-4 lg:grid-cols-3">
        <InfoCard icon={LockKeyhole} title="Emir Yetkisi" badge="Yok" badgeTone="danger">
          <p className="text-sm text-textMuted">AI hiçbir zaman doğrudan emir gönderemez veya risk limitini değiştiremez.</p>
        </InfoCard>
        <InfoCard icon={Cpu} title="Market Girdisi" badge={marketCandles.length ? "Aktif" : "Bekliyor"} badgeTone={marketCandles.length ? "paper" : "neutral"}>
          <p className="text-sm text-textMuted">{marketCandles.length ? "Public candle verisi karar akışına hazır." : "Piyasa verisi henüz yüklenmedi."}</p>
        </InfoCard>
        <InfoCard icon={PauseCircle} title="Motor Durumu" badge={halted ? "Durduruldu" : "Beklemede"} badgeTone={halted ? "warning" : "paper"}>
          <p className="text-sm text-textMuted">{halted ? "Kill switch açıkken yeni sinyal işlenmez." : "Paper mode güvenli beklemede."}</p>
        </InfoCard>
      </div>
      <section className="rounded-md border border-line bg-panel p-4">
        <h2 className="text-sm font-black uppercase tracking-normal">Karar Akışı</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <PipelineStep number="1" title="Veri" detail="Public candles" state={marketCandles.length ? "Aktif" : "Bekliyor"} />
          <PipelineStep number="2" title="Rejim" detail="Trend, volatilite, likidite" state="Hazır" />
          <PipelineStep number="3" title="Risk" detail="Pozisyon ve zarar sınırları" state="Aktif" />
          <PipelineStep number="4" title="Validator" detail="Paper emir onayı" state="Aktif" />
        </div>
      </section>
    </div>
  );
}

function StrategiesSection({
  status,
  marketCandles,
  activationValidation,
  activationValidationLoading,
  activationValidationError
}: {
  status: SystemStatus | null;
  marketCandles: MarketCandle[];
  activationValidation: ActivationValidationSummary | null;
  activationValidationLoading: boolean;
  activationValidationError: string | null;
}) {
  const validationReady = Boolean(activationValidation?.ready) && !status?.trading_halted;
  return (
    <div className="space-y-5">
      <SectionHeader icon={SlidersHorizontal} title="Stratejiler" description="Hazır strateji şablonları ve aktivasyon güvenliği" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <StrategiesTable
          validation={activationValidation}
          loading={activationValidationLoading}
          error={activationValidationError}
        />
        <InfoCard
          icon={ShieldCheck}
          title="Aktivasyon Kilidi"
          badge={validationReady ? "Tamam" : status?.trading_halted ? "Kapalı" : "Bekliyor"}
          badgeTone={validationReady ? "paper" : "warning"}
        >
          <div className="grid gap-3 text-sm">
            <StatusLine label="Market data" value={marketCandles.length ? "Aktif" : "Bekliyor"} />
            <StatusLine label="Doğrulama" value={activationValidation?.ready ? "Tamamlandı" : "Bekliyor"} />
            <StatusLine label="Kontrol sayısı" value={activationValidation ? `${activationValidation.rows.filter((row) => row.passed).length}/${activationValidation.rows.length}` : "-"} />
            <StatusLine label="Kill switch" value={status?.trading_halted ? "Etkin" : "Pasif"} />
            <StatusLine label="Canlı emir" value="Kapalı" />
          </div>
        </InfoCard>
      </div>
    </div>
  );
}

function BacktestSection({
  backtestSymbol,
  backtestWindow,
  marketCandles,
  backtestSummary,
  backtestLoading,
  onRunBacktest,
  onBacktestSymbolChange,
  onBacktestWindowChange
}: {
  backtestSymbol: string;
  backtestWindow: string;
  marketCandles: MarketCandle[];
  backtestSummary: BacktestSummary | null;
  backtestLoading: boolean;
  onRunBacktest: () => Promise<void>;
  onBacktestSymbolChange: (value: string) => void;
  onBacktestWindowChange: (value: string) => void;
}) {
  return (
    <div className="space-y-5">
      <SectionHeader icon={BarChart3} title="Geri Test" description="Walk-forward ve out-of-sample doğrulama hazırlığı" />
      <section className="grid gap-5 rounded-md border border-line bg-panel p-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="grid gap-4">
          <LabeledSelect label="Sembol" value={backtestSymbol} onChange={onBacktestSymbolChange} values={["BTC/USDT", "ETH/USDT", "SOL/USDT"]} />
          <LabeledSelect label="Zaman Aralığı" value={backtestWindow} onChange={onBacktestWindowChange} values={["30 gün", "90 gün", "180 gün", "365 gün"]} />
          <LabeledSelect label="Strateji" value="EMA + RSI" onChange={() => undefined} values={["EMA + RSI", "Donchian ATR", "Bollinger MR"]} />
          <Button variant="primary" disabled={backtestLoading} onClick={() => void onRunBacktest()}>
            <PlayCircle className="h-4 w-4" aria-hidden="true" />
            {backtestLoading ? "Çalışıyor" : "Backtest Çalıştır"}
          </Button>
        </div>
        <div className="rounded-md border border-line bg-panelMuted/35 p-4">
          <h2 className="text-sm font-black uppercase tracking-normal">Test Sonucu</h2>
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <StatusLine label="Seçilen sembol" value={backtestSymbol} />
            <StatusLine label="Test penceresi" value={backtestWindow} />
            <StatusLine label="Canlı mum" value={String(marketCandles.length)} />
            <StatusLine label="Backtest mumu" value={backtestSummary ? String(backtestSummary.candles) : "-"} />
            <StatusLine label="Sinyal" value={backtestSummary ? String(backtestSummary.signals) : "-"} />
            <StatusLine label="Kazanç / Kayıp" value={backtestSummary ? `${backtestSummary.wins} / ${backtestSummary.losses}` : "-"} />
            <StatusLine label="Net PnL" value={backtestSummary ? formatMoney(backtestSummary.net_pnl) : "-"} />
            <StatusLine label="Bitiş equity" value={backtestSummary ? formatMoney(backtestSummary.ending_equity) : "-"} />
          </div>
        </div>
      </section>
    </div>
  );
}

function PaperTradingSection({
  status,
  portfolio,
  automation,
  tradingLoading,
  lastTradingAction,
  lastTradingReason,
  lastSignal,
  lastRiskDecision,
  onRunTradingCycle,
  onToggleAutomation,
  onResetPortfolio
}: {
  status: SystemStatus | null;
  portfolio: PaperPortfolio | null;
  automation: AutomationState | null;
  tradingLoading: boolean;
  lastTradingAction: string;
  lastTradingReason: string;
  lastSignal: TradingSignal | null;
  lastRiskDecision: RiskDecision | null;
  onRunTradingCycle: () => Promise<void>;
  onToggleAutomation: () => Promise<void>;
  onResetPortfolio: () => Promise<void>;
}) {
  const halted = status?.trading_halted ?? true;
  const running = automation?.running ?? false;
  return (
    <div className="space-y-5">
      <SectionHeader
        icon={Activity}
        title="Kağıt İşlem"
        description="Gerçek emir göndermeyen güvenli yürütme alanı"
        action={
          <Button variant={running ? "danger" : "primary"} disabled={tradingLoading || halted} onClick={() => void onToggleAutomation()}>
            {running ? <PauseCircle className="h-4 w-4" aria-hidden="true" /> : <PlayCircle className="h-4 w-4" aria-hidden="true" />}
            {running ? "Botu Durdur" : "Botu Başlat"}
          </Button>
        }
      />
      {halted ? (
        <div className="rounded-md border border-amber/50 bg-amber/10 px-4 py-3 text-sm text-textMuted">
          Paper işlemler güvenlik nedeniyle duraklatıldı. Devam etmek için Ayarlar bölümünden paper modu sürdürün.
        </div>
      ) : null}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-md border border-line bg-panel">
          <div className="border-b border-line px-4 py-3">
            <h2 className="text-sm font-black uppercase tracking-normal">Paper Portföy</h2>
          </div>
          <div className="grid gap-3 p-4 text-sm">
            <StatusLine label="Otomasyon" value={running ? "Çalışıyor" : "Kapalı"} />
            <StatusLine label="Son aksiyon" value={lastTradingAction} />
            <StatusLine label="Son neden" value={lastTradingReason} />
            <StatusLine label="Paper cash" value={portfolio ? formatMoney(portfolio.cash) : "-"} />
            <StatusLine label="Paper equity" value={portfolio ? formatMoney(portfolio.equity) : "-"} />
            <StatusLine label="Günlük PnL" value={portfolio ? formatMoney(portfolio.daily_pnl) : "-"} />
          </div>
          <PositionsTable portfolio={portfolio} />
        </section>
        <div className="grid gap-5">
          <BotStatus status={status} automation={automation} />
          <SignalDecisionPanel
            action={lastTradingAction}
            reason={lastTradingReason}
            signal={lastSignal}
            riskDecision={lastRiskDecision}
          />
        </div>
      </div>
      <details className="rounded-md border border-line bg-panel">
        <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-textMuted">Gelişmiş test araçları</summary>
        <div className="flex flex-wrap gap-2 border-t border-line px-4 py-3">
          <Button variant="secondary" disabled={tradingLoading || halted} onClick={() => void onRunTradingCycle()}>
            <RefreshCw className={`h-4 w-4 ${tradingLoading ? "animate-spin" : ""}`} aria-hidden="true" />
            Tek döngü çalıştır
          </Button>
          <Button variant="secondary" disabled={tradingLoading || running} onClick={() => void onResetPortfolio()}>
            Portföyü sıfırla
          </Button>
        </div>
      </details>
    </div>
  );
}

function SignalDecisionPanel({
  action,
  reason,
  signal,
  riskDecision
}: {
  action: string;
  reason: string;
  signal: TradingSignal | null;
  riskDecision: RiskDecision | null;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Son Karar</h2>
          <p className="text-xs text-textMuted">Strateji filtresi ve risk sonucu</p>
        </div>
        <Badge tone={signal?.side === "BUY" ? "paper" : action.includes("REJECTED") ? "warning" : "neutral"}>
          {signal?.side ?? action}
        </Badge>
      </div>

      <div className="mt-4 grid gap-3 text-sm">
        <StatusLine label="Güven" value={signal ? formatPercent(signal.confidence) : "-"} />
        <StatusLine label="Rejim" value={signal?.market_regime ?? "-"} />
        <StatusLine label="Giriş" value={signal ? formatPrice(signal.entry_price) : "-"} />
        <StatusLine label="Stop / TP" value={signal ? `${formatPrice(signal.stop_loss)} / ${formatPrice(signal.take_profit)}` : "-"} />
        <StatusLine label="Risk" value={riskDecision ? riskDecision.reason : "-"} />
      </div>

      <p className="mt-4 rounded-md bg-panelMuted/70 px-3 py-2 text-xs text-textMuted">{reason}</p>

      {signal?.filters.length ? (
        <div className="mt-4 grid gap-2">
          {signal.filters.map((filter) => (
            <div key={filter.key} className="grid gap-2 rounded-md border border-line/70 bg-panelMuted/45 px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-textPrimary">{filter.label}</span>
                <Badge tone={filter.passed ? "paper" : "warning"}>{filter.passed ? "Geçti" : "Kaldı"}</Badge>
              </div>
              <div className="grid gap-1 text-textMuted">
                <span>Mevcut: {filter.actual}</span>
                <span>Gerekli: {filter.required}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function PortfolioSection({ status, portfolio }: { status: SystemStatus | null; portfolio: PaperPortfolio | null }) {
  const limits = status?.risk_limits;
  return (
    <div className="space-y-5">
      <SectionHeader icon={BriefcaseBusiness} title="Portföy" description="Paper portföy defteri ve maruziyet sınırları" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-md border border-line bg-panel">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <h2 className="text-sm font-black uppercase tracking-normal">Pozisyonlar</h2>
            <Badge tone="neutral">{portfolio?.open_positions.length ?? 0} AÇIK</Badge>
          </div>
          <PositionsTable portfolio={portfolio} />
        </section>
        <InfoCard icon={Wallet} title="Sermaye Koruması" badge="Aktif" badgeTone="paper">
          <div className="grid gap-3 text-sm">
            <StatusLine label="Paper cash" value={portfolio ? formatMoney(portfolio.cash) : "-"} />
            <StatusLine label="Paper equity" value={portfolio ? formatMoney(portfolio.equity) : "-"} />
            <StatusLine label="Maks. tek pozisyon" value={formatPercent(limits?.max_single_position_pct)} />
            <StatusLine label="Maks. toplam maruziyet" value={formatPercent(limits?.max_total_exposure_pct)} />
            <StatusLine label="Açık pozisyon sınırı" value={limits ? String(limits.max_open_positions) : "-"} />
          </div>
        </InfoCard>
      </div>
    </div>
  );
}

function OrdersSection({ status, portfolio }: { status: SystemStatus | null; portfolio: PaperPortfolio | null }) {
  return (
    <div className="space-y-5">
      <SectionHeader icon={ListChecks} title="Emirler" description="Order validator kararları ve güvenlik kuralları" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-md border border-line bg-panel">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <h2 className="text-sm font-black uppercase tracking-normal">Emir Kuyruğu</h2>
            <Badge tone={status?.trading_halted ? "warning" : "paper"}>{status?.trading_halted ? "KİLİTLİ" : "PAPER HAZIR"}</Badge>
          </div>
          <TradesTable portfolio={portfolio} />
        </section>
        <section className="rounded-md border border-line bg-panel p-4">
          <h2 className="text-sm font-black uppercase tracking-normal">Reddetme Kuralları</h2>
          <div className="mt-4 grid gap-3">
            {orderPolicies.map(([rule, state]) => (
              <StatusLine key={rule} label={rule} value={state} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function RiskSection({
  status,
  onSystemStatusChange
}: {
  status: SystemStatus | null;
  onSystemStatusChange: (value: SystemStatus) => void;
}) {
  return (
    <div className="space-y-5">
      <SectionHeader icon={ShieldCheck} title="Risk Merkezi" description="Backend kaynaklı deterministik risk sınırları" />
      <div className="grid gap-5 xl:grid-cols-2">
        <RiskPanel status={status} onSystemStatusChange={onSystemStatusChange} />
        <PlatformStatus status={status} marketCandles={[]} marketError={null} />
      </div>
    </div>
  );
}

function LogsSection({ events, onRefresh, loading }: { events: AuditEvent[]; onRefresh: () => Promise<void>; loading: boolean }) {
  return (
    <div className="space-y-5">
      <SectionHeader
        icon={ScrollText}
        title="Kayıtlar"
        description="Bu oturumdaki menü, API ve kontrol olayları"
        action={
          <Button variant="secondary" onClick={() => void onRefresh()} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
            Yenile
          </Button>
        }
      />
      <section className="rounded-md border border-line bg-panel">
        <div className="border-b border-line px-4 py-3">
          <h2 className="text-sm font-black uppercase tracking-normal">Olay Akışı</h2>
        </div>
        <div className="divide-y divide-line/80">
          {events.map((event) => (
            <div key={event.id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[130px_150px_minmax(0,1fr)_96px] md:items-center">
              <span className="text-textMuted">{formatTime(event.time)}</span>
              <span className="font-semibold">{event.source}</span>
              <span className="text-textMuted">{event.message}</span>
              <Badge tone={event.tone} className="w-fit">{event.tone}</Badge>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function SettingsSection({
  status,
  currentUser,
  updatingControl,
  onRefreshAll,
  onToggleTradingControl
}: {
  status: SystemStatus | null;
  currentUser: UserResponse | null;
  updatingControl: boolean;
  onRefreshAll: () => Promise<void>;
  onToggleTradingControl: () => Promise<void>;
}) {
  const halted = status?.trading_halted ?? true;
  return (
    <div className="space-y-5">
      <SectionHeader icon={Settings} title="Ayarlar" description="Güvenlik ve çalışma modu ayarları" />
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-md border border-line bg-panel p-4">
          <h2 className="text-sm font-black uppercase tracking-normal">Sistem Kontrolleri</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void onRefreshAll()}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Durumu Yenile
            </Button>
            <Button variant={halted ? "secondary" : "danger"} disabled={!status || updatingControl} onClick={() => void onToggleTradingControl()}>
              {halted ? <PlayCircle className="h-4 w-4" aria-hidden="true" /> : <AlertOctagon className="h-4 w-4" aria-hidden="true" />}
              {halted ? "Paper Modu Sürdür" : "Acil Durdur"}
            </Button>
          </div>
          <div className="mt-4 grid gap-3 text-sm">
            <StatusLine label="Çalışma modu" value={status?.trading_mode === "testnet" ? "Testnet" : "Kağıt işlem"} />
            <StatusLine label="Canlı emirler" value="Kapalı" />
            <StatusLine label="Borsa anahtarları" value="Yok" />
            <StatusLine label="AI emir erişimi" value="Kapalı" />
          </div>
        </section>
        <PlatformStatus status={status} marketCandles={[]} marketError={null} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2 mt-5">
        <ChangePasswordForm />
        {currentUser?.is_admin && <UserManagement />}
      </div>
    </div>
  );
}

function MarketToolbar({
  symbol,
  interval,
  symbols,
  loading,
  onSymbolChange,
  onIntervalChange,
  onRefresh
}: {
  symbol: string;
  interval: string;
  symbols: MarketSymbol[];
  loading: boolean;
  onSymbolChange: (value: string) => void;
  onIntervalChange: (value: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const symbolValues = symbols.length ? symbols.map((item) => item.symbol) : fallbackMarketSymbols;

  return (
    <section className="flex flex-wrap items-end gap-3 rounded-md border border-line bg-panel p-4">
      <LabeledSelect label="Sembol" value={symbol} values={symbolValues} onChange={onSymbolChange} />
      <LabeledSelect label="Zaman Aralığı" value={interval} values={marketIntervals} onChange={onIntervalChange} />
      <Button variant="secondary" disabled={loading} onClick={() => void onRefresh()}>
        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
        Piyasa Verisini Yenile
      </Button>
    </section>
  );
}

function CandleTable({ candles }: { candles: MarketCandle[] }) {
  const rows = candles.slice(-12).reverse();
  return (
    <section className="rounded-md border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="text-sm font-black uppercase tracking-normal">Son Mumlar</h2>
        <Badge tone="neutral">{candles.length} KAYIT</Badge>
      </div>
      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase text-textMuted">
              <tr className="border-b border-line">
                <th className="px-4 py-3 font-bold">Zaman</th>
                <th className="px-4 py-3 font-bold">Açılış</th>
                <th className="px-4 py-3 font-bold">Yüksek</th>
                <th className="px-4 py-3 font-bold">Düşük</th>
                <th className="px-4 py-3 font-bold">Kapanış</th>
                <th className="px-4 py-3 font-bold">Hacim</th>
                <th className="px-4 py-3 font-bold">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((candle) => (
                <tr key={candle.open_time} className="border-b border-line/70 last:border-0">
                  <td className="px-4 py-3 text-textMuted">{formatDateTime(candle.open_time)}</td>
                  <td className="px-4 py-3">{formatPrice(candle.open)}</td>
                  <td className="px-4 py-3 text-teal-100">{formatPrice(candle.high)}</td>
                  <td className="px-4 py-3 text-rose-100">{formatPrice(candle.low)}</td>
                  <td className="px-4 py-3 font-semibold">{formatPrice(candle.close)}</td>
                  <td className="px-4 py-3 text-textMuted">{formatCompact(candle.volume)}</td>
                  <td className="px-4 py-3 text-textMuted">{candle.trade_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="Mum verisi yok" detail="Public market-data endpoint yanıt verdiğinde tablo dolacak." className="min-h-64" />
      )}
    </section>
  );
}

function PositionsTable({ portfolio }: { portfolio: PaperPortfolio | null }) {
  const positions = portfolio?.open_positions ?? [];
  if (!positions.length) {
    return <EmptyState title="Açık paper pozisyon yok" detail="Bot sinyal üretip risk onayı aldığında pozisyon burada görünür." className="min-h-56" />;
  }

  return (
    <div className="overflow-hidden">
      <table className="w-full table-fixed text-left text-xs xl:text-sm">
        <thead className="text-xs uppercase text-textMuted">
          <tr className="border-b border-line">
            <th className="w-[15%] px-3 py-3 font-bold">Sembol</th>
            <th className="w-[14%] px-3 py-3 font-bold text-right">Miktar</th>
            <th className="w-[12%] px-3 py-3 font-bold text-right">Giriş</th>
            <th className="w-[12%] px-3 py-3 font-bold text-right">Güncel</th>
            <th className="w-[13%] px-3 py-3 font-bold text-right">K/Z</th>
            <th className="w-[11%] px-3 py-3 font-bold text-right">Stop</th>
            <th className="w-[13%] px-3 py-3 font-bold text-right">Hedef</th>
            <th className="w-[10%] px-3 py-3 font-bold text-right">Str.</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const pnl = position.unrealized_pnl ?? 0;
            const pnlPct = position.unrealized_pnl_pct ?? 0;
            const pnlClass = pnl >= 0 ? "text-teal-100" : "text-rose-100";
            const strategyLabel = position.strategy.replace("_SPOT_LONG", "").replace("EMA_RSI", "EMA");

            return (
              <tr key={position.id} className="border-b border-line/70 last:border-0">
                <td className="truncate px-3 py-3 font-semibold" title={position.symbol}>{position.symbol}</td>
                <td className="truncate px-3 py-3 text-right text-textMuted" title={formatQuantity(position.quantity)}>
                  {formatQuantity(position.quantity)}
                </td>
                <td className="truncate px-3 py-3 text-right" title={formatPrice(position.entry_price)}>{formatPrice(position.entry_price)}</td>
                <td className="truncate px-3 py-3 text-right" title={formatPrice(position.current_price ?? position.entry_price)}>
                  {formatPrice(position.current_price ?? position.entry_price)}
                </td>
                <td className={`px-3 py-3 text-right font-black ${pnlClass}`}>
                  <div>{formatSignedMoney(pnl)}</div>
                  <div className="text-xs">{formatSignedPercent(pnlPct)}</div>
                </td>
                <td className="truncate px-3 py-3 text-right text-rose-100" title={formatPrice(position.stop_loss)}>{formatPrice(position.stop_loss)}</td>
                <td className="truncate px-3 py-3 text-right text-teal-100" title={formatPrice(position.take_profit)}>
                  {formatPrice(position.take_profit)}
                </td>
                <td className="truncate px-3 py-3 text-right text-textMuted" title={position.strategy}>{strategyLabel}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TradesTable({ portfolio }: { portfolio: PaperPortfolio | null }) {
  const trades = portfolio?.closed_trades ?? [];
  if (!trades.length) {
    return <EmptyState title="Kapanmış paper işlem yok" detail="Stop-loss veya take-profit ile kapanan simüle işlemler burada listelenir." className="min-h-72" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="text-xs uppercase text-textMuted">
          <tr className="border-b border-line">
            <th className="px-4 py-3 font-bold">Zaman</th>
            <th className="px-4 py-3 font-bold">Sembol</th>
            <th className="px-4 py-3 font-bold">Yön</th>
            <th className="px-4 py-3 font-bold">Giriş</th>
            <th className="px-4 py-3 font-bold">Çıkış</th>
            <th className="px-4 py-3 font-bold">PnL</th>
            <th className="px-4 py-3 font-bold">Neden</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice().reverse().map((trade) => (
            <tr key={trade.id} className="border-b border-line/70 last:border-0">
              <td className="px-4 py-3 text-textMuted">{formatTime(trade.closed_at)}</td>
              <td className="px-4 py-3 font-semibold">{trade.symbol}</td>
              <td className="px-4 py-3">{trade.side}</td>
              <td className="px-4 py-3">{formatPrice(trade.entry_price)}</td>
              <td className="px-4 py-3">{formatPrice(trade.exit_price)}</td>
              <td className={`px-4 py-3 font-semibold ${trade.realized_pnl >= 0 ? "text-teal-100" : "text-rose-100"}`}>{formatMoney(trade.realized_pnl)}</td>
              <td className="px-4 py-3 text-textMuted">{trade.exit_reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BotStatus({
  status,
  automation
}: {
  status: SystemStatus | null;
  automation: AutomationState | null;
}) {
  const halted = status?.trading_halted ?? true;
  const running = automation?.running ?? false;
  const statusLabel = halted ? "DURDURULDU" : running ? "ÇALIŞIYOR" : "KAPALI";
  const statusTone = halted ? "warning" : running ? "paper" : "neutral";
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Bot Durumu</h2>
          <p className="text-xs text-textMuted">
            {halted
              ? "Yeni sinyal ve emirler engelli"
              : running
                ? "Otomatik paper taraması çalışıyor"
                : "Bot manuel olarak başlatılmayı bekliyor"}
          </p>
        </div>
        <Badge tone={statusTone}>{statusLabel}</Badge>
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        <StatusLine label="İşlem modu" value={status?.trading_mode === "testnet" ? "Testnet" : "Kağıt işlem"} />
        <StatusLine label="Otomasyon" value={running ? "Aktif" : halted ? "Güvenlik kilitli" : "Kapalı"} />
        <StatusLine label="Tarama" value={automation ? `${formatExchange(automation.exchange)} / ${automation.interval}` : "-"} />
        <StatusLine label="Son döngü" value={automation?.last_cycle_at ? formatTime(automation.last_cycle_at) : "Henüz çalışmadı"} />
        <StatusLine label="Gerçek emirler" value="Devre dışı" />
        <StatusLine label="YZ emir erişimi" value="Engellendi" />
      </div>
    </section>
  );
}

type EditableRiskLimits = Omit<RiskLimits, "stop_loss_required">;

const defaultRiskLimitFormData: EditableRiskLimits = {
  risk_per_trade: 0.005,
  max_single_position_pct: 0.1,
  max_total_exposure_pct: 0.3,
  max_open_positions: 3,
  daily_loss_limit_pct: 0.02,
  max_drawdown_limit_pct: 0.08,
  min_risk_reward: 1.5,
  cooldown_after_losses: 3
};

function createRiskLimitFormData(limits: RiskLimits | null | undefined): EditableRiskLimits {
  if (!limits) {
    return defaultRiskLimitFormData;
  }

  return {
    risk_per_trade: limits.risk_per_trade,
    max_single_position_pct: limits.max_single_position_pct,
    max_total_exposure_pct: limits.max_total_exposure_pct,
    max_open_positions: limits.max_open_positions,
    daily_loss_limit_pct: limits.daily_loss_limit_pct,
    max_drawdown_limit_pct: limits.max_drawdown_limit_pct,
    min_risk_reward: limits.min_risk_reward,
    cooldown_after_losses: limits.cooldown_after_losses
  };
}

function validateRiskLimitForm(formData: EditableRiskLimits): string | null {
  const numericValues = Object.values(formData);
  if (numericValues.some((value) => !Number.isFinite(value))) {
    return "Tüm risk limitleri sayısal olmalı.";
  }

  if (formData.risk_per_trade <= 0 || formData.risk_per_trade > 0.05) {
    return "İşlem başına risk 0 ile %5 arasında olmalı.";
  }

  if (formData.max_single_position_pct <= 0 || formData.max_single_position_pct > 1) {
    return "Maksimum pozisyon oranı 0 ile %100 arasında olmalı.";
  }

  if (formData.max_total_exposure_pct < formData.max_single_position_pct || formData.max_total_exposure_pct > 1) {
    return "Maksimum maruziyet, tek pozisyon oranından düşük olamaz.";
  }

  if (!Number.isInteger(formData.max_open_positions) || formData.max_open_positions < 1 || formData.max_open_positions > 50) {
    return "Açık pozisyon sınırı 1 ile 50 arasında tam sayı olmalı.";
  }

  if (formData.daily_loss_limit_pct <= 0 || formData.daily_loss_limit_pct > 0.5) {
    return "Günlük zarar limiti 0 ile %50 arasında olmalı.";
  }

  if (formData.max_drawdown_limit_pct <= 0 || formData.max_drawdown_limit_pct > 0.8) {
    return "Maksimum gerileme 0 ile %80 arasında olmalı.";
  }

  if (formData.min_risk_reward < 1 || formData.min_risk_reward > 10) {
    return "Minimum R/R 1 ile 10 arasında olmalı.";
  }

  if (!Number.isInteger(formData.cooldown_after_losses) || formData.cooldown_after_losses < 0 || formData.cooldown_after_losses > 20) {
    return "Kayıp sonrası bekleme sınırı 0 ile 20 arasında tam sayı olmalı.";
  }

  return null;
}

function RiskPanel({
  status,
  onSystemStatusChange
}: {
  status: SystemStatus | null;
  onSystemStatusChange: (value: SystemStatus) => void;
}) {
  const limits = status?.risk_limits;
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<EditableRiskLimits>(() => createRiskLimitFormData(limits));
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleChange = (key: keyof EditableRiskLimits, value: string) => {
    const parsedValue = key === "max_open_positions" || key === "cooldown_after_losses"
      ? Number.parseInt(value, 10)
      : Number.parseFloat(value);

    setFormError(null);
    setFormData((prev) => ({ ...prev, [key]: Number.isNaN(parsedValue) ? 0 : parsedValue }));
  };

  const handleStartEditing = () => {
    setFormData(createRiskLimitFormData(limits));
    setFormError(null);
    setIsEditing(true);
  };

  const handleCancel = () => {
    setFormData(createRiskLimitFormData(limits));
    setFormError(null);
    setIsEditing(false);
  };

  const handleSave = async () => {
    const validationError = validateRiskLimitForm(formData);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    try {
      setIsSaving(true);
      setFormError(null);
      const nextStatus = await updateRiskLimits(formData);
      onSystemStatusChange(nextStatus);
      setFormData(createRiskLimitFormData(nextStatus.risk_limits));
      setIsEditing(false);
    } catch (requestError) {
      setFormError(requestError instanceof Error ? requestError.message : "Risk limitleri kaydedilemedi.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Risk Durumu</h2>
          <p className="text-xs text-textMuted">Deterministik güvenlik sınırları</p>
        </div>
        {!isEditing ? (
          <Button variant="secondary" className="h-8 text-xs" onClick={handleStartEditing}>Düzenle</Button>
        ) : (
          <div className="flex gap-2">
            <Button variant="secondary" className="h-8 text-xs" onClick={handleCancel} disabled={isSaving}>İptal</Button>
            <Button variant="primary" className="h-8 text-xs" onClick={() => void handleSave()} disabled={isSaving}>
              {isSaving ? "Kaydediliyor..." : "Kaydet"}
            </Button>
          </div>
        )}
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        {!isEditing ? (
          <>
            <StatusLine label="İşlem başına risk" value={formatPercent(limits?.risk_per_trade)} />
            <StatusLine label="Maks. pozisyon" value={formatPercent(limits?.max_single_position_pct)} />
            <StatusLine label="Maks. maruziyet" value={formatPercent(limits?.max_total_exposure_pct)} />
            <StatusLine label="Açık pozisyon sınırı" value={limits ? String(limits.max_open_positions) : "-"} />
            <StatusLine label="Günlük zarar limiti" value={formatPercent(limits?.daily_loss_limit_pct)} />
            <StatusLine label="Maks. gerileme" value={formatPercent(limits?.max_drawdown_limit_pct)} />
            <StatusLine label="Minimum R/R" value={limits ? String(limits.min_risk_reward) : "-"} />
            <StatusLine label="Kayıp sonrası bekleme" value={limits ? String(limits.cooldown_after_losses) : "-"} />
            <StatusLine label="Zarar durdur" value={limits?.stop_loss_required ? "Zorunlu" : "-"} />
          </>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {formError ? (
              <div className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-rose-100 md:col-span-2">
                {formError}
              </div>
            ) : null}
            <div>
              <label className="mb-1 block text-xs text-textMuted">İşlem başına risk (örn: 0.01)</label>
              <input type="number" min="0.001" max="0.05" step="0.001" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.risk_per_trade} onChange={(e) => handleChange("risk_per_trade", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Maks. pozisyon (örn: 0.05)</label>
              <input type="number" min="0.01" max="1" step="0.01" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.max_single_position_pct} onChange={(e) => handleChange("max_single_position_pct", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Maks. maruziyet (örn: 0.2)</label>
              <input type="number" min="0.01" max="1" step="0.01" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.max_total_exposure_pct} onChange={(e) => handleChange("max_total_exposure_pct", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Açık pozisyon sınırı</label>
              <input type="number" min="1" max="50" step="1" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.max_open_positions} onChange={(e) => handleChange("max_open_positions", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Günlük zarar limiti (örn: 0.02)</label>
              <input type="number" min="0.001" max="0.5" step="0.001" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.daily_loss_limit_pct} onChange={(e) => handleChange("daily_loss_limit_pct", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Maks. gerileme (örn: 0.1)</label>
              <input type="number" min="0.001" max="0.8" step="0.001" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.max_drawdown_limit_pct} onChange={(e) => handleChange("max_drawdown_limit_pct", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Minimum R/R (örn: 1.5)</label>
              <input type="number" min="1" max="10" step="0.1" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.min_risk_reward} onChange={(e) => handleChange("min_risk_reward", e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-textMuted">Kayıp sonrası bekleme</label>
              <input type="number" min="0" max="20" step="1" className="w-full rounded-md border border-line bg-background px-3 py-1.5 text-sm" value={formData.cooldown_after_losses} onChange={(e) => handleChange("cooldown_after_losses", e.target.value)} />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function StrategiesTable({
  validation,
  loading,
  error
}: {
  validation: ActivationValidationSummary | null;
  loading: boolean;
  error: string | null;
}) {
  const rows = validation?.rows ?? [];
  const completed = rows.filter((row) => row.passed).length;
  const phaseLabel = validation?.phase === "PHASE_1" ? "AŞAMA 1" : validation?.phase ?? "AŞAMA 1";
  return (
    <section className="rounded-md border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Aktivasyon Doğrulaması</h2>
          <p className="text-xs text-textMuted">
            {loading ? "Paper bot kontrol listesi doğrulanıyor" : error ? error : `${completed}/${rows.length} kontrol tamamlandı`}
          </p>
        </div>
        <Badge tone={validation?.ready ? "paper" : "neutral"}>{phaseLabel}</Badge>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="text-xs uppercase text-textMuted">
            <tr className="border-b border-line">
              <th className="px-4 py-3 font-bold">Kontrol</th>
              <th className="px-4 py-3 font-bold">Durum</th>
              <th className="px-4 py-3 font-bold">Ana Rejim</th>
              <th className="px-4 py-3 font-bold">Aktivasyon</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row) => (
              <tr key={row.key} className="border-b border-line/70 last:border-0">
                <td className="px-4 py-3 font-semibold">
                  <div>{row.name}</div>
                  <div className="mt-1 text-xs font-normal text-textMuted">Mevcut: {row.actual}</div>
                  <div className="text-xs font-normal text-textMuted">Gerekli: {row.required}</div>
                </td>
                <td className="px-4 py-3 text-textMuted">{row.status}</td>
                <td className="px-4 py-3 text-textMuted">{row.market_regime}</td>
                <td className="px-4 py-3"><Badge tone={row.passed ? "paper" : "warning"}>{row.activation}</Badge></td>
              </tr>
            )) : (
              <tr>
                <td className="px-4 py-6 text-textMuted" colSpan={4}>
                  {loading ? "Doğrulama yükleniyor..." : "Doğrulama verisi yok."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PlatformStatus({
  status,
  marketCandles,
  marketError
}: {
  status: SystemStatus | null;
  marketCandles: MarketCandle[];
  marketError: string | null;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Platform Durumu</h2>
          <p className="text-xs text-textMuted">Canlı backend denetimi</p>
        </div>
        <CheckCircle2 className="h-5 w-5 text-accent" aria-hidden="true" />
      </div>
      <div className="grid gap-3 text-sm">
        <StatusLine label="API bağlantısı" value={status ? "Bağlı" : "Bağlantı yok"} />
        <StatusLine label="Market data" value={marketError ? "Hata" : marketCandles.length ? "Bağlı" : "Bekliyor"} />
        <StatusLine label="Kill switch" value={status?.trading_halted ? "Etkin" : "Pasif"} />
        <StatusLine label="Canlı işlem" value="Kalıcı olarak kapalı" />
        <StatusLine label="Son güncelleme" value={formatTime(status?.updated_at)} />
      </div>
    </section>
  );
}

function ConnectionBadge({ status, error, loading }: { status: SystemStatus | null; error: string | null; loading: boolean }) {
  if (loading && !status) {
    return <Badge tone="neutral">BAĞLANIYOR</Badge>;
  }
  if (error || !status) {
    return <Badge tone="danger">API ÇEVRİMDIŞI</Badge>;
  }
  return (
    <Badge tone="paper" className="gap-1.5">
      <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
      API BAĞLI
    </Badge>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  description,
  action
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-accent/35 bg-accent/12">
            <Icon className="h-5 w-5 text-accent" aria-hidden={true} />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-base font-black uppercase tracking-normal">{title}</h2>
            <p className="truncate text-sm text-textMuted">{description}</p>
          </div>
        </div>
        {action}
      </div>
    </section>
  );
}

function InfoCard({
  icon: Icon,
  title,
  badge,
  badgeTone,
  children
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  badge: string;
  badgeTone: "paper" | "neutral" | "warning" | "danger";
  children: ReactNode;
}) {
  return (
    <section className="rounded-md border border-line bg-panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden={true} />
          <h2 className="truncate text-sm font-black uppercase tracking-normal">{title}</h2>
        </div>
        <Badge tone={badgeTone}>{badge}</Badge>
      </div>
      {children}
    </section>
  );
}

function PipelineStep({ number, title, detail, state }: { number: string; title: string; detail: string; state: string }) {
  return (
    <div className="rounded-md border border-line bg-panelMuted/45 p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-xs font-black text-slate-950">{number}</span>
        <Badge tone={state === "Aktif" ? "paper" : "neutral"}>{state}</Badge>
      </div>
      <p className="mt-3 text-sm font-black">{title}</p>
      <p className="mt-1 text-xs text-textMuted">{detail}</p>
    </div>
  );
}

function LabeledSelect({
  label,
  value,
  values,
  onChange
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid min-w-40 gap-2 text-sm">
      <span className="font-bold text-textMuted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-line bg-panelMuted px-3 text-textPrimary outline-none focus:border-accent"
      >
        {values.map((item) => (
          <option key={item} value={item}>{item}</option>
        ))}
      </select>
    </label>
  );
}

function MarketListTable({
  symbols,
  tickers,
  loading,
  error,
  quoteAsset,
  search,
  onQuoteAssetChange,
  onSearchChange,
  onRefresh,
  onSelectSymbol
}: {
  symbols: MarketSymbol[];
  tickers: MarketTicker[];
  loading: boolean;
  error: string | null;
  quoteAsset: string;
  search: string;
  onQuoteAssetChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onSelectSymbol: (symbol: string, exchange?: string) => void;
}) {
  const normalizedSearch = search.toUpperCase().trim();
  const filtered = tickers.filter((ticker) =>
    normalizedSearch
      ? `${ticker.exchange} ${ticker.symbol}`.toUpperCase().includes(normalizedSearch)
      : true
  ).slice(0, 100);

  return (
    <section className="rounded-md border border-line bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-black uppercase tracking-normal">Market Listesi</h2>
          <p className="text-xs text-textMuted">{tickers.length} {quoteAsset} pari, {symbols.length} spot sembol</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LabeledSelect label="Quote" value={quoteAsset} values={quoteAssets} onChange={onQuoteAssetChange} />
          <label className="grid gap-2 text-sm">
            <span className="font-bold text-textMuted">Ara</span>
            <input
              type="text"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="BTCUSDT"
              className="h-10 w-36 rounded-md border border-line bg-panelMuted px-3 text-textPrimary outline-none focus:border-accent"
            />
          </label>
          <Button variant="secondary" disabled={loading} onClick={() => void onRefresh()} className="self-end">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
            Yenile
          </Button>
        </div>
      </div>
      {error ? (
        <EmptyState title="Market listesi alınamadı" detail={error} className="min-h-48" />
      ) : loading && !tickers.length ? (
        <LoadingState title="Binance ticker verisi yükleniyor" detail="Public 24h ticker endpoint okunuyor." className="min-h-48" />
      ) : !filtered.length ? (
        <EmptyState title="Eşleşen sembol bulunamadı" detail={`"${search}" araması sonuç üretmedi.`} className="min-h-48" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase text-textMuted">
              <tr className="border-b border-line">
                <th className="px-4 py-3 font-bold">Sembol</th>
                <th className="px-4 py-3 font-bold">Borsa</th>
                <th className="px-4 py-3 font-bold text-right">Son Fiyat</th>
                <th className="px-4 py-3 font-bold text-right">24s Değişim</th>
                <th className="px-4 py-3 font-bold text-right">Yüksek</th>
                <th className="px-4 py-3 font-bold text-right">Düşük</th>
                <th className="px-4 py-3 font-bold text-right">Hacim ({quoteAsset})</th>
                <th className="px-4 py-3 font-bold text-right">İşlem</th>
                <th className="px-4 py-3 font-bold"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ticker) => {
                const positive = ticker.price_change_percent >= 0;
                return (
                  <tr key={`${ticker.exchange}-${ticker.symbol}`} className="border-b border-line/70 last:border-0 hover:bg-panelMuted/50 transition-colors">
                    <td className="px-4 py-3 font-semibold">{ticker.symbol}</td>
                    <td className="px-4 py-3"><Badge tone="neutral">{formatExchange(ticker.exchange)}</Badge></td>
                    <td className="px-4 py-3 text-right">{formatPrice(ticker.last_price)}</td>
                    <td className={`px-4 py-3 text-right font-semibold ${positive ? "text-teal-100" : "text-rose-100"}`}>
                      {positive ? "+" : ""}{ticker.price_change_percent.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right text-textMuted">{formatPrice(ticker.high_price)}</td>
                    <td className="px-4 py-3 text-right text-textMuted">{formatPrice(ticker.low_price)}</td>
                    <td className="px-4 py-3 text-right text-textMuted">{formatCompact(ticker.quote_volume)}</td>
                    <td className="px-4 py-3 text-right text-textMuted">{formatCompact(ticker.trade_count)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => onSelectSymbol(ticker.symbol, ticker.exchange)}
                        className="rounded-md border border-accent/35 bg-accent/12 px-2 py-1 text-xs font-bold text-teal-100 transition hover:bg-accent/25"
                      >
                        Seç
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, helper, tone }: { label: string; value: string; helper: string; tone: "paper" | "neutral" | "danger" }) {
  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs font-bold uppercase text-textMuted">{label}</p>
        <span className={`h-2 w-2 rounded-full ${tone === "paper" ? "bg-accent" : tone === "danger" ? "bg-danger" : "bg-slate-500"}`} />
      </div>
      <p className="mt-3 truncate text-2xl font-black tracking-normal">{value}</p>
      <p className="mt-1 truncate text-xs text-textMuted">{helper}</p>
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-h-9 items-center justify-between gap-3 rounded-md bg-panelMuted/70 px-3">
      <span className="min-w-0 text-textMuted">{label}</span>
      <span className="shrink-0 text-right font-bold text-textPrimary">{value}</span>
    </div>
  );
}

function formatPercent(value: number | undefined): string {
  if (value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

function formatSignedPercent(value: number | undefined): string {
  if (value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 2, signDisplay: "always" }).format(value);
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: value >= 100 ? 2 : 6 }).format(value);
}

function formatQuantity(value: number): string {
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 8 }).format(value);
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(value);
}

function formatSignedMoney(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    signDisplay: "always"
  }).format(value);
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat("tr-TR", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function formatMarketSource(source: string): string {
  if (source.startsWith("offline_paper")) {
    return "paper data";
  }

  return "public market data";
}

function formatExchange(exchange?: string | null): string {
  if (!exchange) {
    return "-";
  }

  return exchangeLabels[exchange] ?? exchange.toUpperCase();
}

function formatTime(value: string | undefined): string {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}

function formatDateTime(value: number): string {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
