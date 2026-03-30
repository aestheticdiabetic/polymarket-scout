"""
Scanner — the main orchestration loop.
Runs on a schedule (default: every 60 minutes) and:
  1. Fetches active wallets
  2. Scores each one
  3. Runs rotation detection
  4. Fires alerts for new candidates
  5. Persists results to a local JSON store
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config import settings
from models.wallet import ScanResult, WalletScore, RotationLink
from services.fetcher import PolymarketFetcher
from services.scorer import ScoringEngine
from services.rotation_detector import RotationDetector
from services.alerter import maybe_alert, reset_alert_dedup

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data"
CANDIDATES_FILE = DATA_PATH / "candidates.json"
ROTATIONS_FILE = DATA_PATH / "rotations.json"
SCAN_LOG_FILE = DATA_PATH / "scan_log.json"
BLACKLIST_FILE = DATA_PATH / "blacklist.json"

DATA_PATH.mkdir(exist_ok=True)

# In-memory cache (also persisted to disk)
_candidates: Dict[str, WalletScore] = {}
_rotations: List[RotationLink] = []
_scan_log: List[ScanResult] = []
_current_weights: dict = {}
_blacklist: set = set()  # wallets permanently excluded from scanning

# Tracks when each wallet was last fully scored — prevents re-scoring on every cycle
_last_scored_at: Dict[str, datetime] = {}
RESCORE_HOURS = 24  # re-score existing candidates at most once per day


# Load persisted data on import
def _load_from_disk():
    global _candidates, _rotations, _scan_log, _blacklist
    try:
        if CANDIDATES_FILE.exists():
            raw = json.loads(CANDIDATES_FILE.read_text())
            _candidates = {k: WalletScore(**v) for k, v in raw.items()}
            log.info(f"Loaded {len(_candidates)} candidates from disk")
    except Exception as e:
        log.warning(f"Could not load candidates: {e}")

    try:
        if ROTATIONS_FILE.exists():
            raw = json.loads(ROTATIONS_FILE.read_text())
            _rotations = [RotationLink(**r) for r in raw]
    except Exception as e:
        log.warning(f"Could not load rotations: {e}")

    try:
        if SCAN_LOG_FILE.exists():
            raw = json.loads(SCAN_LOG_FILE.read_text())
            _scan_log = [ScanResult(**r) for r in raw]
    except Exception as e:
        log.warning(f"Could not load scan log: {e}")

    try:
        if BLACKLIST_FILE.exists():
            _blacklist = set(json.loads(BLACKLIST_FILE.read_text()))
            log.info(f"Loaded {len(_blacklist)} blacklisted wallets from disk")
    except Exception as e:
        log.warning(f"Could not load blacklist: {e}")


def _save_to_disk():
    try:
        CANDIDATES_FILE.write_text(
            json.dumps({k: v.model_dump(mode="json") for k, v in _candidates.items()}, indent=2)
        )
        ROTATIONS_FILE.write_text(
            json.dumps([r.model_dump(mode="json") for r in _rotations], indent=2)
        )
        SCAN_LOG_FILE.write_text(
            json.dumps([s.model_dump(mode="json") for s in _scan_log[-50:]], indent=2)  # keep last 50
        )
        BLACKLIST_FILE.write_text(json.dumps(sorted(_blacklist), indent=2))
    except Exception as e:
        log.error(f"Failed to save data: {e}")


def get_candidates() -> List[WalletScore]:
    return sorted(_candidates.values(), key=lambda s: s.composite_score, reverse=True)


def remove_candidate(wallet: str) -> bool:
    """Remove a wallet from candidates and add to blacklist. Returns True if it existed."""
    wallet = wallet.lower()
    if wallet not in _candidates:
        return False
    del _candidates[wallet]
    _last_scored_at.pop(wallet, None)
    _blacklist.add(wallet)
    _save_to_disk()
    log.info(f"Blacklisted {wallet}")
    return True


def set_note(wallet: str, note: Optional[str]) -> bool:
    """Set or clear the note on a candidate. Returns True if wallet exists."""
    wallet = wallet.lower()
    if wallet not in _candidates:
        return False
    _candidates[wallet] = _candidates[wallet].model_copy(update={"note": note or None})
    _save_to_disk()
    return True


def set_viability(wallet: str, viability: str, reasons: list) -> bool:
    """Update copy_trade_viability and viability_reasons on a candidate."""
    wallet = wallet.lower()
    if wallet not in _candidates:
        return False
    _candidates[wallet] = _candidates[wallet].model_copy(update={
        "copy_trade_viability": viability,
        "viability_reasons": reasons,
    })
    _save_to_disk()
    return True


def set_review_pending(wallet: str) -> bool:
    """Mark a wallet as having a review in progress. Returns True if wallet exists."""
    wallet = wallet.lower()
    if wallet not in _candidates:
        return False
    _candidates[wallet] = _candidates[wallet].model_copy(update={"ai_review_pending": True})
    _save_to_disk()
    return True


def set_review(wallet: str, review: Optional[dict], error: Optional[str] = None) -> bool:
    """Save a completed AI review on a candidate. Returns True if wallet exists."""
    wallet = wallet.lower()
    if wallet not in _candidates:
        return False
    _candidates[wallet] = _candidates[wallet].model_copy(update={
        "ai_review": review,
        "ai_review_at": datetime.now(tz=timezone.utc) if review else None,
        "ai_review_pending": False,
        "ai_review_error": error,
    })
    _save_to_disk()
    return True


def get_blacklist() -> List[str]:
    return sorted(_blacklist)


def remove_from_blacklist(wallet: str) -> bool:
    """Un-blacklist a wallet so it can be discovered again. Returns True if it was blacklisted."""
    wallet = wallet.lower()
    if wallet not in _blacklist:
        return False
    _blacklist.discard(wallet)
    _save_to_disk()
    log.info(f"Removed {wallet} from blacklist")
    return True


def get_rotations() -> List[RotationLink]:
    return _rotations


def get_scan_log() -> List[ScanResult]:
    return _scan_log


async def rescore_all_candidates() -> dict:
    """
    Re-fetch and re-score every existing candidate using the current scoring logic.
    Evicts wallets that no longer pass filters (stale data, fixed bugs, etc.).
    Runs up to 10 wallets concurrently. Returns a summary dict.
    """
    wallets = list(_candidates.keys())
    if not wallets:
        return {"rescored": 0, "evicted": 0, "kept": 0}

    log.info(f"Rescoring {len(wallets)} existing candidates (parallel, max 10 concurrent)...")
    fetcher = PolymarketFetcher()
    scorer = ScoringEngine(weights=_current_weights)
    market_price_cache: Dict[str, float] = {}
    market_resolution_cache: Dict[str, dict] = {}
    sem = asyncio.Semaphore(10)
    counters = {"evicted": 0, "kept": 0}

    async def _rescore_one(wallet: str):
        async with sem:
            try:
                trades, username = await fetcher._activity_trades(wallet)
                trades = sorted(trades, key=lambda t: t.timestamp)
                if not trades:
                    _candidates.pop(wallet, None)
                    counters["evicted"] += 1
                    return

                unique_markets = [
                    mid for mid in {t.market_id for t in trades if t.market_id != "unknown"}
                    if mid not in market_price_cache
                ]
                if unique_markets:
                    price_results = await asyncio.gather(
                        *[fetcher.get_market_open_price(mid, "YES") for mid in unique_markets],
                        return_exceptions=True,
                    )
                    for mid, pr in zip(unique_markets, price_results):
                        if isinstance(pr, float):
                            market_price_cache[mid] = pr

                unique_for_res = [
                    mid for mid in {t.market_id for t in trades if t.market_id != "unknown"}
                    if mid not in market_resolution_cache
                ]
                if unique_for_res:
                    res_results = await asyncio.gather(
                        *[fetcher.get_market_resolution_data(mid) for mid in unique_for_res],
                        return_exceptions=True,
                    )
                    for mid, res in zip(unique_for_res, res_results):
                        if isinstance(res, dict):
                            market_resolution_cache[mid] = res

                enriched = _enrich_trades(trades, market_resolution_cache)
                score = scorer.score(wallet, enriched, market_open_prices=market_price_cache)

                if score is None or not scorer.passes_filters(score):
                    log.info(f"Evicting {wallet[:10]}... — fails updated scoring")
                    _candidates.pop(wallet, None)
                    _last_scored_at.pop(wallet, None)
                    counters["evicted"] += 1
                    return

                # Preserve user-added fields
                existing = _candidates.get(wallet)
                if existing:
                    score = score.model_copy(update={
                        "note": existing.note,
                        "ai_review": existing.ai_review,
                        "ai_review_at": existing.ai_review_at,
                        "ai_review_pending": existing.ai_review_pending,
                        "username": score.username or existing.username,
                        "is_new": existing.is_new,
                        "discovered_at": existing.discovered_at,
                    })
                _candidates[wallet] = score
                _last_scored_at[wallet] = datetime.now(tz=timezone.utc)
                counters["kept"] += 1

            except Exception as e:
                log.warning(f"Rescore failed for {wallet[:10]}...: {e}")

    try:
        await asyncio.gather(*[_rescore_one(w) for w in wallets])
    finally:
        await fetcher.close()
        _save_to_disk()

    log.info(f"Rescore complete: {counters['kept']} kept, {counters['evicted']} evicted")
    return {"rescored": len(wallets), "evicted": counters["evicted"], "kept": counters["kept"]}


def set_weights(weights: dict):
    global _current_weights
    _current_weights = weights
    log.info(f"Scoring weights updated: {weights}")


def _enrich_trades(trades: List, resolution_cache: Dict[str, dict]) -> List:
    """
    Returns a new list of trades with resolved/won fields populated using the
    resolution cache (built from CLOB /markets/{conditionId} responses).

    A trade is considered:
      resolved=True  if the market is closed
      won=True       if the market is closed AND the outcome the wallet bet on won
      won=False      if the market is closed AND the outcome the wallet bet on lost
      won=None       if the market is not yet resolved
    """
    enriched = []
    for t in trades:
        res = resolution_cache.get(t.market_id)
        if res and res.get("closed"):
            outcome_winners = res.get("outcome_winners", {})
            # Match the trade outcome (e.g. "Yes"/"No") to the CLOB token outcome name.
            # The activity API returns mixed case ("Yes", "No", "Down", etc.);
            # try exact match first, then case-insensitive fallback.
            won: Optional[bool] = None
            for clob_outcome, is_winner in outcome_winners.items():
                if clob_outcome == t.outcome or clob_outcome.lower() == t.outcome.lower():
                    won = is_winner
                    break
            enriched.append(t.model_copy(update={"resolved": True, "won": won}))
        else:
            enriched.append(t)
    return enriched


async def run_scan() -> ScanResult:
    """Full scan cycle."""
    scan_id = str(uuid.uuid4())[:8]
    result = ScanResult(scan_id=scan_id, started_at=datetime.now(tz=timezone.utc))
    _scan_log.append(result)
    reset_alert_dedup()

    log.info(f"[{scan_id}] Starting scan...")

    fetcher = PolymarketFetcher()
    scorer = ScoringEngine(weights=_current_weights)
    detector = RotationDetector(known_scores=list(_candidates.values()))

    try:
        wallets = await fetcher.get_active_wallets(limit=300)
        result.wallets_scanned = len(wallets)
        log.info(f"[{scan_id}] Scanning {len(wallets)} wallets...")

        new_count = 0
        rotation_count = 0
        skipped_count = 0
        now = datetime.now(tz=timezone.utc)
        rescore_cutoff = now - timedelta(hours=RESCORE_HOURS)

        # Cache market open prices and resolution data across wallets in this scan
        market_price_cache: Dict[str, float] = {}
        market_resolution_cache: Dict[str, dict] = {}  # conditionId → {closed, outcome_winners}

        for wallet in wallets:
            try:
                # Skip permanently blacklisted wallets
                if wallet in _blacklist:
                    skipped_count += 1
                    continue

                # Skip existing candidates that were scored recently — avoid re-fetching
                # the same 300 wallets every cycle. New wallets are always processed.
                if wallet in _candidates and wallet in _last_scored_at:
                    if _last_scored_at[wallet] > rescore_cutoff:
                        skipped_count += 1
                        continue

                trades, username = await fetcher._activity_trades(wallet)
                trades = sorted(trades, key=lambda t: t.timestamp)
                if not trades:
                    continue

                # Fetch opening prices and resolution data for unseen markets this scan
                unique_markets = [
                    mid for mid in {t.market_id for t in trades if t.market_id != "unknown"}
                    if mid not in market_price_cache
                ]
                if unique_markets:
                    price_results = await asyncio.gather(
                        *[fetcher.get_market_open_price(mid, "YES") for mid in unique_markets],
                        return_exceptions=True,
                    )
                    for mid, pr in zip(unique_markets, price_results):
                        if isinstance(pr, float):
                            market_price_cache[mid] = pr

                # Fetch resolution data (closed + winner) for unseen markets this scan
                unique_markets_for_resolution = [
                    mid for mid in {t.market_id for t in trades if t.market_id != "unknown"}
                    if mid not in market_resolution_cache
                ]
                if unique_markets_for_resolution:
                    res_results = await asyncio.gather(
                        *[fetcher.get_market_resolution_data(mid) for mid in unique_markets_for_resolution],
                        return_exceptions=True,
                    )
                    for mid, res in zip(unique_markets_for_resolution, res_results):
                        if isinstance(res, dict):
                            market_resolution_cache[mid] = res

                # Enrich trades with resolved/won using the resolution cache
                enriched_trades = _enrich_trades(trades, market_resolution_cache)

                score = scorer.score(wallet, enriched_trades, market_open_prices=market_price_cache)
                if score is not None and username:
                    score = score.model_copy(update={"username": username})
                if score is None:
                    continue

                if not scorer.passes_filters(score):
                    _last_scored_at[wallet] = now
                    # Evict from candidates if it was previously accepted but no longer passes
                    if wallet in _candidates:
                        del _candidates[wallet]
                        log.info(f"[{scan_id}] Evicted {wallet[:10]}... — no longer passes filters")
                    continue

                # Rotation detection
                funding_source = await fetcher.get_wallet_funding_source(wallet)
                detector.register_trades(wallet, trades)
                link = detector.find_rotation(
                    candidate_wallet=wallet,
                    candidate_trades=trades,
                    candidate_funding_source=funding_source,
                )

                if link:
                    score.linked_from = link.old_wallet
                    score.rotation_confidence = link.confidence
                    score.rotation_signals = link.signals
                    _rotations.append(link)
                    rotation_count += 1
                    log.info(f"[{scan_id}] Rotation detected: {link.old_wallet[:8]}... → {wallet[:8]}... (conf={link.confidence:.0%})")

                # Mark as new if we haven't seen this wallet before
                is_new = wallet not in _candidates
                score.is_new = is_new

                # Preserve user-added fields from the existing candidate
                if wallet in _candidates:
                    existing = _candidates[wallet]
                    score = score.model_copy(update={
                        "note": existing.note,
                        "ai_review": existing.ai_review,
                        "ai_review_at": existing.ai_review_at,
                        "ai_review_pending": existing.ai_review_pending,
                        # Keep existing username if the fresh fetch returned nothing
                        "username": score.username or existing.username,
                    })

                _candidates[wallet] = score
                _last_scored_at[wallet] = now

                if is_new:
                    new_count += 1
                    await maybe_alert(score)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning(f"[{scan_id}] Error processing {wallet[:10]}...: {e}")
                result.errors.append(f"{wallet[:10]}: {e}")

        result.new_candidates = new_count
        result.rotation_links_found = rotation_count

        # Backfill usernames for candidates that still have none (e.g. loaded from disk
        # before username tracking was added, or not in the current active pool).
        no_username = [w for w, s in _candidates.items() if not s.username]
        if no_username:
            log.info(f"[{scan_id}] Backfilling usernames for {len(no_username)} candidates (up to 100)...")
            backfilled = 0
            for wallet in no_username[:100]:
                try:
                    _, username = await fetcher._activity_trades(wallet, limit=1)
                    if username and wallet in _candidates:
                        _candidates[wallet] = _candidates[wallet].model_copy(update={"username": username})
                        backfilled += 1
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.debug(f"[{scan_id}] Username backfill failed for {wallet[:10]}: {e}")
            log.info(f"[{scan_id}] Username backfill: {backfilled}/{min(len(no_username), 100)} filled")

        result.completed_at = datetime.now(tz=timezone.utc)

        log.info(
            f"[{scan_id}] Done. {new_count} new candidates, "
            f"{rotation_count} rotation links, "
            f"{skipped_count} skipped (recently scored or blacklisted), "
            f"{len(result.errors)} errors"
        )

    except Exception as e:
        log.error(f"[{scan_id}] Scan failed: {e}")
        result.errors.append(str(e))
        result.completed_at = datetime.now(tz=timezone.utc)
    finally:
        await fetcher.close()
        _save_to_disk()

    return result


_load_from_disk()
