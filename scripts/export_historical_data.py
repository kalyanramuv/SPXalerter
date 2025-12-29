"""Script to export historical intraday data from Tradier to JSON files for playback."""
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.tradier import TradierProvider
from config import AppConfig


def export_historical_data(symbol: str = "SPY", timeframes: list = None, count: int = 2000, output_dir: str = "historical_data"):
    """
    Export historical intraday data from Tradier to JSON files.
    
    Args:
        symbol: Trading symbol (default: SPY)
        timeframes: List of timeframes to export (default: ["1min", "5min", "30min"])
        count: Number of bars to export per timeframe (default: 2000)
        output_dir: Output directory for JSON files (default: "historical_data")
    """
    if timeframes is None:
        timeframes = ["1min", "5min", "30min"]
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Load config
    config = AppConfig.from_env()
    
    # Check if API key is set
    if not config.tradier.api_key:
        print("ERROR: TRADIER_API_KEY environment variable is not set!")
        print("\nTo fix this:")
        print("1. Get your API key from https://developer.tradier.com/")
        print("2. Set the environment variable:")
        print("   Windows PowerShell: $env:TRADIER_API_KEY='your_api_key_here'")
        print("   Windows CMD: set TRADIER_API_KEY=your_api_key_here")
        print("   Linux/Mac: export TRADIER_API_KEY='your_api_key_here'")
        print("\nOr create a .env file with:")
        print("   TRADIER_API_KEY=your_api_key_here")
        sys.exit(1)
    
    # Create Tradier provider
    provider = TradierProvider(config.tradier)
    
    print(f"Exporting historical data for {symbol}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Bars per timeframe: {count}")
    print(f"Output directory: {output_path.absolute()}")
    print("-" * 50)
    
    for timeframe in timeframes:
        print(f"\nExporting {timeframe} data...")
        
        try:
            # Fetch historical bars
            bars = provider.get_historical_bars(symbol, timeframe, count=count)
            
            if not bars:
                print(f"  Warning: No bars returned for {timeframe}")
                continue
            
            print(f"  Fetched {len(bars)} bars")
            
            # Convert bars to JSON-serializable format
            bars_data = []
            for bar in bars:
                bars_data.append({
                    "timestamp": bar.timestamp.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume)
                })
            
            # Save to JSON file
            output_file = output_path / f"{symbol}_{timeframe}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(bars_data, f, indent=2, ensure_ascii=False)
            
            print(f"  Saved to {output_file}")
            
            # Show date range
            if bars:
                first_bar = bars[0]
                last_bar = bars[-1]
                print(f"  Date range: {first_bar.timestamp.strftime('%Y-%m-%d %H:%M')} to {last_bar.timestamp.strftime('%Y-%m-%d %H:%M')}")
        
        except Exception as e:
            print(f"  Error exporting {timeframe}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "-" * 50)
    print("Export complete!")
    print(f"\nTo use this data for playback:")
    print(f"1. Enable 'Simulate Data' in the web UI, OR")
    print(f"2. Set environment variable: USE_HISTORICAL_PLAYBACK=true")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export historical intraday data from Tradier")
    parser.add_argument("--symbol", default="SPY", help="Trading symbol (default: SPY)")
    parser.add_argument("--timeframes", nargs="+", default=["1min", "5min", "30min"],
                        help="Timeframes to export (default: 1min 5min 30min)")
    parser.add_argument("--count", type=int, default=2000,
                        help="Number of bars to export per timeframe (default: 2000)")
    parser.add_argument("--output-dir", default="historical_data",
                        help="Output directory for JSON files (default: historical_data)")
    
    args = parser.parse_args()
    
    export_historical_data(
        symbol=args.symbol,
        timeframes=args.timeframes,
        count=args.count,
        output_dir=args.output_dir
    )

