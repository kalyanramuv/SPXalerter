"""Main entry point for RSI Live Alerter."""
import os
import uvicorn
import threading
from dotenv import load_dotenv
from config import AppConfig
from engine import RSIEngine

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
    
    # Validate required config
    if not config.tradier.api_key:
        print("ERROR: TRADIER_API_KEY environment variable is required")
        print("Please set it: export TRADIER_API_KEY=your_key")
        return
    
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

