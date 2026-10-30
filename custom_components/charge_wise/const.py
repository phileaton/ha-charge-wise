"""Constants for Charge Wise."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "charge_wise"

CONF_GRID_POWER_ENTITY = "grid_power_entity"
CONF_CHARGER_POWER_ENTITY = "charger_power_entity"
CONF_CHARGER_SWITCH_ENTITY = "charger_switch_entity"
CONF_CURRENT_TARGET_ENTITY = "current_target_entity"
CONF_HARDWARE_MAXIMUM_ENTITY = "hardware_maximum_entity"
CONF_BATTERY_POWER_ENTITY = "battery_power_entity"
CONF_BATTERY_DISCHARGE_SIGN = "battery_discharge_sign"
CONF_EV_CONNECTED_ENTITY = "ev_connected_entity"
CONF_MINIMUM_CURRENT_A = "minimum_current_a"
CONF_MAXIMUM_CURRENT_A = "maximum_current_a"
CONF_VOLTAGE_V = "voltage_v"
CONF_SOLAR_START_W = "solar_start_w"
CONF_LOW_SOLAR_CONFIRMATION_S = "low_solar_confirmation_s"
CONF_COOLDOWN_S = "cooldown_s"
CONF_BATTERY_DISCHARGE_W = "battery_discharge_w"
CONF_BATTERY_RECOVERY_W = "battery_recovery_w"
CONF_BATTERY_CONFIRMATION_S = "battery_confirmation_s"
CONF_BATTERY_RECOVERY_CONFIRMATION_S = "battery_recovery_confirmation_s"
CONF_CURRENT_DEADBAND_A = "current_deadband_a"
CONF_MANUAL_CURRENT_A = "manual_current_a"
CONF_OFFPEAK_WINDOWS = "offpeak_windows"
CONF_FORECAST_REMAINING_ENTITY = "forecast_remaining_entity"
CONF_BATTERY_LEVEL_ENTITY = "battery_level_entity"
CONF_HOUSE_POWER_ENTITY = "house_power_entity"
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_BATTERY_TARGET_PERCENT = "battery_target_percent"
CONF_FORECAST_TRUST_PERCENT = "forecast_trust_percent"
CONF_HOUSE_LOAD_WINDOW_DAYS = "house_load_window_days"

BATTERY_SIGN_POSITIVE = "positive"
BATTERY_SIGN_NEGATIVE = "negative"

DEFAULT_MINIMUM_CURRENT_A = 6
DEFAULT_VOLTAGE_V = 240
DEFAULT_SOLAR_START_W = 1800
DEFAULT_LOW_SOLAR_CONFIRMATION_S = 90
DEFAULT_COOLDOWN_S = 180
DEFAULT_BATTERY_DISCHARGE_W = 300
DEFAULT_BATTERY_RECOVERY_W = 150
DEFAULT_BATTERY_CONFIRMATION_S = 90
DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S = 90
DEFAULT_CURRENT_DEADBAND_A = 1.0
DEFAULT_BATTERY_DISCHARGE_SIGN = BATTERY_SIGN_POSITIVE
DEFAULT_BATTERY_TARGET_PERCENT = 90
DEFAULT_FORECAST_TRUST_PERCENT = 80
DEFAULT_HOUSE_LOAD_WINDOW_DAYS = 3
