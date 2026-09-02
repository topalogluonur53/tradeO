# NEXUS AI TRADER

AI-assisted crypto paper-trading terminal. Phase 1 is intentionally limited to paper trading and testnet-safe architecture. It does not send real orders, request exchange API keys, or claim guaranteed returns.

## Architecture

The modular monolith flow is prepared as:

Market Data -> Indicators -> Market Regime Detector -> Strategy Engine -> Signal -> Optional AI Analysis -> Risk Engine -> Order Validator -> Paper Execution Engine -> Portfolio

Risk, PnL, position sizing, fees, slippage, indicators, and stop-loss checks are deterministic backend concerns. LLM output may explain context, but it must not place orders or calculate trading risk.

## Run Locally

Windows quick start (after installing dependencies once):

```powershell
.\baslat.bat
```

The script starts the FastAPI backend and Next.js frontend in separate terminal windows, waits until both are ready, and opens the application in the default browser. It leaves an already running service untouched. Use `.\baslat.bat --no-browser` to skip opening the browser.

## How To Use The Paper Bot

1. Run `.\baslat.bat` and open http://127.0.0.1:3000.
2. Open `Piyasalar`, choose a symbol and interval, then confirm candles are loading.
3. Open `Geri Test`, choose the same symbol, and run the backtest.
4. Open `Kağıt İşlem` and press `Tek Döngü` to run one safe paper-trading cycle.
5. Press `Botu Başlat` to enable automatic paper trading. The backend loop checks public candles every `PAPER_TRADE_INTERVAL_SECONDS`.
6. Use `Acil Durdur` any time. It blocks new signals and paper orders through the shared kill switch.

This is still paper trading. It does not send real exchange orders, does not ask for exchange API keys, and does not trade futures, margin, leverage, shorts, or withdrawals.

Backend:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Docker:

```powershell
docker compose up --build
```

Services:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- System status: http://localhost:8000/api/system/status
- Market candles: http://localhost:8000/api/market-data/candles?symbol=BTCUSDT&interval=1h&limit=200
- Trading state: http://localhost:8000/api/trading/state
- Run one paper cycle: POST http://localhost:8000/api/trading/step?symbol=BTCUSDT&interval=1h
- Backtest: http://localhost:8000/api/trading/backtest?symbol=BTCUSDT&interval=1h&limit=300
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Validation Commands

```powershell
cd backend
python -m pytest
python -c "from app.main import app; print(app.title)"

cd ../frontend
npm run lint
npm run type-check
npm run build

cd ..
docker compose config
```

## Current Scope

- FastAPI backend with structured config, logging, CORS, database session helpers, Alembic, health route, trading safety interfaces, and tests.
- Read-only Binance public market-data adapter for OHLCV candles. It does not use exchange API keys or trading endpoints.
- Deterministic EMA/RSI spot-long strategy engine, risk sizing, order validation, in-memory paper broker, automatic paper trading loop, and backtest endpoint.
- Next.js trading terminal UI with live API status, functional mobile navigation, backend-controlled Emergency Stop/resume actions, dashboard metrics, live candlestick chart, market table, bot controls, paper portfolio, trade history, risk status, and reusable loading/empty/error components.
- Docker Compose with PostgreSQL, Redis, backend, worker, and frontend services.

## Safety Limits

- Paper trading only by default.
- Spot long-or-cash model only.
- No futures, leverage, margin, shorts, withdrawals, or live exchange key collection.
- Stop-loss is mandatory for automated orders.
- Kill switch blocks signals and orders and is not bypassable by strategy or AI modules.

## Known Limitations

- Persistent market-data storage, persistent order storage, advanced walk-forward reports, and AI narrative analysis are Phase 2+ work.
- Dashboard values are empty or explicitly marked demo until paper-trading data exists.
- The backend database layer is configured but migrations are intentionally minimal until domain tables are finalized.

## Phase 2 Direction

- Add persistent OHLCV storage and scheduled market-data refresh jobs.
- Implement deterministic indicator pipelines and strategy selection by market regime.
- Add walk-forward validation, out-of-sample reporting, fees/slippage modeling, and Monte Carlo trade-order simulation scaffolding.
