from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from typing import List, Optional
from pydantic import BaseModel
from models.wallet import WalletScore, RotationLink, Alert, ScanResult, ScoreWeights
from services import scanner, alerter
from services.ai_reviewer import generate_review

router = APIRouter()


# ---- Candidates ----

@router.get("/candidates", response_model=List[WalletScore])
async def list_candidates(
    min_score: float = 0,
    arb_only: bool = False,
    rotated_only: bool = False,
    limit: int = 100,
):
    candidates = scanner.get_candidates()
    if min_score > 0:
        candidates = [c for c in candidates if c.composite_score >= min_score]
    if arb_only:
        candidates = [c for c in candidates if c.arb_flag]
    if rotated_only:
        candidates = [c for c in candidates if c.rotation_confidence > 0]
    return candidates[:limit]


@router.get("/candidates/{wallet}", response_model=WalletScore)
async def get_candidate(wallet: str):
    candidates = {c.wallet: c for c in scanner.get_candidates()}
    if wallet not in candidates:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return candidates[wallet]


@router.delete("/candidates/{wallet}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(wallet: str):
    """Remove a candidate and add it to the blacklist so it is never surfaced again."""
    if not scanner.remove_candidate(wallet):
        raise HTTPException(status_code=404, detail="Wallet not found")


class NoteBody(BaseModel):
    note: Optional[str] = None


@router.patch("/candidates/{wallet}/note", response_model=WalletScore)
async def set_note(wallet: str, body: NoteBody):
    """Set or clear a note on a candidate wallet."""
    if not scanner.set_note(wallet, body.note):
        raise HTTPException(status_code=404, detail="Wallet not found")
    candidates = {c.wallet: c for c in scanner.get_candidates()}
    return candidates[wallet.lower()]


# ---- AI Review ----

async def _run_review(wallet: str, score: WalletScore):
    """Background task: generate review and persist it."""
    try:
        review = await generate_review(score)
        if review is None:
            scanner.set_review(wallet, None, error="AI review returned no result — check backend logs")
        else:
            scanner.set_review(wallet, review)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"AI review background task failed for {wallet[:10]}...: {e}")
        scanner.set_review(wallet, None, error=str(e))


@router.post("/candidates/{wallet}/review", response_model=WalletScore)
async def trigger_review(wallet: str, background_tasks: BackgroundTasks):
    """Trigger an AI deep-dive review of a wallet. Runs in the background; poll
    GET /candidates/{wallet} until ai_review_pending is False and ai_review is set."""
    candidates = {c.wallet: c for c in scanner.get_candidates()}
    if wallet not in candidates:
        raise HTTPException(status_code=404, detail="Wallet not found")

    from config import settings
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    score = candidates[wallet]
    # Don't re-run if already pending
    if score.ai_review_pending:
        return score

    scanner.set_review_pending(wallet)
    updated = {c.wallet: c for c in scanner.get_candidates()}[wallet]
    background_tasks.add_task(_run_review, wallet, score)
    return updated


# ---- Blacklist ----

@router.get("/blacklist", response_model=List[str])
async def list_blacklist():
    return scanner.get_blacklist()


@router.delete("/blacklist/{wallet}", status_code=status.HTTP_204_NO_CONTENT)
async def unblacklist(wallet: str):
    """Remove a wallet from the blacklist so it can be discovered again."""
    if not scanner.remove_from_blacklist(wallet):
        raise HTTPException(status_code=404, detail="Wallet not in blacklist")


# ---- Rotation links ----

@router.get("/rotations", response_model=List[RotationLink])
async def list_rotations():
    return scanner.get_rotations()


# ---- Alerts ----

@router.get("/alerts/pending", response_model=List[Alert])
async def pending_alerts():
    return alerter.get_pending_browser_alerts()


@router.post("/alerts/ack/{alert_id}")
async def ack_alert(alert_id: str):
    ok = alerter.ack_alert(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acked"}


# ---- Scan ----

@router.post("/scan", response_model=ScanResult)
async def trigger_scan(background_tasks: BackgroundTasks):
    """Manually trigger a scan. Runs in background, returns immediately."""
    background_tasks.add_task(scanner.run_scan)
    return ScanResult(
        scan_id="manual",
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        wallets_scanned=0,
    )


@router.get("/scan/log", response_model=List[ScanResult])
async def scan_log():
    return scanner.get_scan_log()


# ---- Rescore all (full re-fetch + re-score, evicts stale candidates) ----

@router.post("/rescore-all")
async def rescore_all(background_tasks: BackgroundTasks):
    """Re-fetch and re-score every existing candidate with current logic.
    Evicts wallets that no longer pass filters. Runs in background."""
    background_tasks.add_task(scanner.rescore_all_candidates)
    return {"status": "started", "message": "Rescore running in background — poll /candidates to see results"}


# ---- Rescore viability ----

@router.post("/rescore-viability")
async def rescore_viability():
    """Re-run the copy-trade viability check on all existing candidates using
    stored fields only (no API calls). Returns a summary of what changed."""
    from config import settings as cfg
    from collections import defaultdict

    candidates = scanner.get_candidates()
    updated = 0
    summary: dict = defaultdict(int)

    for score in candidates:
        bot_reasons = []
        suspect_reasons = []

        # 1. Micro-sizing
        if score.total_trades >= cfg.viability_min_trades_for_size_check and score.total_trades > 0:
            approx_avg = score.total_invested_usdc / score.total_trades
            if approx_avg < cfg.viability_max_avg_trade_usdc:
                bot_reasons.append(
                    f"Approx avg trade size ${approx_avg:.2f} "
                    f"(threshold ${cfg.viability_max_avg_trade_usdc:.0f})"
                )

        # 2. Both-sides proxy — arb detector already caught YES+NO patterns
        if score.arb_flag and score.arb_reason and "YES and NO" in score.arb_reason:
            bot_reasons.append("Both YES and NO positions detected (from arb scan)")

        # 3. Trades per market
        if score.distinct_markets > 0:
            tpm = score.total_trades / score.distinct_markets
            if tpm > cfg.viability_max_trades_per_market:
                bot_reasons.append(
                    f"{tpm:.0f} trades/market "
                    f"(threshold {cfg.viability_max_trades_per_market:.0f})"
                )

        # 4. Implausible win rate
        if (
            score.total_trades >= cfg.viability_min_trades_for_win_rate_check
            and score.resolved_trades <= cfg.viability_max_resolved_for_win_rate_check
            and score.win_rate >= cfg.viability_suspicious_win_rate
        ):
            suspect_reasons.append(
                f"{score.win_rate:.0%} win rate on {score.resolved_trades} resolved trades"
            )

        # 5. Extreme ROI
        if score.roi > cfg.viability_max_roi:
            suspect_reasons.append(f"ROI {score.roi:.0%} exceeds {cfg.viability_max_roi:.0%} threshold")

        if bot_reasons:
            viability, reasons = "LIKELY_BOT", bot_reasons + suspect_reasons
        elif suspect_reasons:
            viability, reasons = "SUSPECT", suspect_reasons
        else:
            viability, reasons = "VIABLE", []

        if viability != score.copy_trade_viability or reasons != score.viability_reasons:
            scanner.set_viability(score.wallet, viability, reasons)
            updated += 1

        summary[viability] += 1

    return {
        "rescored": len(candidates),
        "updated": updated,
        "viable": summary["VIABLE"],
        "suspect": summary["SUSPECT"],
        "likely_bot": summary["LIKELY_BOT"],
    }


# ---- Config / weights ----

@router.get("/config", response_model=ScoreWeights)
async def get_config():
    from config import settings
    return ScoreWeights(
        min_trades=settings.min_trades,
        min_win_rate=settings.min_win_rate,
        min_roi=settings.min_roi,
        min_markets=settings.min_markets,
        min_exit_cleanliness=settings.min_exit_cleanliness,
        early_entry_weight=settings.early_entry_weight,
        win_rate_weight=settings.win_rate_weight,
        roi_weight=settings.roi_weight,
        consistency_weight=settings.consistency_weight,
        conviction_quality_weight=settings.conviction_quality_weight,
        exit_cleanliness_weight=settings.exit_cleanliness_weight,
        arb_max_hold_seconds=settings.arb_max_hold_seconds,
        rotation_similarity_threshold=settings.rotation_similarity_threshold,
    )


@router.post("/config", response_model=ScoreWeights)
async def update_config(weights: ScoreWeights):
    """Update scoring weights at runtime — no restart needed."""
    scanner.set_weights(weights.model_dump())
    return weights


# ---- Health ----

@router.get("/health")
async def health():
    return {"status": "ok"}
