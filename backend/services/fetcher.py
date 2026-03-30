"""
Fetches trade data from the Polymarket public data API.
  1. data-api.polymarket.com/trades  — recent platform-wide fills (no auth needed)
  2. data-api.polymarket.com/activity — per-wallet trade history (no auth needed)
  3. lb-api.polymarket.com/profit     — leaderboard for top-performer discovery
  4. CLOB prices-history              — opening prices for early-entry scoring
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import httpx
from web3 import AsyncWeb3, AsyncHTTPProvider

from config import settings
from models.wallet import Trade, TradeDirection

log = logging.getLogger(__name__)

_SHORT_TERM_SLUG_PATTERNS = (
    "-updown-",       # BTC/ETH up-or-down markets
    "-above-",        # "bitcoin-above-62k-on-march-27" style daily crypto price markets
    "-below-",        # inverse of the above
    "btc-price-",     # other BTC price variants
    "eth-price-",
    "crypto-price-",
)


def _is_short_term_crypto(fill: dict) -> bool:
    """Returns True for short-term automated crypto price markets (e.g. BTC/ETH up-or-down)."""
    slug = fill.get("slug", "")
    return any(p in slug for p in _SHORT_TERM_SLUG_PATTERNS)


class PolymarketFetcher:
    def __init__(self):
        self.clob = settings.polymarket_clob_api
        self.gamma = settings.polymarket_gamma_api
        self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.polygon_rpc_url))
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    # -------------------------------------------------------------------------
    # Public helpers
    # -------------------------------------------------------------------------

    async def get_active_wallets(self, limit: int = 500) -> List[str]:
        """
        Returns wallets to scan from two sources:
          1. Recent platform-wide trades via the public data API (no auth)
          2. lb-api 7-day leaderboard — catches wallets on a current hot streak
             before they become widely followed
        """
        client = await self._http()
        wallets: set[str] = set()
        offset = 0
        batch = 500

        while len(wallets) < limit:
            try:
                r = await client.get(
                    "https://data-api.polymarket.com/trades",
                    params={"limit": batch, "offset": offset},
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log.warning(f"Data API trades fetch error: {e}")
                break

            if not data:
                break

            for fill in data:
                if fill.get("proxyWallet") and not _is_short_term_crypto(fill):
                    wallets.add(fill["proxyWallet"].lower())

            if len(data) < batch:
                break
            offset += batch

        # Supplement with top 7-day performers only.
        # All-time and 30d leaderboards are too well-known — bots with lower latency
        # already track those wallets. The 7d window catches wallets on a current hot
        # streak before they become widely followed.
        try:
            r = await client.get(
                "https://lb-api.polymarket.com/profit",
                params={"window": "7d", "limit": 100},
            )
            if r.status_code == 200:
                for entry in (r.json() or []):
                    pw = entry.get("proxyWallet", "").lower()
                    if pw:
                        wallets.add(pw)
        except Exception as e:
            log.warning(f"lb-api leaderboard fetch error: {e}")

        return list(wallets)[:limit]

    async def get_wallet_trades(self, wallet: str, limit: int = 2000) -> List[Trade]:
        """Fetch trade history for a single wallet from the public data API."""
        trades, _ = await self._activity_trades(wallet, limit=limit)
        return sorted(trades, key=lambda t: t.timestamp)

    async def get_wallet_username(self, wallet: str) -> Optional[str]:
        """
        Fetch the display name for a wallet from the first activity item.
        Uses 'name' if it's a real username (not a 0x address), else 'pseudonym'.
        """
        _, username = await self._activity_trades(wallet, limit=1)
        return username

    async def get_market_open_price(self, market_id: str, outcome: str) -> Optional[float]:
        """
        Returns the opening price of a market outcome from the CLOB price history.
        Used to score early entry.
        """
        client = await self._http()
        try:
            r = await client.get(
                f"{self.clob}/prices-history",
                params={"market": market_id, "startTs": 0, "interval": "1h", "fidelity": 60},
            )
            r.raise_for_status()
            data = r.json()
            history = data.get("history", [])
            if history:
                return float(history[0].get("p", 0.5))
        except Exception as e:
            log.debug(f"Price history fetch failed for {market_id}: {e}")
        return None

    async def get_market_resolution_data(self, condition_id: str) -> Optional[dict]:
        """
        Returns resolution data for a market from the CLOB /markets/{condition_id} endpoint.

        Returns a dict:
          {
            "closed": bool,                   # True if market has resolved
            "outcome_winners": {str: bool},   # e.g. {"Yes": True, "No": False}
          }
        Returns None if the market cannot be looked up.
        """
        client = await self._http()
        try:
            r = await client.get(f"{self.clob}/markets/{condition_id}", timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            closed = bool(data.get("closed", False))
            tokens = data.get("tokens", [])
            # tokens: [{"token_id": ..., "outcome": "Yes", "price": 1, "winner": true}, ...]
            outcome_winners: dict[str, bool] = {}
            for token in tokens:
                outcome_name = token.get("outcome", "")
                winner = bool(token.get("winner", False))
                if outcome_name:
                    outcome_winners[outcome_name] = winner
            return {"closed": closed, "outcome_winners": outcome_winners}
        except Exception as e:
            log.debug(f"Market resolution fetch failed for {condition_id}: {e}")
        return None

    async def get_wallet_funding_source(self, wallet: str) -> Optional[str]:
        """
        Traces the first funding transaction for a wallet on Polygon.
        Returns the sending address (the 'parent' or funding source).
        Used for rotation detection.
        """
        try:
            client = await self._http()
            query = """
            {
              transfers(
                where: { to: "%s" }
                orderBy: timestamp
                orderDirection: asc
                first: 1
              ) {
                from
                timestamp
                value
              }
            }
            """ % wallet.lower()

            r = await client.post(
                "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-polygon",
                json={"query": query},
                timeout=10,
            )
            data = r.json()
            transfers = data.get("data", {}).get("transfers", [])
            if transfers:
                return transfers[0]["from"].lower()
        except Exception as e:
            log.debug(f"Funding source lookup failed for {wallet}: {e}")
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -------------------------------------------------------------------------
    # Private: data API queries
    # -------------------------------------------------------------------------

    async def _activity_trades(self, wallet: str, limit: int = 2000):
        """
        Fetch trade history for a wallet from the public Polymarket data API.
        Uses data-api.polymarket.com/activity which works for any wallet without auth.
        Paginates up to `limit` trades (default 2000 for scanner; 10000 for AI reviews).
        Returns (List[Trade], Optional[str]) — trades and the wallet's display name.
        """
        client = await self._http()
        trades: List[Trade] = []
        username: Optional[str] = None
        offset = 0
        batch = 500

        while len(trades) < limit:
            try:
                r = await client.get(
                    "https://data-api.polymarket.com/activity",
                    params={"user": wallet, "limit": batch, "offset": offset},
                    timeout=20,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log.debug(f"Activity fetch for {wallet}: {e}")
                break

            if not data:
                break

            # Extract username from first item — 'name' is user-chosen,
            # 'pseudonym' is always a readable auto-generated fallback.
            # A real name won't start with '0x' (that's Polymarket's placeholder).
            if username is None and data:
                first = data[0]
                raw_name = first.get("name", "")
                pseudonym = first.get("pseudonym", "")
                username = raw_name if raw_name and not raw_name.startswith("0x") else pseudonym or None

            for fill in data:
                # Skip short-term crypto price markets
                if _is_short_term_crypto(fill):
                    continue
                # Only count actual trades, not redemptions
                if fill.get("type") not in ("TRADE", None):
                    continue
                try:
                    t = Trade(
                        tx_hash=fill.get("transactionHash", "unknown"),
                        wallet=wallet,
                        market_id=fill.get("conditionId", "unknown"),
                        market_question=fill.get("title", "Unknown"),
                        outcome=fill.get("outcome", "YES"),
                        direction=TradeDirection.BUY if fill.get("side", "BUY") == "BUY" else TradeDirection.SELL,
                        size_usdc=float(fill.get("usdcSize", fill.get("size", 0))),
                        price=float(fill.get("price", 0.5)),
                        timestamp=datetime.fromtimestamp(
                            int(fill.get("timestamp", 0)), tz=timezone.utc
                        ),
                    )
                    trades.append(t)
                except Exception as e:
                    log.debug(f"Parse error on activity fill: {e}")

            if len(data) < batch:
                break
            offset += batch

        return trades, username
