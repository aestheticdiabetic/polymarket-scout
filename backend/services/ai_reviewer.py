"""
AI Wallet Reviewer — generates a structured copy-trading suitability report
for a wallet using Claude. Fetches fresh trade data at review time so the
analysis is based on the most complete picture available.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from models.wallet import WalletScore
from services.fetcher import PolymarketFetcher

log = logging.getLogger(__name__)


def _build_prompt(score: WalletScore, trades: list, trades_summary: str) -> str:
    """Build the analysis prompt from wallet data."""
    TRADE_FETCH_LIMIT = 10000  # matches the limit passed to get_wallet_trades for AI reviews

    # Derive wallet age from the freshly-fetched trades list, not score.first_trade_at.
    # score.first_trade_at comes from the scanner's 2,000-trade window and is unreliable
    # for high-volume wallets. trades are sorted ascending so trades[0] is oldest fetched.
    now = datetime.now(tz=timezone.utc)

    def _tz(ts):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    wallet_age_line = "unknown"

    candidates = []
    if trades:
        candidates.append(_tz(trades[0].timestamp))
    if score.first_trade_at:
        candidates.append(_tz(score.first_trade_at))

    age_days = None
    age_warning = ""

    if candidates:
        first_ts = min(candidates)
        last_ts  = _tz(trades[-1].timestamp) if trades else first_ts
        fetched_span_days = (last_ts - first_ts).days
        age_days = (now.date() - first_ts.date()).days

        trades_per_day = len(trades) / max(fetched_span_days, 1)
        high_frequency = trades_per_day >= 200 or len(trades) >= 500

        if len(trades) >= TRADE_FETCH_LIMIT:
            wallet_age_line = (
                f"CANNOT DETERMINE — fetched {TRADE_FETCH_LIMIT:,} trades (hit the limit). "
                f"Those trades span only {fetched_span_days} day(s) of visible history. "
                f"This is an extremely high-frequency wallet; it is almost certainly months or years old. "
                f"DO NOT describe this wallet as new, young, or recently discovered."
            )
        else:
            wallet_age_line = (
                f"{age_days} calendar day(s) "
                f"(first activity: {first_ts.date()}, fetched {len(trades):,} trades)"
            )

        if age_days is not None and age_days <= 2 and high_frequency:
            age_warning = (
                f"\n\nCRITICAL INSTRUCTION — IGNORE WALLET AGE ENTIRELY IN YOUR ANALYSIS:\n"
                f"This wallet is {age_days} day(s) old with {len(trades):,} trades "
                f"(~{trades_per_day:.0f}/day). At that volume, wallet age is meaningless — "
                f"it cannot be used to infer discovery risk, bot tracking status, or anything else. "
                f"Do NOT mention wallet age anywhere in your response. "
                f"Do NOT list it as a green flag OR a red flag. "
                f"Do NOT reference it in wallet_age_risk, summary, or any other field. "
                f"Omit age entirely and focus on trading behaviour only."
            )

    pnl_section = ""
    if score.pnl_all is not None:
        pnl_section = f"""
Verified P&L (Polymarket source of truth):
  - Lifetime: ${score.pnl_all:,.0f}
  - Last 30d:  ${score.pnl_30d:,.0f}
  - Last 7d:   ${score.pnl_7d:,.0f}
"""

    arb_section = ""
    if score.arb_flag:
        arb_section = f"\nARBITRAGE FLAG: YES — {score.arb_reason}\n"
    else:
        arb_section = "\nARBITRAGE FLAG: NO\n"

    rotation_section = ""
    if score.rotation_confidence > 0:
        rotation_section = f"""
WALLET ROTATION DETECTED:
  - Confidence: {score.rotation_confidence:.0%}
  - Signals matched: {', '.join(score.rotation_signals)}
  - Linked from older wallet: {score.linked_from or 'unknown'}
"""

    # Conviction quality metrics
    conviction_section = ""
    if score.conviction_win_rate > 0:
        delta = score.conviction_win_rate_delta
        delta_str = f"+{delta:.1%}" if delta >= 0 else f"{delta:.1%}"
        conviction_section = (
            f"  Conviction win rate:  {score.conviction_win_rate:.1%} on above-avg bets "
            f"vs {score.win_rate:.1%} overall ({delta_str} edge) — "
            f"positive delta means large bets outperform, the primary signal my bot amplifies\n"
        )

    bet_size_cv_line = ""
    if score.bet_size_cv > 0:
        bet_size_cv_line = f"  Bet size variation: {score.bet_size_cv:.2f} CV (std/mean on buy sizes — higher means more variable conviction signals; >1.0 is high)\n"

    return f"""You are analysing a Polymarket prediction market trader for copy-trading suitability.

MY COPY BOT — HOW IT WORKS:
- Automated copy-trading bot on Polymarket. ~4 second execution delay from on-chain detection to order placement.
- Professional competing bots operate at ~0.2s. I cannot exploit arbitrage or any latency-sensitive strategy.
- CONVICTION-EXPONENT SIZING: My bot does NOT copy flat. Bets significantly above the wallet's average are copied with disproportionately larger size (exponent ~1.5). A bet 2x their average triggers ~2.8x my normal copy size. This means I benefit most from wallets who occasionally make very large bets relative to their norm — wallets with flat consistent sizing give me no amplification signal.
- ENTRY FILTER: In live mode I skip entries above 0.80 probability. Wallets who primarily trade heavy favourites (>80% implied probability) will have most of their trades skipped entirely.
- EXIT DETECTION: I track exits via on-chain chain monitoring. Clean exits (single sell transaction per market) are reliably detected. Wallets who drip-sell across multiple transactions per market are harder to follow cleanly.
- MULTI-TRANCHE ENTRIES: Multiple buys into the same market over time are handled correctly — staggered accumulation is fine and does not cause problems.
- I prefer wallets not yet widely tracked. Many bots copying the same wallet creates slippage that erodes profitability for all followers.

WALLET DATA:
  Address:            {score.wallet}
  Username:           {score.username or 'none'}
  Wallet age:         {wallet_age_line}
  Total trades:       {score.total_trades}
  Resolved trades:    {score.resolved_trades}
  Won trades:         {score.won_trades}
  Win rate:           {score.win_rate:.1%}
  Distinct markets:   {score.distinct_markets}
  Total invested:     ${score.total_invested_usdc:,.0f} USDC
  Total returned:     ${score.total_returned_usdc:,.0f} USDC
  ROI:                {score.roi:.1%}
  Avg entry price:    {score.avg_entry_price:.3f} (lower = earlier entry before consensus)
  Early entry score:  {score.early_entry_score:.4f} (higher = enters markets earlier)
  Avg buy size:       ${score.avg_bet_size_usdc:,.0f} USDC
{bet_size_cv_line}  Exit cleanliness:   {score.exit_cleanliness:.1%} of markets exited in a single sell tx (higher = easier to follow via chain monitor)
  Composite score:    {score.composite_score:.1f}/100
{conviction_section}{pnl_section}{arb_section}{rotation_section}{age_warning}
RECENT TRADE HISTORY (up to 50 most recent trades):
{trades_summary}

---

Produce a structured JSON analysis report with EXACTLY this format — no extra keys, no markdown, just raw JSON:

{{
  "summary": "<2-3 sentence plain-English overview of this trader>",
  "strategy": "<How they appear to select markets and structure their bets — position sizing patterns, timing, whether they show variable conviction or flat sizing>",
  "market_preferences": "<What categories of markets they favour — politics, crypto, sports, current events, etc. — based on the trade titles>",
  "arbitrage_assessment": "<Whether there are signs of arbitrage or automated trading that would make copy-trading useless. Be specific.>",
  "wallet_age_risk": "<Assessment of how long this wallet has existed and the risk that it is already widely tracked by other bots>",
  "copy_trading_viability": "<Direct assessment for THIS specific bot: (1) Does the wallet vary their bet size enough to generate strong conviction signals? (2) Are entry prices typically below 0.80 so trades won't be filtered? (3) Are exits clean enough for chain monitoring? (4) Is trade frequency low enough that a 4-second delay doesn't matter? Be specific with numbers.>",
  "red_flags": ["<specific red flag 1>", "<specific red flag 2>"],
  "green_flags": ["<specific positive signal 1>", "<specific positive signal 2>"],
  "recommendation": "STRONG BUY" | "BUY" | "WATCH" | "PASS" | "HARD PASS",
  "recommendation_reason": "<1-2 sentences explaining the recommendation>",
  "suitability_score": <integer 0-10 where 10 = perfect copy-trade candidate for this specific bot>
}}

Be direct and specific. Use numbers from the data. Do not pad with generic advice.
If red_flags or green_flags are empty, use an empty array [].
"""


def _format_trades(trades: list) -> str:
    """Summarise trades into a readable block for the prompt."""
    if not trades:
        return "No trade history available."

    # Take the 50 most recent trades (already sorted by timestamp ascending)
    recent = trades[-50:]
    lines = []
    for t in recent:
        direction = "BUY " if t.direction.value == "buy" else "SELL"
        won_str = ""
        if t.won is True:
            won_str = " [WON]"
        elif t.won is False:
            won_str = " [LOST]"
        lines.append(
            f"  {t.timestamp.strftime('%Y-%m-%d')} {direction} {t.outcome} "
            f"@ {t.price:.3f} · ${t.size_usdc:.0f} · {t.market_question[:60]}{won_str}"
        )
    return "\n".join(lines)


async def generate_review(score: WalletScore) -> Optional[dict]:
    """
    Fetch fresh trade data and generate a structured AI review of the wallet.
    Returns the review dict, or None if the Anthropic API key is not configured
    or the request fails.
    """
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY not set — skipping AI review")
        return None

    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed — run: pip install anthropic")
        return None

    fetcher = PolymarketFetcher()
    try:
        trades = await fetcher.get_wallet_trades(score.wallet, limit=10000)
    except Exception as e:
        log.warning(f"Failed to fetch trades for AI review ({score.wallet[:10]}...): {e}")
        trades = []
    finally:
        await fetcher.close()

    trades_summary = _format_trades(trades)
    prompt = _build_prompt(score, trades, trades_summary)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    # Strip markdown code fences if the model wraps in ```json ... ```
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    review = json.loads(raw)
    review["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    return review
