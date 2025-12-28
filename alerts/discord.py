"""Discord webhook integration."""
import requests
from typing import Optional
from signals.detector import Signal
from config import DiscordConfig


class DiscordNotifier:
    """Discord webhook notification handler."""
    
    def __init__(self, config: Optional[DiscordConfig]):
        """
        Initialize Discord notifier.
        
        Args:
            config: Discord configuration (None if disabled)
        """
        self.config = config
        self.enabled = config is not None and config.enabled and config.webhook_url is not None
    
    def send_alert(self, message: str) -> bool:
        """
        Send alert message to Discord.
        
        Args:
            message: Alert message to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not self.config:
            return False
        
        try:
            payload = {
                "content": f"```\n{message}\n```",
                "username": "RSI Alerter"
            }
            
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error sending Discord notification: {e}")
            return False




