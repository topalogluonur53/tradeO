from typing import Protocol

from app.trading.schemas import MarketRegime, Signal


class Strategy(Protocol):
    name: str

    def calculate_indicators(self, candles: list[dict[str, float]]) -> dict[str, float]:
        ...

    def generate_signal(self, symbol: str, candles: list[dict[str, float]], regime: MarketRegime) -> Signal | None:
        ...

    def explain_signal(self, signal: Signal) -> str:
        ...
