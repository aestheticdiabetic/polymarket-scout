"""
Alert engine.
Sends browser push notifications when the dashboard is open,
falls back to Telegram (and optionally email) when it isn't.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from config import settings
from models.wallet import Alert, WalletScore

log = logging.getLogger(__name__)

# In-memory store of pending browser alerts
# The dashboard polls GET /alerts/pending and clears them on ACK
_pending_browser_alerts: List[Alert] = []
_sent_alert_ids: set[str] = set()


async def maybe_alert(score: WalletScore) -> Optional[Alert]:
    """
    Called by the scanner whenever a wallet crosses the threshold.
    Deduplicates, then routes to the right channel.
    """
    # Deduplicate — don't re-alert the same wallet within a scan cycle
    if score.wallet in _sent_alert_ids:
        return None

    reason = _build_reason(score)
    alert = Alert(
        id=str(uuid.uuid4()),
        wallet=score.wallet,
        composite_score=score.composite_score,
        reason=reason,
        triggered_at=datetime.now(tz=timezone.utc),
    )

    # Always queue for browser
    _pending_browser_alerts.append(alert)
    alert.sent_browser = True
    _sent_alert_ids.add(score.wallet)

    # Also fire Telegram if configured
    if settings.telegram_bot_token and settings.telegram_chat_id:
        sent = await _send_telegram(alert)
        alert.sent_telegram = sent

    return alert


def get_pending_browser_alerts() -> List[Alert]:
    return list(_pending_browser_alerts)


def ack_alert(alert_id: str) -> bool:
    global _pending_browser_alerts
    before = len(_pending_browser_alerts)
    _pending_browser_alerts = [a for a in _pending_browser_alerts if a.id != alert_id]
    return len(_pending_browser_alerts) < before


def reset_alert_dedup():
    """Called at the start of each scan cycle so wallets can be re-alerted next cycle."""
    _sent_alert_ids.clear()


async def _send_telegram(alert: Alert) -> bool:
    rotation_note = ""
    if alert.reason and "rotated" in alert.reason.lower():
        rotation_note = "\n⚠️ *Possible wallet rotation detected*"

    message = (
        f"🎯 *New Polymarket Copy-Trade Candidate*{rotation_note}\n\n"
        f"Wallet: `{alert.wallet}`\n"
        f"Score: *{alert.composite_score:.1f}/100*\n"
        f"Reason: {alert.reason}\n\n"
        f"_Triggered at {alert.triggered_at.strftime('%Y-%m-%d %H:%M UTC')}_"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )
            r.raise_for_status()
            log.info(f"Telegram alert sent for {alert.wallet}")
            return True
    except Exception as e:
        log.warning(f"Telegram alert failed: {e}")
        return False


def _build_reason(score: WalletScore) -> str:
    parts = []
    parts.append(f"Win rate {score.win_rate:.0%}")
    parts.append(f"ROI {score.roi:+.0%}")
    # Conviction quality — the key signal for the conviction-exponent copy model
    delta = score.conviction_win_rate_delta
    delta_str = f"+{delta:.0%}" if delta >= 0 else f"{delta:.0%}"
    parts.append(f"Big-bet edge {delta_str} (high bets win {score.conviction_win_rate:.0%} vs {score.win_rate:.0%} overall)")
    parts.append(f"Exit cleanliness {score.exit_cleanliness:.0%}")
    parts.append(f"Avg bet ${score.avg_bet_size_usdc:.0f}")
    if score.rotation_confidence > 0:
        parts.append(f"Rotated from {score.linked_from[:8]}... (conf={score.rotation_confidence:.0%})")
    return " | ".join(parts)
