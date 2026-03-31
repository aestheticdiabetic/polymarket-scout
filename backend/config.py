from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # RPC / API keys
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com", description="Your Alchemy/Infura/QuickNode Polygon RPC URL")
    dune_api_key: Optional[str] = Field(default=None, description="Dune Analytics API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key for AI wallet reviews")
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram bot token for alerts")
    telegram_chat_id: Optional[str] = Field(default=None, description="Telegram chat ID for alerts")

    # Polymarket endpoints
    polymarket_clob_api: str = "https://clob.polymarket.com"
    polymarket_gamma_api: str = "https://gamma-api.polymarket.com"
    polymarket_subgraph: str = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-3"

    # Scoring defaults (all configurable via the dashboard)
    min_trades: int = Field(default=20, description="Minimum trades before a wallet is evaluated")
    min_win_rate: float = Field(default=0.60, description="Minimum win rate (0-1)")
    min_roi: float = Field(default=0.40, description="Minimum ROI (e.g. 0.40 = 40%)")
    min_markets: int = Field(default=3, description="Minimum distinct markets traded")
    min_exit_cleanliness: float = Field(default=0.25, description="Minimum fraction of markets exited in a single sell tx (0-1).")
    max_avg_entry_price: float = Field(default=0.85, description="Maximum average entry price — excludes wallets who primarily trade heavy favourites above the copier's entry ceiling")
    min_tradeable_rate: float = Field(default=0.50, description="Minimum fraction of buy trades with price <= copier_max_entry_price (0.80). Ensures enough trades will actually be copied.")
    copier_max_entry_price: float = Field(default=0.80, description="Copier entry price ceiling — used to compute tradeable_rate. Mirrors REAL_MAX_ENTRY_PRICE in polymarket-copier.")
    early_entry_weight: float = Field(default=0.15, description="Weight given to early market entry signal")
    win_rate_weight: float = Field(default=0.20, description="Weight given to win rate")
    roi_weight: float = Field(default=0.05, description="Weight given to ROI")
    consistency_weight: float = Field(default=0.00, description="Weight given to market consistency (disabled — breadth is not a strong copier signal)")
    conviction_quality_weight: float = Field(default=0.25, description="Weight given to win rate specifically on above-average bets — the primary signal under a conviction-exponent copy model")
    exit_cleanliness_weight: float = Field(default=0.20, description="Weight given to clean single-transaction exits — wallets with messy drip-sells are harder to follow via chain monitoring")
    bet_size_cv_weight: float = Field(default=0.15, description="Weight given to bet size variation (std/mean). High CV means the wallet occasionally makes very large bets — the conviction exponent amplifies these most.")

    # Arbitrage detection thresholds
    arb_max_hold_seconds: int = Field(default=300, description="Trades held less than this (seconds) are flagged as potential arb")
    arb_max_position_ratio: float = Field(default=0.05, description="Positions < this % of market volume flagged as potential arb")

    # Rotation detection thresholds
    rotation_similarity_threshold: float = Field(default=0.70, description="Minimum pattern similarity score to link wallets (0-1)")
    rotation_lookback_days: int = Field(default=90, description="Days to look back when searching for rotated wallets")

    # Scheduler
    scan_interval_minutes: int = Field(default=60, description="How often to scan for new candidates")

    # Copy-trade viability pre-screening thresholds
    viability_max_avg_trade_usdc: float = Field(default=5.0, description="Avg trade size (USDC) below this with enough trades → LIKELY_BOT")
    viability_min_trades_for_size_check: int = Field(default=100, description="Min total trades before avg size check applies")
    viability_suspicious_win_rate: float = Field(default=0.95, description="Win rate above this on a small resolved sample → SUSPECT")
    viability_max_resolved_for_win_rate_check: int = Field(default=100, description="Max resolved trades for the suspicious win rate check to trigger")
    viability_min_trades_for_win_rate_check: int = Field(default=200, description="Min total trades for the suspicious win rate check to trigger")
    viability_max_roi: float = Field(default=5.0, description="ROI above this (e.g. 5.0 = 500%) → SUSPECT")
    viability_max_trades_per_market: float = Field(default=50.0, description="total_trades / distinct_markets above this → LIKELY_BOT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
