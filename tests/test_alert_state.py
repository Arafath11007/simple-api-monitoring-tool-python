import time
from api_monitor.alert_state import AlertStateManager

def test_alert_cooldown(tmp_path):
    state_file = tmp_path / "alert_state.json"
    mgr = AlertStateManager(state_file)

    # First check: should alert
    assert mgr.should_alert("Orders API", cooldown_minutes=60) is True

    # Record alert
    mgr.record_alert("Orders API")

    # Immediate second check: should NOT alert (inside cooldown)
    assert mgr.should_alert("Orders API", cooldown_minutes=60) is False

    # Different endpoint: should alert
    assert mgr.should_alert("Inventory API", cooldown_minutes=60) is True

    # Cooldown 0 minutes: should allow alerting immediately
    assert mgr.should_alert("Orders API", cooldown_minutes=0) is True
