from __future__ import annotations

from services.android_thermostat import (
    normalize_get_status,
    normalize_set_range,
)


def test_normalize_get_status_passthrough_schema() -> None:
    data = {
        "current_temp": 72,
        "target_low": 68,
        "target_high": 74,
        "mode": "heat_cool",
        "humidity": 45,
        "status": "idle",
    }
    out = normalize_get_status(data)
    assert out["current_temp"] == 72
    assert out["target_low"] == 68
    assert out["target_high"] == 74
    assert out["mode"] == "heat_cool"
    assert out["humidity"] == 45
    assert out["status"] == "idle"


def test_normalize_get_status_common_google_home_shape() -> None:
    data = {
        "thermostat_device_name": "Nest Thermostat",
        "current_temperature": "68°",
        "heat_setpoint": "65",
        "cool_setpoint": "68",
        "mode": "Heat • Cool",
        "status_text": "Maintaining 65° for heating and 68° for cooling",
        "additional_readings": {"indoor_humidity": "45%"},
    }
    out = normalize_get_status(data)
    assert out["device_name"] == "Nest Thermostat"
    assert out["current_temp"] == 68
    assert out["target_low"] == 65
    assert out["target_high"] == 68
    assert out["mode"] == "heat_cool"
    assert out["humidity"] == 45
    assert out["status"] == "idle"


def test_normalize_get_status_nested_setpoints_shape() -> None:
    data = {
        "device_name": "Nest Thermostat",
        "current_temperature": "70°F",
        "setpoints": {"heat_setpoint": "66°", "cool_setpoint": "72°"},
        "hvac_status": "Cooling",
        "mode": "Cool",
    }
    out = normalize_get_status(data)
    assert out["current_temp"] == 70
    assert out["target_low"] == 66
    assert out["target_high"] == 72
    assert out["mode"] == "cool"
    assert out["status"] == "cooling"


def test_normalize_set_range_handles_string_values() -> None:
    data = {
        "final_low_temp": "65°",
        "final_high_temp": "68°F",
        "mode": "Heat & Cool",
    }
    out = normalize_set_range(data)
    assert out["final_low_temp"] == 65
    assert out["final_high_temp"] == 68
    assert out["mode"] == "heat_cool"
