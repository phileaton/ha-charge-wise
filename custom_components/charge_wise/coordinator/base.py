"""Event-driven coordinator for Charge Wise."""

import asyncio
from datetime import datetime
from math import isclose, isfinite
from typing import TYPE_CHECKING, Any, Literal

from custom_components.charge_wise.const import (
    BATTERY_SIGN_NEGATIVE,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CONFIRMATION_S,
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_BATTERY_DISCHARGE_W,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_RECOVERY_CONFIRMATION_S,
    CONF_BATTERY_RECOVERY_W,
    CONF_BATTERY_TARGET_PERCENT,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_COOLDOWN_S,
    CONF_CURRENT_DEADBAND_A,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TRUST_PERCENT,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_HOUSE_LOAD_WINDOW_DAYS,
    CONF_LOW_SOLAR_CONFIRMATION_S,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    CONF_OFFPEAK_WINDOWS,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_START_W,
    CONF_VOLTAGE_V,
    DEFAULT_BATTERY_CONFIRMATION_S,
    DEFAULT_BATTERY_DISCHARGE_SIGN,
    DEFAULT_BATTERY_DISCHARGE_W,
    DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
    DEFAULT_BATTERY_RECOVERY_W,
    DEFAULT_BATTERY_TARGET_PERCENT,
    DEFAULT_COOLDOWN_S,
    DEFAULT_CURRENT_DEADBAND_A,
    DEFAULT_FORECAST_TRUST_PERCENT,
    DEFAULT_HOUSE_LOAD_WINDOW_DAYS,
    DEFAULT_LOW_SOLAR_CONFIRMATION_S,
    DEFAULT_MINIMUM_CURRENT_A,
    DEFAULT_SOLAR_START_W,
    DEFAULT_VOLTAGE_V,
    DOMAIN,
    LOGGER,
)
from custom_components.charge_wise.coordinator.data import ChargeWiseSnapshot
from custom_components.charge_wise.utils.charging_controller import (
    ChargeWiseController,
    ChargeWiseReason,
    ControllerConfig,
    ControllerDecision,
    ControllerInput,
    ControllerStatus,
    ControlSettings,
)
from custom_components.charge_wise.utils.ev_first import EvFirstConfig, EvFirstInputs, EvFirstResult, evaluate_ev_first
from custom_components.charge_wise.utils.house_load import HouseLoadProfile
from custom_components.charge_wise.utils.tariff_windows import is_active, next_change, next_start, windows_from_options
from homeassistant.const import ATTR_ENTITY_ID, ATTR_UNIT_OF_MEASUREMENT, STATE_OFF, STATE_ON, UnitOfEnergy, UnitOfPower
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry

_HOUSE_LOAD_SAVE_DELAY_S = 300

_POWER_FACTORS: dict[str, float] = {
    UnitOfPower.MILLIWATT: 0.001,
    UnitOfPower.WATT: 1.0,
    UnitOfPower.KILO_WATT: 1000.0,
}


_ENERGY_FACTORS_KWH: dict[str, float] = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}

type SwitchKey = Literal["enabled", "solar_enabled", "offpeak_enabled", "manual_override", "ev_first_enabled"]


class ChargeWiseDataUpdateCoordinator(DataUpdateCoordinator[ChargeWiseSnapshot]):
    """Keep a shared snapshot current from Home Assistant entity state changes."""

    def __init__(self, hass: HomeAssistant, entry: ChargeWiseConfigEntry) -> None:
        """Initialize controller state from config-entry options."""
        self.entry = entry
        self.options = entry.options
        self.switches: dict[SwitchKey, bool] = {
            "enabled": False,
            "solar_enabled": False,
            "offpeak_enabled": False,
            "manual_override": False,
            "ev_first_enabled": False,
        }
        self.manual_current_a = float(self.options[CONF_MINIMUM_CURRENT_A])
        self.offpeak_current_a = self.manual_current_a
        self.windows = windows_from_options(self.options.get(CONF_OFFPEAK_WINDOWS))
        self.ev_first_config = self._ev_first_config_from_options()
        self.battery_configured = bool(self.options.get(CONF_BATTERY_POWER_ENTITY))
        self.ev_connected_configured = bool(self.options.get(CONF_EV_CONNECTED_ENTITY))
        self.house_load = HouseLoadProfile(
            float(self.options.get(CONF_HOUSE_LOAD_WINDOW_DAYS, DEFAULT_HOUSE_LOAD_WINDOW_DAYS)),
        )
        self._house_load_store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.house_load")
        self._timer_unsub: Any = None
        self._state_unsub: Any = None
        self._evaluation_lock = asyncio.Lock()
        self._config = ControllerConfig(
            minimum_current_a=int(self.options.get(CONF_MINIMUM_CURRENT_A, DEFAULT_MINIMUM_CURRENT_A)),
            maximum_current_a=int(self.options[CONF_MAXIMUM_CURRENT_A]),
            voltage_v=int(self.options.get(CONF_VOLTAGE_V, DEFAULT_VOLTAGE_V)),
            solar_start_w=int(self.options.get(CONF_SOLAR_START_W, DEFAULT_SOLAR_START_W)),
            low_solar_confirmation_s=int(
                self.options.get(CONF_LOW_SOLAR_CONFIRMATION_S, DEFAULT_LOW_SOLAR_CONFIRMATION_S),
            ),
            cooldown_s=int(self.options.get(CONF_COOLDOWN_S, DEFAULT_COOLDOWN_S)),
            battery_discharge_w=int(self.options.get(CONF_BATTERY_DISCHARGE_W, DEFAULT_BATTERY_DISCHARGE_W)),
            battery_recovery_w=int(self.options.get(CONF_BATTERY_RECOVERY_W, DEFAULT_BATTERY_RECOVERY_W)),
            battery_confirmation_s=int(self.options.get(CONF_BATTERY_CONFIRMATION_S, DEFAULT_BATTERY_CONFIRMATION_S)),
            battery_recovery_confirmation_s=int(
                self.options.get(
                    CONF_BATTERY_RECOVERY_CONFIRMATION_S,
                    DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
                ),
            ),
            current_deadband_a=float(
                self.options.get(CONF_CURRENT_DEADBAND_A, DEFAULT_CURRENT_DEADBAND_A),
            ),
        )
        self.controller = ChargeWiseController(self._config)

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=None,
            always_update=False,
        )
        self.data = ChargeWiseSnapshot(
            enabled=False,
            solar_enabled=False,
            offpeak_enabled=False,
            manual_override=False,
            ev_first_enabled=False,
            ev_first_active=False,
            offpeak_active=False,
            next_offpeak_start=None,
            status=ControllerStatus.OFF,
            reason=ChargeWiseReason.OFF,
            available_solar_w=None,
            requested_current_a=0.0,
            manual_current_a=self.manual_current_a,
            offpeak_current_a=self.offpeak_current_a,
            battery_protection_active=False if self.battery_configured else None,
        )

    async def async_start(self) -> None:
        """Subscribe to inputs and start with every charging source off."""
        entity_ids = {
            self.options[key]
            for key in (
                CONF_GRID_POWER_ENTITY,
                CONF_CHARGER_POWER_ENTITY,
                CONF_CHARGER_SWITCH_ENTITY,
                CONF_CURRENT_TARGET_ENTITY,
                CONF_HARDWARE_MAXIMUM_ENTITY,
                CONF_BATTERY_POWER_ENTITY,
                CONF_EV_CONNECTED_ENTITY,
                CONF_FORECAST_REMAINING_ENTITY,
                CONF_BATTERY_LEVEL_ENTITY,
                CONF_SOLAR_POWER_ENTITY,
            )
            if self.options.get(key)
        }
        if self.ev_first_config is not None:
            entity_ids.add("sun.sun")
            self.house_load.restore(await self._house_load_store.async_load())
        self._state_unsub = async_track_state_change_event(
            self.hass,
            entity_ids,
            self._handle_state_change,
        )
        await self._async_evaluate()

    async def async_stop(self) -> None:
        """Remove state and timer subscriptions."""
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        self._cancel_timer()
        if self.ev_first_config is not None:
            await self._house_load_store.async_save(self.house_load.as_dict())

    async def async_set_switch(self, key: SwitchKey, value: bool, *, restoring: bool = False) -> None:
        """Turn a charging source on or off; a restored source waits through the safety cooldown."""
        if key == "ev_first_enabled" and value and self.ev_first_config is None:
            if restoring:
                return
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="ev_first_not_configured")
        self.switches[key] = value
        if restoring and value:
            self.controller.start_cooldown(dt_util.utcnow())
        await self._async_evaluate()

    @property
    def maximum_current_a(self) -> float:
        """Return the configured maximum, lowered to the live hardware maximum when available."""
        maximum = float(self.controller.config.maximum_current_a)
        hardware_a = self._number_value(self.options.get(CONF_HARDWARE_MAXIMUM_ENTITY))
        return maximum if hardware_a is None else min(maximum, hardware_a)

    async def async_set_manual_current(self, current_a: float) -> None:
        """Store a manual target and immediately re-evaluate."""
        self.manual_current_a = current_a
        await self._async_evaluate()

    async def async_set_offpeak_current(self, current_a: float) -> None:
        """Store the off-peak target and immediately re-evaluate."""
        self.offpeak_current_a = current_a
        await self._async_evaluate()

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Schedule a new snapshot after any configured source changes."""
        self.entry.async_create_task(self.hass, self._async_evaluate(), "Charge Wise state update")

    @callback
    def _handle_timer(self, now: datetime) -> None:
        """Re-evaluate when a confirmation or cooldown deadline expires."""
        self._timer_unsub = None
        self.entry.async_create_task(self.hass, self._async_evaluate(), "Charge Wise timer")

    async def _async_evaluate(self) -> None:
        """Calculate, apply, and publish the next controller decision."""
        async with self._evaluation_lock:
            await self._async_evaluate_locked()

    async def _async_evaluate_locked(self) -> None:
        """Calculate, apply, and publish one controller decision at a time."""
        now = dt_util.utcnow()
        local_now = dt_util.as_local(now)
        self._observe_house_load(now)
        offpeak_active = self.switches["offpeak_enabled"] and is_active(self.windows, local_now)
        settings = ControlSettings(
            enabled=self.switches["enabled"],
            solar_enabled=self.switches["solar_enabled"],
            offpeak_enabled=self.switches["offpeak_enabled"],
            manual_override=self.switches["manual_override"],
            manual_current_a=self.manual_current_a,
            offpeak_current_a=self.offpeak_current_a,
            offpeak_active=offpeak_active,
            offpeak_next_change=next_change(self.windows, local_now),
        )
        ev_first_active = self._ev_first_active(now)
        decision = self.controller.evaluate(settings, self._read_inputs(ev_first_active=ev_first_active), now)
        next_start_at = next_start(self.windows, local_now) if self.switches["offpeak_enabled"] else None
        try:
            await self._async_apply_decision(decision)
        except HomeAssistantError:
            LOGGER.exception("Failed to apply charger control decision")
            await self._async_fail_safe()
            self.async_set_updated_data(
                self._snapshot(
                    decision,
                    offpeak_active,
                    next_start_at,
                    ev_first_active,
                    status=ControllerStatus.ERROR,
                    reason=ChargeWiseReason.CONTROL_FAILED,
                    requested_current_a=0.0,
                ),
            )
            self._cancel_timer()
            return

        self.async_set_updated_data(self._snapshot(decision, offpeak_active, next_start_at, ev_first_active))
        self._schedule_timer(decision)

    def _snapshot(
        self,
        decision: ControllerDecision,
        offpeak_active: bool,
        next_offpeak_start: datetime | None,
        ev_first_active: bool,
        *,
        status: ControllerStatus | None = None,
        reason: ChargeWiseReason | None = None,
        requested_current_a: float | None = None,
    ) -> ChargeWiseSnapshot:
        """Combine a controller decision with user switches for entities."""
        return ChargeWiseSnapshot(
            enabled=self.switches["enabled"],
            solar_enabled=self.switches["solar_enabled"],
            offpeak_enabled=self.switches["offpeak_enabled"],
            manual_override=self.switches["manual_override"],
            ev_first_enabled=self.switches["ev_first_enabled"],
            ev_first_active=ev_first_active,
            offpeak_active=offpeak_active,
            next_offpeak_start=next_offpeak_start,
            status=status or decision.status,
            reason=reason or decision.reason,
            available_solar_w=decision.available_solar_w,
            requested_current_a=decision.requested_current_a if requested_current_a is None else requested_current_a,
            manual_current_a=self.manual_current_a,
            offpeak_current_a=self.offpeak_current_a,
            battery_protection_active=decision.battery_protection_active,
            average_house_load_w=self.house_load.overall_w,
        )

    def _observe_house_load(self, now: datetime) -> None:
        """Feed the current house power into the learned consumption profile."""
        if self.ev_first_config is None:
            return
        self.house_load.observe(self._house_power_w(), dt_util.as_local(now))
        self._house_load_store.async_delay_save(self.house_load.as_dict, _HOUSE_LOAD_SAVE_DELAY_S)

    def _battery_discharge_w(self) -> float | None:
        """Return battery power with discharge positive, whatever sign the sensor uses."""
        power = self._power_w(self.options.get(CONF_BATTERY_POWER_ENTITY))
        if (
            power is not None
            and self.options.get(CONF_BATTERY_DISCHARGE_SIGN, DEFAULT_BATTERY_DISCHARGE_SIGN) == BATTERY_SIGN_NEGATIVE
        ):
            return -power
        return power

    def _house_power_w(self) -> float | None:
        """Return house consumption excluding the EV: production + grid import + battery discharge - charger."""
        production = self._power_w(self.options.get(CONF_SOLAR_POWER_ENTITY))
        grid = self._power_w(self.options[CONF_GRID_POWER_ENTITY])
        charger = self._power_w(self.options[CONF_CHARGER_POWER_ENTITY])
        battery = self._battery_discharge_w() if self.battery_configured else 0.0
        if production is None or grid is None or charger is None or battery is None:
            return None
        return max(0.0, production + grid + battery - charger)

    def _read_inputs(self, *, ev_first_active: bool = False) -> ControllerInput:
        """Read and normalize the currently configured Home Assistant entities."""
        battery_power = self._battery_discharge_w()

        ev_connected: bool | None = None
        ev_entity = self.options.get(CONF_EV_CONNECTED_ENTITY)
        if ev_entity:
            state = self.hass.states.get(ev_entity)
            if state is not None:
                if state.state == STATE_ON:
                    ev_connected = True
                elif state.state == STATE_OFF:
                    ev_connected = False

        ev_first_boost_w = max(0.0, -battery_power) if ev_first_active and battery_power is not None else 0.0

        return ControllerInput(
            grid_power_w=self._power_w(self.options[CONF_GRID_POWER_ENTITY]),
            charger_power_w=self._power_w(self.options[CONF_CHARGER_POWER_ENTITY]),
            battery_discharge_w=battery_power,
            battery_configured=self.battery_configured,
            ev_connected=ev_connected,
            ev_connected_configured=self.ev_connected_configured,
            charger_enabled=self._entity_is_on(self.options[CONF_CHARGER_SWITCH_ENTITY]),
            current_target_a=self._number_value(self.options[CONF_CURRENT_TARGET_ENTITY]),
            hardware_maximum_a=self._number_value(self.options.get(CONF_HARDWARE_MAXIMUM_ENTITY)),
            ev_first_boost_w=ev_first_boost_w,
        )

    def _ev_first_config_from_options(self) -> EvFirstConfig | None:
        """Return the EV-first settings, or None when the forecast inputs are not all configured."""
        keys = (
            CONF_FORECAST_REMAINING_ENTITY,
            CONF_BATTERY_LEVEL_ENTITY,
            CONF_SOLAR_POWER_ENTITY,
            CONF_BATTERY_CAPACITY_KWH,
        )
        if not all(self.options.get(key) for key in keys):
            return None
        return EvFirstConfig(
            battery_capacity_kwh=float(self.options[CONF_BATTERY_CAPACITY_KWH]),
            battery_target_percent=float(self.options.get(CONF_BATTERY_TARGET_PERCENT, DEFAULT_BATTERY_TARGET_PERCENT)),
            forecast_trust_percent=float(self.options.get(CONF_FORECAST_TRUST_PERCENT, DEFAULT_FORECAST_TRUST_PERCENT)),
        )

    def _ev_first_result(self, now: datetime) -> EvFirstResult | None:
        """Return the forecast energy balance, or None when EV-first cannot be judged."""
        if self.ev_first_config is None:
            return None
        sun_state = self.hass.states.get("sun.sun")
        hours_until_sunset: float | None = None
        house_use_kwh: float | None = None
        instant_w = self._house_power_w()
        if sun_state is not None and sun_state.state == "above_horizon":
            setting = dt_util.parse_datetime(str(sun_state.attributes.get("next_setting", "")))
            if setting is not None:
                hours_until_sunset = (setting - now).total_seconds() / 3600
                if instant_w is not None or self.house_load.overall_w is not None:
                    house_use_kwh = self.house_load.expected_energy_kwh(
                        dt_util.as_local(now),
                        dt_util.as_local(setting),
                        instant_w if instant_w is not None else 0.0,
                    )
        return evaluate_ev_first(
            self.ev_first_config,
            EvFirstInputs(
                forecast_remaining_kwh=self._energy_kwh(self.options.get(CONF_FORECAST_REMAINING_ENTITY)),
                battery_level_percent=self._number_value(self.options.get(CONF_BATTERY_LEVEL_ENTITY)),
                house_use_kwh=house_use_kwh,
                hours_until_sunset=hours_until_sunset,
            ),
        )

    def _ev_first_active(self, now: datetime) -> bool:
        """Return whether the EV may currently share the battery's charging power."""
        if not (self.switches["ev_first_enabled"] and self.switches["solar_enabled"]):
            return False
        result = self._ev_first_result(now)
        return result is not None and result.active

    def _energy_kwh(self, entity_id: str | None) -> float | None:
        """Return a finite energy reading converted to kWh."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        factor = _ENERGY_FACTORS_KWH.get(str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)))
        if factor is None or not isfinite(value):
            return None
        return value * factor

    def _power_w(self, entity_id: str | None) -> float | None:
        """Return a finite W measurement from a sensor reporting a power unit."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if not isinstance(unit, str):
            return None
        factor = _POWER_FACTORS.get(unit)
        if factor is None or not isfinite(value):
            return None
        return value * factor

    def _number_value(self, entity_id: str | None) -> float | None:
        """Return a finite numeric value from a number entity."""
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if isfinite(value) else None

    def _entity_is_on(self, entity_id: str) -> bool:
        """Return whether the selected charger switch currently reports on."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == STATE_ON

    async def _async_apply_decision(self, decision: ControllerDecision) -> None:
        """Apply current limit before enabling the charger; stop immediately when unsafe."""
        switch_entity = self.options[CONF_CHARGER_SWITCH_ENTITY]
        switch_state = self.hass.states.get(switch_entity)

        if not decision.charger_enabled:
            if switch_state is None or switch_state.state != STATE_OFF:
                await self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    {ATTR_ENTITY_ID: switch_entity},
                    blocking=True,
                )
            return

        current_entity = self.options[CONF_CURRENT_TARGET_ENTITY]
        current_state = self._number_value(current_entity)
        if current_state is None or not isclose(
            current_state,
            decision.requested_current_a,
            abs_tol=0.01,
        ):
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    ATTR_ENTITY_ID: current_entity,
                    "value": decision.requested_current_a,
                },
                blocking=True,
            )

        if switch_state is None or switch_state.state != STATE_ON:
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {ATTR_ENTITY_ID: switch_entity},
                blocking=True,
            )

    async def _async_fail_safe(self) -> None:
        """Try to disable charging after a failed target or switch command."""
        switch_entity = self.options[CONF_CHARGER_SWITCH_ENTITY]
        state = self.hass.states.get(switch_entity)
        if state is not None and state.state == STATE_OFF:
            return
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {ATTR_ENTITY_ID: switch_entity},
                blocking=True,
            )
        except HomeAssistantError:
            LOGGER.exception("Failed to disable charger after a control error")

    def _schedule_timer(self, decision: ControllerDecision) -> None:
        """Schedule only the next required confirmation or cooldown evaluation."""
        self._cancel_timer()
        if decision.next_update_at is None:
            return
        delay = max(0.0, (decision.next_update_at - dt_util.utcnow()).total_seconds())
        if delay:
            self._timer_unsub = async_call_later(self.hass, delay, self._handle_timer)

    def _cancel_timer(self) -> None:
        """Cancel the pending controller timer, if any."""
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None
