"""Tradier market data provider implementation."""
import requests
from typing import List, Optional
from datetime import datetime, timedelta
from .base import MarketDataProvider, Bar
from config import TradierConfig


class TradierProvider(MarketDataProvider):
    """Tradier API market data provider."""
    
    def __init__(self, config: TradierConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_key}",
            "Accept": "application/json"
        })
    
    def get_historical_bars(
        self,
        symbol: str,
        interval: str,
        count: int = 100
    ) -> List[Bar]:
        """Fetch historical bars from Tradier."""
        # For intraday intervals, use timesales endpoint
        if interval.endswith("min"):
            return self._get_timesales(symbol, interval, count)
        
        # For daily intervals, use history endpoint
        tradier_interval = self._map_interval(interval)
        start_date = datetime.now() - timedelta(days=30)
        
        url = f"{self.config.base_url}/markets/history"
        params = {
            "symbol": symbol,
            "interval": tradier_interval,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": datetime.now().strftime("%Y-%m-%d")
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            bars = []
            if "history" in data and "day" in data["history"]:
                for bar_data in data["history"]["day"][-count:]:
                    bars.append(self._parse_bar(bar_data, interval))
            
            return sorted(bars, key=lambda x: x.timestamp)
        except Exception as e:
            print(f"Error fetching historical bars: {e}")
            return []
    
    def _get_timesales(
        self,
        symbol: str,
        interval: str,
        count: int
    ) -> List[Bar]:
        """Fetch intraday timesales data from Tradier."""
        # Fetch from multiple days to get historical data
        # Calculate bars per trading day based on interval
        # Trading day: 6.5 hours (9:30 AM - 4:00 PM ET) = 390 minutes
        interval_minutes = int(interval.replace("min", ""))
        bars_per_trading_day = 390 // interval_minutes  # ~390 for 1min, ~78 for 5min, ~13 for 30min
        
        # Calculate trading days needed (add 50% buffer for weekends/holidays)
        trading_days_needed = (count // bars_per_trading_day) + 1
        # Convert to calendar days (7 calendar days per 5 trading days)
        # Add extra buffer for holidays and weekends
        max_days_back = int(trading_days_needed * 7 / 5 * 1.5)  # Extra buffer for holidays
        # Minimum 30 days, maximum 365 days (allow up to 1 year for large bar counts)
        # Note: Tradier API may have limits, but we'll try up to 365 days
        max_days_back = max(30, min(max_days_back, 365))
        
        print(f"Fetching {count} {interval} bars: need ~{trading_days_needed} trading days, checking up to {max_days_back} calendar days")
        
        all_bars = []
        trading_days_found = 0
        
        for days_back in range(max_days_back):
            target_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            url = f"{self.config.base_url}/markets/timesales"
            
            tradier_interval = self._map_interval(interval)
            params = {
                "symbol": symbol,
                "interval": tradier_interval,
                "start": f"{target_date} 09:30",
                "end": f"{target_date} 16:00",
                "session_filter": "all"
            }
            
            try:
                response = self.session.get(url, params=params, timeout=10)
                
                # Handle 400 Bad Request (invalid date/weekend/holiday) gracefully
                if response.status_code == 400:
                    # Invalid date - likely weekend, holiday, or future date
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                day_bars = []
                if "series" in data and data["series"] is not None and "data" in data["series"]:
                    timesales = data["series"]["data"]
                    
                    # Convert timesales to bars
                    if timesales:
                        for item in timesales:
                            day_bars.append(self._parse_timesale(item))
                
                if day_bars:
                    all_bars.extend(day_bars)
                    trading_days_found += 1
                    # Log progress every 10 trading days
                    if trading_days_found % 10 == 0:
                        print(f"Progress: {trading_days_found} trading days, {len(all_bars)} bars collected so far...")
                    # If we have enough bars, we can stop fetching
                    if len(all_bars) >= count:
                        print(f"Collected {len(all_bars)} bars (requested {count}), stopping early")
                        break
                # Note: No timesales data is expected for weekends/holidays, so we don't log it
                    
            except requests.exceptions.HTTPError as e:
                # For HTTP errors other than 400, log and continue
                print(f"HTTP error fetching timesales for {target_date}: {e.response.status_code}")
                continue
            except Exception as e:
                print(f"Error fetching timesales for {target_date}: {e}")
                continue
        
        if all_bars:
            # Sort by timestamp and return the most recent bars
            sorted_bars = sorted(all_bars, key=lambda x: x.timestamp)
            num_bars = min(count, len(sorted_bars))
            print(f"Total historical bars collected: {len(sorted_bars)} from {trading_days_found} trading days, returning last {num_bars}")
            
            # Warn if we didn't get enough bars
            if len(sorted_bars) < count:
                print(f"WARNING: Requested {count} bars but only collected {len(sorted_bars)} bars. "
                      f"This may be due to Tradier API historical data limits. "
                      f"Consider reducing the requested bar count or using a different data provider.")
            
            return sorted_bars[-count:]
        else:
            print(f"No historical bars found after checking {max_days_back} days")
        
        # If all timesales attempts failed, try history fallback
        print(f"No timesales data available, trying history endpoint...")
        return self._get_history_fallback(symbol, interval, count)
    
    def _get_history_fallback(
        self,
        symbol: str,
        interval: str,
        count: int
    ) -> List[Bar]:
        """Fallback method using history endpoint for intraday."""
        # Try to get recent trading days (go back up to 5 days to find a trading day)
        for days_back in range(1, 6):
            start_date = datetime.now() - timedelta(days=days_back)
            end_date = datetime.now() - timedelta(days=days_back-1) if days_back > 1 else datetime.now()
            
            url = f"{self.config.base_url}/markets/history"
            params = {
                "symbol": symbol,
                "interval": "1min",  # History endpoint uses 1min for intraday
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d")
            }
            
            try:
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                bars = []
                if "history" in data and "day" in data["history"]:
                    day_data = data["history"]["day"]
                    if isinstance(day_data, list) and len(day_data) > 0:
                        # For intraday, Tradier history might return daily bars
                        # We'll take the most recent day's data
                        latest_day = day_data[-1]
                        # If we have intraday data, it should be in a sub-structure
                        # Otherwise, create a single bar from daily data
                        if isinstance(latest_day, dict):
                            bars.append(self._parse_bar(latest_day, interval))
                
                if bars:
                    return sorted(bars, key=lambda x: x.timestamp)
            except Exception as e:
                continue
        
        print(f"History fallback also failed for {symbol}")
        return []
    
    def _parse_timesale(self, timesale_data: dict) -> Bar:
        """Parse Tradier timesale data to Bar object."""
        timestamp_str = timesale_data.get("time", "")
        try:
            # Tradier timesales format: "2024-01-01T10:30:00"
            timestamp = datetime.fromisoformat(timestamp_str)
        except:
            timestamp = datetime.now()
        
        return Bar(
            timestamp=timestamp,
            open=float(timesale_data.get("open", 0)),
            high=float(timesale_data.get("high", 0)),
            low=float(timesale_data.get("low", 0)),
            close=float(timesale_data.get("close", 0)),
            volume=int(timesale_data.get("volume", 0))
        )
    
    def get_latest_bar(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Bar]:
        """Get latest bar using quotes endpoint."""
        url = f"{self.config.base_url}/markets/quotes"
        params = {"symbols": symbol}
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if "quotes" in data and "quote" in data["quotes"]:
                quote = data["quotes"]["quote"]
                if isinstance(quote, list):
                    quote = quote[0]
                
                # Use current price as close, create synthetic bar
                now = datetime.now()
                price = float(quote.get("last", quote.get("bid", 0)))
                if price > 0:
                    return Bar(
                        timestamp=now,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=int(quote.get("volume", 0))
                    )
        except Exception as e:
            print(f"Error fetching latest bar: {e}")
        
        return None
    
    def is_market_open(self) -> bool:
        """Check if market is open using Tradier clock endpoint."""
        url = f"{self.config.base_url}/markets/clock"
        
        try:
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "clock" in data:
                state = data["clock"].get("state", "").lower()
                return state == "open"
        except Exception as e:
            print(f"Error checking market status: {e}")
        
        return False
    
    def _map_interval(self, interval: str) -> str:
        """Map interval format to Tradier format."""
        mapping = {
            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "1hour": "1hour",
            "daily": "daily"
        }
        return mapping.get(interval, "1min")
    
    def _parse_bar(self, bar_data: dict, interval: str) -> Bar:
        """Parse Tradier bar data to Bar object."""
        # Tradier returns daily bars, need to adapt for intraday
        timestamp_str = bar_data.get("date", "")
        try:
            if "T" in timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d")
        except:
            timestamp = datetime.now()
        
        return Bar(
            timestamp=timestamp,
            open=float(bar_data.get("open", 0)),
            high=float(bar_data.get("high", 0)),
            low=float(bar_data.get("low", 0)),
            close=float(bar_data.get("close", 0)),
            volume=int(bar_data.get("volume", 0))
        )

