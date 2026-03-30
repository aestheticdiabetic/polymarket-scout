"""
Rotation Detector — tries to link a new wallet to a known good wallet
that has changed addresses to avoid copy-trading.

Signals used (all weighted):
  1. Common funding source   — both wallets funded from the same parent address
  2. Bet sizing similarity   — similar distribution of trade sizes
  3. Market selection overlap— trades in same markets around the same time
  4. Timing correlation      — activity bursts at similar hours/days

All four signals are scored 0-1 and combined into a confidence score.
If confidence >= settings.rotation_similarity_threshold, we flag the link.
"""
import logging
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from config import settings
from models.wallet import RotationLink, Trade, WalletScore

log = logging.getLogger(__name__)


class RotationDetector:
    def __init__(self, known_scores: List[WalletScore]):
        # Index known wallets by address for fast lookup
        self.known: Dict[str, WalletScore] = {s.wallet: s for s in known_scores}
        # Known trades indexed by wallet
        self.known_trades: Dict[str, List[Trade]] = {}

    def register_trades(self, wallet: str, trades: List[Trade]):
        self.known_trades[wallet] = trades

    def find_rotation(
        self,
        candidate_wallet: str,
        candidate_trades: List[Trade],
        candidate_funding_source: Optional[str],
    ) -> Optional[RotationLink]:
        """
        Checks candidate_wallet against all known good wallets.
        Returns the best RotationLink if confidence meets threshold, else None.
        """
        best_link: Optional[RotationLink] = None
        best_confidence = 0.0

        for known_wallet, known_score in self.known.items():
            if known_wallet == candidate_wallet:
                continue

            known_trades = self.known_trades.get(known_wallet, [])
            if not known_trades:
                continue

            confidence, signals = self._compare(
                candidate_trades=candidate_trades,
                candidate_funding=candidate_funding_source,
                known_trades=known_trades,
                known_wallet=known_wallet,
            )

            if confidence > best_confidence:
                best_confidence = confidence
                if confidence >= settings.rotation_similarity_threshold:
                    best_link = RotationLink(
                        old_wallet=known_wallet,
                        new_wallet=candidate_wallet,
                        confidence=round(confidence, 3),
                        signals=signals,
                        detected_at=datetime.now(tz=timezone.utc),
                    )

        return best_link

    # ---- Comparison helpers ----

    def _compare(
        self,
        candidate_trades: List[Trade],
        candidate_funding: Optional[str],
        known_trades: List[Trade],
        known_wallet: str,
    ) -> Tuple[float, List[str]]:
        """Returns (confidence: 0-1, list_of_matched_signals)."""
        signals: List[str] = []
        scores: List[Tuple[float, float]] = []  # (score, weight)

        # --- Signal 1: Common funding source (weight 0.35) ---
        known_funding = self._infer_funding(known_trades)
        if candidate_funding and known_funding:
            if candidate_funding.lower() == known_funding.lower():
                signals.append(f"Same funding source: {candidate_funding[:10]}...")
                scores.append((1.0, 0.35))
            else:
                scores.append((0.0, 0.35))
        # If we can't determine, don't penalise — just skip this signal

        # --- Signal 2: Bet sizing similarity (weight 0.25) ---
        size_sim = self._size_similarity(candidate_trades, known_trades)
        if size_sim > 0.6:
            signals.append(f"Similar bet sizing (similarity={size_sim:.2f})")
        scores.append((size_sim, 0.25))

        # --- Signal 3: Market selection overlap (weight 0.25) ---
        market_sim = self._market_overlap(candidate_trades, known_trades)
        if market_sim > 0.3:
            signals.append(f"Market selection overlap ({market_sim:.0%})")
        scores.append((market_sim, 0.25))

        # --- Signal 4: Activity timing correlation (weight 0.15) ---
        timing_sim = self._timing_similarity(candidate_trades, known_trades)
        if timing_sim > 0.5:
            signals.append(f"Activity timing correlation ({timing_sim:.2f})")
        scores.append((timing_sim, 0.15))

        if not scores:
            return 0.0, []

        total_weight = sum(w for _, w in scores)
        weighted_score = sum(s * w for s, w in scores) / total_weight if total_weight > 0 else 0.0

        return weighted_score, signals

    def _infer_funding(self, trades: List[Trade]) -> Optional[str]:
        """Placeholder — in production this would call fetcher.get_wallet_funding_source."""
        # The fetcher stores funding sources externally; we return None here
        # and the scanner injects the known funding source when available.
        return None

    def _size_similarity(self, a_trades: List[Trade], b_trades: List[Trade]) -> float:
        """
        Compares the distribution of trade sizes between two wallets using
        bucket histogram similarity (cosine similarity on log-binned buckets).
        """
        def size_histogram(trades: List[Trade]) -> List[float]:
            buckets = [0] * 8  # log bins: <$5, $5-10, $10-25, $25-50, $50-100, $100-250, $250-500, >$500
            bounds = [5, 10, 25, 50, 100, 250, 500]
            for t in trades:
                s = t.size_usdc
                idx = next((i for i, b in enumerate(bounds) if s < b), 7)
                buckets[idx] += 1
            total = sum(buckets) or 1
            return [b / total for b in buckets]

        ha = size_histogram(a_trades)
        hb = size_histogram(b_trades)
        return self._cosine_sim(ha, hb)

    def _market_overlap(self, a_trades: List[Trade], b_trades: List[Trade]) -> float:
        """Jaccard similarity of market IDs traded."""
        a_markets = set(t.market_id for t in a_trades)
        b_markets = set(t.market_id for t in b_trades)
        if not a_markets or not b_markets:
            return 0.0
        intersection = len(a_markets & b_markets)
        union = len(a_markets | b_markets)
        return intersection / union if union > 0 else 0.0

    def _timing_similarity(self, a_trades: List[Trade], b_trades: List[Trade]) -> float:
        """
        Compares hour-of-day activity profiles.
        Two wallets that consistently trade at 2am UTC are more likely linked.
        """
        def hour_profile(trades: List[Trade]) -> List[float]:
            counts = Counter(t.timestamp.hour for t in trades)
            total = sum(counts.values()) or 1
            return [counts.get(h, 0) / total for h in range(24)]

        ha = hour_profile(a_trades)
        hb = hour_profile(b_trades)
        return self._cosine_sim(ha, hb)

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
