"""Main entry point for RSI Live Alerter."""
import os
import uvicorn
import threading
from dotenv import load_dotenv
from config import AppConfig
from engine import RSIEngine
from pathlib import Path

# Load environment variables from .env file
load_dotenv()


def run_api():
    """Run FastAPI server in separate thread."""
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


def main():
    """Main entry point."""
    # Load configuration
    config = AppConfig.from_env()
    
    # Initialize runtime config (loads persisted settings if available)
    from api.runtime_config import runtime_config
    # On first run (no persisted config file), use config value from .env
    # If persisted config exists, it will have been loaded in RuntimeConfig.__init__
    config_file_path = Path("runtime_config.json")
    if not config_file_path.exists():
        # First run - use config values from .env and save them
        runtime_config.polling_interval_seconds = config.polling_interval_seconds
        runtime_config.historical_bars_count = config.historical_bars_count
        runtime_config._save_config()
    
    # Note: Runtime config (bypass_market_hours, use_mock_data, polling_interval) is checked
    # dynamically in the engine, so we don't need to set it here at startup
    
    # Validate required config (will be checked again in engine if mock mode enabled)
    if not config.tradier.api_key:
        print("WARNING: TRADIER_API_KEY not set. Enable 'Simulate Data' mode in web UI to use mock data.")
        print("Or set it: export TRADIER_API_KEY=your_key")
    
    # Start API server in background thread
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    print("FastAPI dashboard started at http://localhost:8000")
    print("-" * 50)
    
    # Start RSI engine
    engine = RSIEngine(config)
    engine.run()


if __name__ == "__main__":
    main()

