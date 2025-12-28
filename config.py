"""Configuration management for RSI Live Alerter."""
import os
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class MarketDataProvider(str, Enum):
    """Supported market data providers."""
    TRADIER = "tradier"
    SCHWAB = "schwab"


@dataclass
class RSIConfig:
    """RSI indicator configuration."""
    period: int = 14
    oversold_threshold: int = 30
    overbought_threshold: int = 70
    bullish_reclaim_upper: int = 35
    bearish_reclaim_lower: int = 65


@dataclass
class TimeframeConfig:
    """Timeframe configuration."""
    timeframes: list[str] = None  # e.g., ["1min", "5min", "30min"]
    
    def __post_init__(self):
        if self.timeframes is None:
            self.timeframes = ["1min", "5min", "30min"]


@dataclass
class TradierConfig:
    """Tradier API configuration."""
    api_key: str = ""
    account_id: str = ""
    base_url: str = "https://sandbox.tradier.com/v1"  # Default to sandbox for safety


@dataclass
class DiscordConfig:
    """Discord webhook configuration."""
    webhook_url: Optional[str] = None
    enabled: bool = False


@dataclass
class AlertConfig:
    """Alert system configuration."""
    cooldown_seconds: int = 300  # 5 minutes default cooldown
    enable_discord: bool = False
    discord: Optional[DiscordConfig] = None


@dataclass
class MarketHoursConfig:
    """Market hours configuration."""
    start_time: str = "09:30"  # ET
    end_time: str = "16:00"    # ET
    timezone: str = "America/New_York"


@dataclass
class AppConfig:
    """Main application configuration."""
    symbol: str = "SPY"
    provider: MarketDataProvider = MarketDataProvider.TRADIER
    polling_interval_seconds: int = 20
    bypass_market_hours: bool = False  # Allow testing outside market hours
    historical_bars_count: int = 2000  # Number of historical bars to fetch
    rsi: RSIConfig = None
    timeframes: TimeframeConfig = None
    tradier: TradierConfig = None
    alerts: AlertConfig = None
    market_hours: MarketHoursConfig = None
    
    def __post_init__(self):
        if self.rsi is None:
            self.rsi = RSIConfig()
        if self.timeframes is None:
            self.timeframes = TimeframeConfig()
        if self.tradier is None:
            self.tradier = TradierConfig()
        if self.alerts is None:
            self.alerts = AlertConfig()
        if self.market_hours is None:
            self.market_hours = MarketHoursConfig()

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        config = cls()
        
        # Tradier config
        config.tradier.api_key = os.getenv("TRADIER_API_KEY", "")
        config.tradier.account_id = os.getenv("TRADIER_ACCOUNT_ID", "")
        # Allow users to specify base URL (sandbox or production)
        config.tradier.base_url = os.getenv(
            "TRADIER_BASE_URL", 
            "https://sandbox.tradier.com/v1"  # Default to sandbox for safety
        )
        
        # Discord config
        discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
        if discord_webhook:
            config.alerts.enable_discord = True
            config.alerts.discord = DiscordConfig(
                webhook_url=discord_webhook,
                enabled=True
            )
        
        # Symbol
        config.symbol = os.getenv("SYMBOL", "SPY")
        
        # Polling interval
        polling = os.getenv("POLLING_INTERVAL_SECONDS", "20")
        try:
            config.polling_interval_seconds = int(polling)
        except ValueError:
            pass
        
        # Cooldown
        cooldown = os.getenv("ALERT_COOLDOWN_SECONDS", "300")
        try:
            config.alerts.cooldown_seconds = int(cooldown)
        except ValueError:
            pass
        
        # Bypass market hours (for testing)
        config.bypass_market_hours = os.getenv("BYPASS_MARKET_HOURS", "false").lower() == "true"
        
        # Historical bars count
        bars_count = os.getenv("HISTORICAL_BARS_COUNT", "2000")
        try:
            config.historical_bars_count = int(bars_count)
        except ValueError:
            pass  # Keep default if invalid
        
        # Timeframes (comma-separated, e.g., "1min,5min,30min")
        timeframes_str = os.getenv("TIMEFRAMES", "")
        if timeframes_str:
            config.timeframes.timeframes = [tf.strip() for tf in timeframes_str.split(",") if tf.strip()]
        
        return config



