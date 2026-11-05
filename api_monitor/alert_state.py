"""Alert cooldown manager to suppress repeated failure alerts."""

import json
from datetime import datetime, timezone
from pathlib import Path


class AlertStateManager:
    def __init__(self, state_file: str | Path = "./logs/alert_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict[str, str]:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self, state: dict[str, str]) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def should_alert(self, endpoint_name: str, cooldown_minutes: int) -> bool:
        """Returns True if the endpoint should alert, False if currently within cooldown."""
        state = self._load_state()
        last_alert_str = state.get(endpoint_name)
        if not last_alert_str:
            return True

        try:
            last_alert_time = datetime.fromisoformat(last_alert_str)
            now = datetime.now(timezone.utc)
            diff_minutes = (now - last_alert_time).total_seconds() / 60.0
            return diff_minutes >= cooldown_minutes
        except Exception:
            return True

    def record_alert(self, endpoint_name: str) -> None:
        """Records an alert timestamp for an endpoint."""
        state = self._load_state()
        state[endpoint_name] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)
