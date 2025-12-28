"""Main RSI alerting engine."""
import time
from typing import Dict, List
from datetime import datetime
from providers.base import MarketDataProvider, Bar
from providers.tradier import TradierProvider
from signals.detector import SignalDetector, Signal
from alerts.manager import AlertManager
from alerts.discord import DiscordNotifier
from api.main import broadcast_alert
from config import AppConfig


class RSIEngine:
    """Main RSI alerting engine."""
    
    def __init__(self, config: AppConfig):
        """
        Initialize RSI engine.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.provider = self._create_provider()
        self.detector = SignalDetector(config.rsi, config.timeframes.timeframes, config.symbol)
        self.alert_manager = AlertManager(config.alerts)
        self.discord = DiscordNotifier(config.alerts.discord) if config.alerts.discord else None
        self.bars_cache: Dict[str, List[Bar]] = {
            tf: [] for tf in config.timeframes.timeframes
        }
    
    def _create_provider(self) -> MarketDataProvider:
        """Create market data provider based on config."""
        if self.config.provider.value == "tradier":
            return TradierProvider(self.config.tradier)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
    
    def _update_bars(self, timeframe: str) -> bool:
        """
        Update bars for a timeframe.
        
        Args:
            timeframe: Timeframe to update
            
        Returns:
            True if bars were updated successfully
        """
        try:
            # Get historical bars (enough for RSI calculation and historical analysis)
            bars = self.provider.get_historical_bars(
                self.config.symbol,
                timeframe,
                count=self.config.historical_bars_count
            )
            
            if bars:
                self.bars_cache[timeframe] = bars
                print(f"Updated {len(bars)} bars for {timeframe}")
                return True
            else:
                print(f"No bars returned for {timeframe}")
        except Exception as e:
            print(f"Error updating bars for {timeframe}: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def _update_all_timeframes(self):
        """Update bars for all timeframes."""
        for timeframe in self.config.timeframes.timeframes:
            self._update_bars(timeframe)
    
    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours."""
        # If bypass is enabled, always return True (for testing)
        if self.config.bypass_market_hours:
            return True
        
        # Simple check - could be enhanced with timezone handling
        # For now, rely on provider's is_market_open()
        try:
            return self.provider.is_market_open()
        except:
            # Fallback: assume market is open if check fails
            return True
    
    def run_once(self):
        """Run one iteration of the alerting loop."""
        # Check if market is open
        if not self._is_market_hours():
            print("Market is closed, skipping...")
            return
        
        # Update bars for all timeframes
        self._update_all_timeframes()
        
        # Debug: Print RSI values and price for each timeframe
        for timeframe in self.config.timeframes.timeframes:
            bars = self.bars_cache.get(timeframe, [])
            if bars:
                rsi_value = self.detector.rsi.get_latest(bars)
                current_price = bars[-1].close if bars else None
                if rsi_value is not None and current_price is not None:
                    print(f"[{timeframe}] Bars: {len(bars)}, Price: ${current_price:.2f}, RSI: {rsi_value:.2f}")
                elif rsi_value is not None:
                    print(f"[{timeframe}] Bars: {len(bars)}, RSI: {rsi_value:.2f}")
                else:
                    print(f"[{timeframe}] Bars: {len(bars)}, RSI: Not enough data")
            else:
                print(f"[{timeframe}] No bars available")
        
        # Detect signals
        signals = self.detector.detect_signals(self.bars_cache)
        
        # Process signals and send alerts
        for signal in signals:
            if self.alert_manager.should_send_alert(signal):
                message = self.alert_manager.get_alert_message(signal)
                
                # Send to dashboard
                broadcast_alert(signal, message)
                
                # Send to Discord if enabled
                if self.discord:
                    self.discord.send_alert(message)
                
                # Record alert
                self.alert_manager.record_alert(signal)
                
                print(f"Alert sent: {message}")
    
    def run(self):
        """Run the alerting engine continuously."""
        print(f"Starting RSI Alerter for {self.config.symbol}")
        print(f"Timeframes: {', '.join(self.config.timeframes.timeframes)}")
        print(f"Polling interval: {self.config.polling_interval_seconds}s")
        print("-" * 50)
        
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                print("\nStopping engine...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
            
            time.sleep(self.config.polling_interval_seconds)

