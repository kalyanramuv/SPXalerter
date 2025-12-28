"""Main RSI alerting engine."""
import time
from typing import Dict, List
from datetime import datetime
from providers.base import MarketDataProvider, Bar
from providers.tradier import TradierProvider
from providers.mock import MockProvider
from signals.detector import SignalDetector, Signal
from alerts.manager import AlertManager
from alerts.discord import DiscordNotifier
from api.main import broadcast_alert, update_market_data, update_historical_bars
from api.runtime_config import runtime_config
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
        # Always create the real provider - _get_provider() will handle mock mode switching
        if self.config.provider.value == "tradier":
            return TradierProvider(self.config.tradier)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
    
    def _get_provider(self) -> MarketDataProvider:
        """Get the appropriate provider (checks runtime config for mock mode)."""
        from api.runtime_config import runtime_config
        if runtime_config.use_mock_data:
            # Return mock provider if enabled
            if not hasattr(self, '_mock_provider'):
                self._mock_provider = MockProvider(symbol=self.config.symbol, base_price=500.0)
                print("Using MOCK data provider (simulation mode)")
            return self._mock_provider
        # Use real provider
        return self.provider
    
    def _update_bars(self, timeframe: str) -> bool:
        """
        Update bars for a timeframe.
        
        Args:
            timeframe: Timeframe to update
            
        Returns:
            True if bars were updated successfully
        """
        try:
            # Get the appropriate provider (checks for mock mode)
            provider = self._get_provider()
            
            # Get historical bars (enough for RSI calculation and historical analysis)
            # Use runtime config value (has default 2000)
            from api.runtime_config import runtime_config
            bars_count = runtime_config.historical_bars_count
            bars = provider.get_historical_bars(
                self.config.symbol,
                timeframe,
                count=bars_count
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
        # Check runtime config (can be changed via web UI)
        from api.runtime_config import runtime_config
        if runtime_config.bypass_market_hours:
            return True
        
        # If bypass is enabled in config, always return True (for testing)
        if self.config.bypass_market_hours:
            return True
        
        # Get the appropriate provider (handles mock mode)
        provider = self._get_provider()
        
        # Simple check - could be enhanced with timezone handling
        # For now, rely on provider's is_market_open()
        try:
            return provider.is_market_open()
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
        
        # Collect RSI values and current price for charting
        rsi_by_timeframe = {}
        current_price = None
        
        # Debug: Print RSI values and price for each timeframe
        # Also calculate and store RSI history for all bars
        for timeframe in self.config.timeframes.timeframes:
            bars = self.bars_cache.get(timeframe, [])
            if bars:
                # Get latest RSI for alerts
                rsi_value = self.detector.rsi.get_latest(bars)
                if current_price is None:
                    current_price = bars[-1].close if bars else None
                if rsi_value is not None:
                    rsi_by_timeframe[timeframe] = rsi_value
                
                # Calculate RSI for all bars and store history
                # For 1min timeframe, use bar index directly
                if timeframe == "1min":
                    rsi_values = self.detector.rsi.calculate(bars)
                    # Clear and rebuild history for this timeframe
                    runtime_config.clear_rsi_history(timeframe)
                    for i, rsi_val in enumerate(rsi_values):
                        if rsi_val is not None and i < len(bars):
                            runtime_config.add_rsi_point(timeframe, bars[i].timestamp, rsi_val, i)
                else:
                    # For other timeframes (5min, 30min), map to 1min bar indices
                    # RSI is calculated using the closing price of each bar, so RSI[i] represents
                    # the RSI value at the END of bar[i] (i.e., at bar[i].timestamp)
                    # We need to map this to the corresponding 1min bar index
                    if "1min" in self.bars_cache and self.bars_cache["1min"]:
                        rsi_values = self.detector.rsi.calculate(bars)
                        # Clear and rebuild history for this timeframe
                        runtime_config.clear_rsi_history(timeframe)
                        min_bars = self.bars_cache["1min"]
                        
                        # Create a timestamp-to-index map for fast exact lookup
                        min_bar_map = {}
                        for j, min_bar in enumerate(min_bars):
                            # Use timestamp as key (normalize to second precision for matching)
                            timestamp_key = min_bar.timestamp.replace(microsecond=0)
                            if timestamp_key not in min_bar_map:
                                min_bar_map[timestamp_key] = j
                        
                        # Map each RSI value to the 1min bar index with matching timestamp
                        for i, rsi_val in enumerate(rsi_values):
                            if rsi_val is not None and i < len(bars):
                                bar_time = bars[i].timestamp
                                # Normalize to second precision
                                bar_time_key = bar_time.replace(microsecond=0)
                                
                                # Try exact match first
                                if bar_time_key in min_bar_map:
                                    target_index = min_bar_map[bar_time_key]
                                else:
                                    # Find the latest 1min bar with timestamp <= bar_time
                                    target_index = 0
                                    for j, min_bar in enumerate(min_bars):
                                        if min_bar.timestamp <= bar_time:
                                            target_index = j
                                        else:
                                            # We've passed the timestamp, previous index is closest
                                            break
                                runtime_config.add_rsi_point(timeframe, bar_time, rsi_val, target_index)
                if rsi_value is not None and current_price is not None:
                    print(f"[{timeframe}] Bars: {len(bars)}, Price: ${current_price:.2f}, RSI: {rsi_value:.2f}")
                elif rsi_value is not None:
                    print(f"[{timeframe}] Bars: {len(bars)}, RSI: {rsi_value:.2f}")
                else:
                    print(f"[{timeframe}] Bars: {len(bars)}, RSI: Not enough data")
            else:
                print(f"[{timeframe}] No bars available")
        
        # Update market data for charting (use first available timeframe's price)
        if current_price is not None and rsi_by_timeframe:
            update_market_data(datetime.now(), current_price, rsi_by_timeframe)
        
        # Update historical bars for all timeframes (for candlestick chart)
        for timeframe in self.config.timeframes.timeframes:
            if timeframe in self.bars_cache and self.bars_cache[timeframe]:
                update_historical_bars(timeframe, self.bars_cache[timeframe])
        
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
        from api.runtime_config import runtime_config
        initial_interval = runtime_config.get_polling_interval(self.config.polling_interval_seconds)
        
        print(f"Starting RSI Alerter for {self.config.symbol}")
        print(f"Timeframes: {', '.join(self.config.timeframes.timeframes)}")
        print(f"Polling interval: {initial_interval}s (configurable via web UI)")
        print("-" * 50)
        
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                print("\nStopping engine...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
            
            # Use runtime config polling interval if set, otherwise use config value
            interval = runtime_config.get_polling_interval(self.config.polling_interval_seconds)
            time.sleep(interval)

