"""
Scores a wallet based on its trade history.
All weights are configurable and loaded from settings (or overridden via API).
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

from config import settings
from models.wallet import Trade, WalletScore, TradeDirection

log = logging.getLogger(__name__)


class ScoringEngine:
    def __init__(self, weights: Optional[dict] = None):
        # Allow runtime weight overrides from the dashboard config panel
        w = weights or {}
        self.early_entry_w = w.get("early_entry_weight", settings.early_entry_weight)
        self.win_rate_w = w.get("win_rate_weight", settings.win_rate_weight)
        self.roi_w = w.get("roi_weight", settings.roi_weight)
        self.consistency_w = w.get("consistency_weight", settings.consistency_weight)
        self.conviction_quality_w = w.get("conviction_quality_weight", settings.conviction_quality_weight)
        self.exit_cleanliness_w = w.get("exit_cleanliness_weight", settings.exit_cleanliness_weight)
        self.arb_max_hold = w.get("arb_max_hold_seconds", settings.arb_max_hold_seconds)
        self.arb_position_ratio = w.get("arb_max_position_ratio", settings.arb_max_position_ratio)
        self.min_trades = w.get("min_trades", settings.min_trades)
        self.min_exit_cleanliness = w.get("min_exit_cleanliness", settings.min_exit_cleanliness)

    def score(
        self,
        wallet: str,
        trades: List[Trade],
        market_open_prices: Optional[Dict[str, float]] = None,
    ) -> Optional[WalletScore]:
        """
        Returns a WalletScore or None if the wallet doesn't meet minimum criteria.
        market_open_prices: mapping of market_id → opening price, fetched by the scanner.
        """
        if len(trades) < self.min_trades:
            return None

        # ---- Basic metrics ----
        resolved = [t for t in trades if t.resolved and t.won is not None]
        won = [t for t in resolved if t.won]
        win_rate = len(won) / len(resolved) if resolved else 0.0

        buy_trades = [t for t in trades if t.direction == TradeDirection.BUY]
        sell_trades = [t for t in trades if t.direction == TradeDirection.SELL]
        total_invested = sum(t.size_usdc for t in buy_trades)

        # Realized returns = actual USDC received from SELL trades (confirmed exits)
        sell_proceeds = sum(t.size_usdc for t in sell_trades)

        # Theoretical payout for positions held to resolution and won:
        # size_usdc / price = shares bought; each share pays $1 at resolution.
        # Only count BUY trades (not SELLs) to avoid double-counting.
        won_buy_trades = [t for t in won if t.direction == TradeDirection.BUY]
        held_won_payout = sum(
            t.size_usdc / t.price for t in won_buy_trades if t.price > 0
        )

        # ROI is calculated on CLOSED positions only (resolved or manually sold out).
        # Open (unresolved) positions are excluded from both numerator and denominator
        # so an early-stage wallet with mostly open positions doesn't look like a 100%
        # loser just because its markets haven't resolved yet.
        sells_by_market: Dict[str, float] = defaultdict(float)
        for t in sell_trades:
            sells_by_market[t.market_id] += t.size_usdc

        closed_invested = 0.0
        closed_returned = 0.0
        for t in buy_trades:
            market_resolved = t.resolved  # True if CLOB confirmed market closed
            market_sold = sells_by_market.get(t.market_id, 0.0) > 0
            if market_resolved or market_sold:
                closed_invested += t.size_usdc
        # Returns on closed positions
        closed_returned = sell_proceeds + held_won_payout

        roi = (closed_returned - closed_invested) / closed_invested if closed_invested > 0 else 0.0

        total_returned = sell_proceeds + held_won_payout  # actual cash received (display only)

        markets = set(t.market_id for t in trades)
        distinct_markets = len(markets)

        # ---- Average bet size ----
        avg_bet_size_usdc = (
            sum(t.size_usdc for t in buy_trades) / len(buy_trades) if buy_trades else 0.0
        )

        # ---- Conviction quality ----
        # Win rate specifically on above-average bets vs overall win rate.
        # Positive delta means the whale's large bets outperform their small bets —
        # the most valuable signal under a conviction-exponent copy model.
        resolved_buys = [t for t in buy_trades if t.resolved and t.won is not None]
        high_conviction = [t for t in resolved_buys if t.size_usdc >= avg_bet_size_usdc]
        conviction_win_rate = (
            sum(1 for t in high_conviction if t.won) / len(high_conviction)
            if high_conviction else win_rate
        )
        conviction_win_rate_delta = conviction_win_rate - win_rate

        # ---- Exit cleanliness ----
        # Fraction of markets where the wallet exited in a single SELL transaction.
        # Clean exits (1.0) are easier to follow via chain monitoring than drip-sells.
        sell_trades = [t for t in trades if t.direction == TradeDirection.SELL]
        if sell_trades:
            sells_by_market: dict = defaultdict(list)
            for t in sell_trades:
                sells_by_market[t.market_id].append(t)
            single_exits = sum(1 for sells in sells_by_market.values() if len(sells) == 1)
            exit_cleanliness = single_exits / len(sells_by_market)
        else:
            exit_cleanliness = 0.0

        # ---- Early entry score ----
        # Compare each trade's entry price to the market's opening price.
        # Trades entered when odds were still underpriced (low p on winners) score higher.
        early_scores: List[float] = []
        for t in resolved:
            if t.won and t.market_final_price is not None:
                # Price moved from entry to 1.0 — bigger move = earlier entry
                price_appreciation = max(0.0, 1.0 - t.price)
                early_scores.append(price_appreciation)

        early_entry_score = (sum(early_scores) / len(early_scores)) if early_scores else 0.0
        avg_entry_price = (sum(t.price for t in trades) / len(trades)) if trades else 0.5

        # ---- avg_market_open_price ----
        # Use actual market opening prices when available; fall back to 0.5 per market.
        if market_open_prices:
            open_prices = [
                market_open_prices[mid]
                for mid in markets
                if mid in market_open_prices
            ]
            avg_market_open_price = sum(open_prices) / len(open_prices) if open_prices else 0.5
        else:
            avg_market_open_price = 0.5

        # ---- Arb detection ----
        arb_flag, arb_reason = self._detect_arb(trades)

        # ---- Composite score (0–100) ----
        # Normalise each component to 0-1, then weight and normalise by total weight
        # so the composite stays in 0-100 regardless of which weights are active.
        wr_norm = min(win_rate / 1.0, 1.0)
        roi_norm = min(max(roi / 2.0, 0.0), 1.0)   # cap at 200% ROI
        ee_norm = min(early_entry_score / 0.5, 1.0)  # cap at 0.5 price appreciation
        cons_norm = min(distinct_markets / 20.0, 1.0)
        # conviction_win_rate_delta in [-1, +1] → normalise to [0, 1]
        cq_norm = (conviction_win_rate_delta + 1.0) / 2.0
        # exit_cleanliness already in [0, 1]
        ec_norm = exit_cleanliness

        total_w = (
            self.win_rate_w + self.roi_w + self.early_entry_w
            + self.consistency_w + self.conviction_quality_w
            + self.exit_cleanliness_w
        )
        raw = (
            self.win_rate_w * wr_norm
            + self.roi_w * roi_norm
            + self.early_entry_w * ee_norm
            + self.consistency_w * cons_norm
            + self.conviction_quality_w * cq_norm
            + self.exit_cleanliness_w * ec_norm
        ) / total_w
        composite = round(raw * 100, 2)

        # Penalise suspected arb accounts
        if arb_flag:
            composite *= 0.3

        first_trade = min(t.timestamp for t in trades)
        last_trade = max(t.timestamp for t in trades)

        return WalletScore(
            wallet=wallet,
            total_trades=len(trades),
            resolved_trades=len(resolved),
            won_trades=len(won),
            win_rate=round(win_rate, 4),
            total_invested_usdc=round(total_invested, 2),
            total_returned_usdc=round(total_returned, 2),
            roi=round(roi, 4),
            distinct_markets=distinct_markets,
            avg_entry_price=round(avg_entry_price, 4),
            avg_market_open_price=round(avg_market_open_price, 4),
            early_entry_score=round(early_entry_score, 4),
            avg_bet_size_usdc=round(avg_bet_size_usdc, 2),
            conviction_win_rate=round(conviction_win_rate, 4),
            conviction_win_rate_delta=round(conviction_win_rate_delta, 4),
            exit_cleanliness=round(exit_cleanliness, 4),
            composite_score=composite,
            arb_flag=arb_flag,
            arb_reason=arb_reason,
            first_trade_at=first_trade,
            last_trade_at=last_trade,
            discovered_at=datetime.now(tz=timezone.utc),
        )

    def passes_filters(self, score: WalletScore) -> bool:
        """Returns True if the wallet meets the minimum thresholds to be a candidate."""
        if score.arb_flag:
            return False
        # Win rate and ROI filters require enough resolved trades to be meaningful.
        # Wallets with mostly unresolved markets are kept until evidence says otherwise.
        if score.resolved_trades >= 5:
            if score.win_rate < settings.min_win_rate:
                return False
            if score.roi < settings.min_roi:
                return False
        if score.distinct_markets < settings.min_markets:
            return False
        if score.exit_cleanliness < self.min_exit_cleanliness:
            return False
        return True

    # ---- Arb detection helpers ----

    def _detect_arb(self, trades: List[Trade]) -> Tuple[bool, Optional[str]]:
        """
        Heuristic arb detection — not perfect, but catches the most common patterns:
         1. Very short hold times (flash arbitrage between order book levels)
         2. Simultaneous YES + NO positions on the same market
         3. Extremely small position sizes relative to market (market maker / liquidity arb)
        """
        reasons: List[str] = []

        # Pattern 1: round-trip trades in the same market very quickly
        by_market: dict = defaultdict(list)
        for t in trades:
            by_market[t.market_id].append(t)

        fast_exits = 0
        for market_id, mkt_trades in by_market.items():
            mkt_trades_sorted = sorted(mkt_trades, key=lambda t: t.timestamp)
            for i in range(1, len(mkt_trades_sorted)):
                dt = (mkt_trades_sorted[i].timestamp - mkt_trades_sorted[i - 1].timestamp).total_seconds()
                if 0 < dt < self.arb_max_hold:
                    fast_exits += 1

        if fast_exits > len(trades) * 0.4:
            reasons.append(f"{fast_exits} trades with hold time < {self.arb_max_hold}s")

        # Pattern 2: opposing positions in same market (hedging / arb)
        for market_id, mkt_trades in by_market.items():
            outcomes = set(t.outcome for t in mkt_trades)
            if "YES" in outcomes and "NO" in outcomes:
                reasons.append(f"Both YES and NO positions in market {market_id[:8]}...")

        # Pattern 3: all trades are tiny — consistent micro-sizing = market maker
        avg_size = sum(t.size_usdc for t in trades) / len(trades) if trades else 0
        if avg_size < 5.0 and len(trades) > 50:
            reasons.append(f"Avg trade size ${avg_size:.2f} with {len(trades)} trades — likely market maker")

        if reasons:
            return True, " | ".join(reasons)
        return False, None
