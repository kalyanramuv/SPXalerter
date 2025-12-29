"""Historical data playback provider for testing with real market data."""
import json
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
from .base import MarketDataProvider, Bar


class HistoricalPlaybackProvider(MarketDataProvider):
    """
    Provider that plays back historical market data to simulate real-time updates.
    
    Loads historical data from JSON files and feeds it progressively to simulate
    real-time market data for testing alert generation.
    """
    
    def __init__(self, symbol: str, data_dir: str = "historical_data"):
        """
        Initialize historical playback provider.
        
        Args:
            symbol: Trading symbol (e.g., "SPY")
            data_dir: Directory containing historical data files
        """
        self.symbol = symbol
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Store loaded historical data by timeframe
        self.historical_data: Dict[str, List[Bar]] = {}
        
        # Current time position (datetime) for time-aligned playback
        self.current_time: Optional[datetime] = None
        
        # Track which timeframes have been called this cycle (to advance time only once)
        self._cycle_called_timeframes: set = set()
        
        # Load historical data for all timeframes
        self._load_historical_data()
        
        # Initialize current_time to earliest timestamp across all timeframes
        self._initialize_current_time()
    
    def _load_historical_data(self):
        """Load historical data from JSON files."""
        for timeframe in ["1min", "5min", "30min"]:
            data_file = self.data_dir / f"{self.symbol}_{timeframe}.json"
            
            if not data_file.exists():
                print(f"Warning: Historical data file not found: {data_file}")
                print(f"  Expected format: JSON array of bars with timestamp, open, high, low, close, volume")
                continue
            
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                bars = []
                for bar_data in data:
                    # Parse timestamp (handle ISO format strings)
                    if isinstance(bar_data.get('timestamp'), str):
                        timestamp = datetime.fromisoformat(bar_data['timestamp'].replace('Z', '+00:00'))
                        # Remove timezone info for simplicity (keep naive datetime)
                        if timestamp.tzinfo:
                            timestamp = timestamp.replace(tzinfo=None)
                    else:
                        timestamp = datetime.now()
                    
                    bars.append(Bar(
                        timestamp=timestamp,
                        open=float(bar_data['open']),
                        high=float(bar_data['high']),
                        low=float(bar_data['low']),
                        close=float(bar_data['close']),
                        volume=int(bar_data.get('volume', 0))
                    ))
                
                # Sort by timestamp (oldest first)
                bars.sort(key=lambda x: x.timestamp)
                self.historical_data[timeframe] = bars
                
                print(f"Loaded {len(bars)} historical bars for {timeframe} from {data_file}")
                
            except Exception as e:
                print(f"Error loading historical data from {data_file}: {e}")
                self.historical_data[timeframe] = []
    
    def _initialize_current_time(self):
        """Initialize current_time to ensure all timeframes have enough bars for RSI calculation."""
        if not self.historical_data:
            return
        
        min_bars_needed = 15  # RSI period is 14, need at least 15 bars
        
        # Find the latest timestamp needed to ensure all timeframes have at least min_bars_needed bars
        # This ensures we start from a point where all timeframes can calculate RSI
        required_times = []
        
        for timeframe, bars in self.historical_data.items():
            if len(bars) >= min_bars_needed:
                # Get timestamp of the Nth bar (where N = min_bars_needed) - enough for RSI calculation
                # This is the timestamp we need to reach to have N bars
                required_time = bars[min_bars_needed - 1].timestamp
                required_times.append(required_time)
        
        if required_times:
            # Start from the LATEST required time to ensure ALL timeframes have enough data
            # This means we might start with more than min_bars_needed for some timeframes, which is fine
            self.current_time = max(required_times)
            
            # Debug: Show how many bars each timeframe has at initialization
            bars_at_init = {}
            for tf, tf_bars in self.historical_data.items():
                bars_at_init[tf] = len([b for b in tf_bars if b.timestamp <= self.current_time])
            
            print(f"Playback initialized at: {self.current_time}")
            print(f"  Bars at initialization: {bars_at_init}")
        else:
            # Fallback: use earliest timestamp from any timeframe
            all_times = []
            for bars in self.historical_data.values():
                if bars:
                    all_times.append(bars[0].timestamp)
            if all_times:
                self.current_time = max(all_times)
                print(f"Playback initialized at: {self.current_time} (using fallback)")
    
    def get_historical_bars(
        self,
        symbol: str,
        interval: str,
        count: int = 100
    ) -> List[Bar]:
        """
        Get historical bars up to the current playback time (time-aligned across all timeframes).
        Advances time by 1 minute each call to simulate real-time updates.
        
        Args:
            symbol: Trading symbol
            interval: Time interval (e.g., "1min", "5min", "30min")
            count: Minimum number of bars to return (ensures enough for RSI calculation)
            
        Returns:
            List of Bar objects up to the current playback time
        """
        if interval not in self.historical_data or self.current_time is None:
            return []
        
        bars = self.historical_data[interval]
        
        # Filter bars up to current_time (inclusive)
        result = [bar for bar in bars if bar.timestamp <= self.current_time]
        
        # Ensure we have at least enough bars for RSI calculation
        min_bars_needed = 15  # RSI period is 14, need at least 15 bars
        if len(result) < min_bars_needed:
            # If we don't have enough bars yet, return empty (will get more on next call)
            return []
        
        # Advance time only once per cycle (on first call, typically "1min")
        # Use the first timeframe as the trigger for time advancement
        should_advance = False
        if not self._cycle_called_timeframes:
            # This is the first call of the cycle, advance time
            should_advance = True
        
        self._cycle_called_timeframes.add(interval)
        
        # If all timeframes have been called this cycle, reset for next cycle
        if len(self._cycle_called_timeframes) >= len(self.historical_data):
            self._cycle_called_timeframes.clear()
        
        if should_advance:
            # Advance time by 1 minute to simulate real-time progression
            from datetime import timedelta
            self.current_time += timedelta(minutes=1)
            
            # Check if we've reached the end of all data
            max_time = None
            for tf_bars in self.historical_data.values():
                if tf_bars:
                    tf_max_time = tf_bars[-1].timestamp
                    if max_time is None or tf_max_time > max_time:
                        max_time = tf_max_time
            
            # If we've passed the end, loop back to beginning
            if max_time and self.current_time > max_time:
                print(f"Reached end of historical data, looping back to start")
                self._initialize_current_time()
                self._cycle_called_timeframes.clear()
        
        return result
    
    def get_latest_bar(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Bar]:
        """
        Get the latest bar up to the current playback time.
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            
        Returns:
            Latest Bar up to current time, or None if not available
        """
        if interval not in self.historical_data or self.current_time is None:
            return None
        
        bars = self.historical_data[interval]
        
        # Find the latest bar up to current_time
        latest_bar = None
        for bar in bars:
            if bar.timestamp <= self.current_time:
                latest_bar = bar
            else:
                break
        
        return latest_bar
    
    def reset_playback(self):
        """Reset playback time to beginning."""
        self._initialize_current_time()
        print("Reset playback time to beginning")
    
    def set_playback_time(self, target_time: datetime):
        """
        Set playback time to a specific datetime.
        
        Args:
            target_time: Target datetime to set playback to
        """
        # Find the earliest timestamp across all timeframes
        earliest_times = []
        for bars in self.historical_data.values():
            if bars:
                earliest_times.append(bars[0].timestamp)
        
        if earliest_times:
            min_time = max(earliest_times)  # Latest of earliest (ensures all have data)
            max_time = min(bars[-1].timestamp for bars in self.historical_data.values() if bars)
            
            # Clamp target_time to valid range
            if target_time < min_time:
                self.current_time = min_time
            elif target_time > max_time:
                self.current_time = max_time
            else:
                self.current_time = target_time
            
            print(f"Set playback time to {self.current_time}")
    
    def is_market_open(self) -> bool:
        """
        Always return True for playback mode (allows continuous playback).
        
        Returns:
            True (market is always "open" during playback)
        """
        return True

