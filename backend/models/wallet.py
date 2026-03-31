from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"


class Trade(BaseModel):
    tx_hash: str
    wallet: str
    market_id: str
    market_question: str
    outcome: str  # "YES" or "NO"
    direction: TradeDirection
    size_usdc: float
    price: float          # price at time of trade (0-1)
    timestamp: datetime
    market_final_price: Optional[float] = None   # filled when market resolves
    resolved: bool = False
    won: Optional[bool] = None


class WalletScore(BaseModel):
    wallet: str
    username: Optional[str] = None       # Polymarket display name or pseudonym
    alias: Optional[str] = None          # set if we detect a linked older wallet
    linked_from: Optional[str] = None    # older wallet this was rotated from

    # Raw metrics
    total_trades: int
    resolved_trades: int
    won_trades: int
    win_rate: float
    total_invested_usdc: float
    total_returned_usdc: float
    roi: float
    distinct_markets: int
    avg_entry_price: float               # avg price when they entered (lower = earlier entry)
    avg_market_open_price: float         # avg opening odds of markets they traded
    early_entry_score: float             # how much before odds shifted they entered
    avg_bet_size_usdc: float = 0.0       # mean buy size — scale vs your copy balance
    bet_size_cv: float = 0.0             # coefficient of variation on buy sizes (std/mean); higher = more variable conviction signals
    conviction_win_rate: float = 0.0     # win rate specifically on above-average bets
    conviction_win_rate_delta: float = 0.0  # conviction_win_rate minus overall win_rate (positive = big bets win more)
    exit_cleanliness: float = 0.0        # fraction of market exits completed in a single sell tx (1.0 = always clean)
    tradeable_rate: float = 0.0          # fraction of buy trades with price <= copier entry ceiling (0.80)

    # Computed composite
    composite_score: float               # 0-100
    arb_flag: bool = False               # True if we suspect arb behaviour
    arb_reason: Optional[str] = None

    # Rotation detection
    rotation_confidence: float = 0.0    # 0-1 confidence that this is a rotated wallet
    rotation_signals: List[str] = []    # which signals matched

    # lb-api verified P&L (source of truth — same numbers Polymarket shows on profiles)
    pnl_all: Optional[float] = None      # lifetime P&L in USD
    pnl_30d: Optional[float] = None      # last 30-day P&L in USD
    pnl_7d: Optional[float] = None       # last 7-day P&L in USD

    # Copy-trade viability pre-screen
    copy_trade_viability: str = "VIABLE"   # VIABLE | SUSPECT | LIKELY_BOT
    viability_reasons: List[str] = []

    # Recent win rate (resolved markets in last ~30 days)
    win_rate_7d: Optional[float] = None   # wins / resolved in recent window
    wins_7d: Optional[int] = None         # markets won recently
    losses_7d: Optional[int] = None       # markets lost recently

    # User note
    note: Optional[str] = None

    # AI review
    ai_review: Optional[dict] = None     # Structured report from Claude
    ai_review_at: Optional[datetime] = None  # When the review was generated
    ai_review_pending: bool = False      # True while review is being generated
    ai_review_error: Optional[str] = None   # Error message if review failed

    # Meta
    first_trade_at: datetime
    last_trade_at: datetime
    discovered_at: datetime
    is_new: bool = False                 # True if discovered in last scan


class RotationLink(BaseModel):
    old_wallet: str
    new_wallet: str
    confidence: float
    signals: List[str]
    detected_at: datetime


class Alert(BaseModel):
    id: str
    wallet: str
    composite_score: float
    reason: str
    triggered_at: datetime
    sent_telegram: bool = False
    sent_browser: bool = False


class ScanResult(BaseModel):
    scan_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    wallets_scanned: int = 0
    new_candidates: int = 0
    rotation_links_found: int = 0
    errors: List[str] = []


class ScoreWeights(BaseModel):
    """Sent from the dashboard config panel to update scoring on the fly."""
    min_trades: int = 20
    min_win_rate: float = 0.60
    min_roi: float = 0.40
    min_markets: int = 3
    min_exit_cleanliness: float = 0.25
    max_avg_entry_price: float = 0.85
    min_tradeable_rate: float = 0.50
    early_entry_weight: float = 0.15
    win_rate_weight: float = 0.20
    roi_weight: float = 0.05
    consistency_weight: float = 0.00
    conviction_quality_weight: float = 0.25
    exit_cleanliness_weight: float = 0.20
    bet_size_cv_weight: float = 0.15
    arb_max_hold_seconds: int = 300
    rotation_similarity_threshold: float = 0.70
