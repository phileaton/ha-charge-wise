"""Event-driven coordinator for Charge Wise."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial
from math import isclose, isfinite
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy.exc import SQLAlchemyError

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
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CHARGER_STATUS_PROFILE,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_COOLDOWN_S,
    CONF_CURRENT_DEADBAND_A,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_EV_FIRST_RELEASE_MARGIN_PERCENT,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_HOUSE_LOAD_WINDOW_DAYS,
    CONF_LOW_SOLAR_CONFIRMATION_S,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    CONF_NATIVE_SOLAR_ENTITY,
    CONF_NATIVE_SOLAR_OFF_OPTION,
    CONF_NATIVE_SOLAR_OPTION,
    CONF_NATIVE_SOLAR_RELEASE_PERCENT,
    CONF_OFFPEAK_WINDOWS,
    CONF_SETTLE_HOLD_S,
    CONF_SMOOTHING_WINDOW_S,
    CONF_SOLAR_ENERGY_ENTITY,
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
    DEFAULT_EV_FIRST_RELEASE_MARGIN_PERCENT,
    DEFAULT_HOUSE_LOAD_WINDOW_DAYS,
    DEFAULT_LOW_SOLAR_CONFIRMATION_S,
    DEFAULT_MINIMUM_CURRENT_A,
    DEFAULT_NATIVE_SOLAR_RELEASE_PERCENT,
    DEFAULT_SETTLE_HOLD_S,
    DEFAULT_SMOOTHING_WINDOW_S,
    DEFAULT_SOLAR_START_W,
    DEFAULT_VOLTAGE_V,
    DOMAIN,
    LOGGER,
    POWER_TO_W,
)
from custom_components.charge_wise.coordinator.data import ChargeWiseSnapshot
from custom_components.charge_wise.utils.charger_startup import COMMAND_CONFIRMATION, ChargeWiseStartupMonitor
from custom_components.charge_wise.utils.charger_status import (
    ChargerObservation,
    ChargingPowerDetector,
    charger_status_source,
    classify_status,
)
from custom_components.charge_wise.utils.charging_controller import (
    ChargeWiseController,
    ChargeWiseReason,
    ControllerConfig,
    ControllerDecision,
    ControllerInput,
    ControllerStatus,
    ControlSettings,
    solar_budget_w,
)
from custom_components.charge_wise.utils.ev_first import EvFirstConfig, EvFirstInputs, EvFirstResult, evaluate_ev_first
from custom_components.charge_wise.utils.ev_under_drawing import EvUnderDrawingDetector
from custom_components.charge_wise.utils.forecast_accuracy import ForecastAccuracy
from custom_components.charge_wise.utils.house_load import HouseLoadProfile
from custom_components.charge_wise.utils.tariff_windows import (
    is_active,
    next_change,
    next_period_end,
    next_start,
    windows_from_options,
)
from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry

_HOUSE_LOAD_SAVE_DELAY_S = 300

_ENERGY_FACTORS_KWH: dict[str, float] = {
    UnitOfEnergy.WATT_HOUR: 0.001,
    UnitOfEnergy.KILO_WATT_HOUR: 1.0,
    UnitOfEnergy.MEGA_WATT_HOUR: 1000.0,
}

SWITCH_COMMAND_GRACE_S = 30

type SwitchKey = Literal["enabled", "solar_enabled", "manual_override"]


class ChargeWiseDataUpdateCoordinator(DataUpdateCoordinator[ChargeWiseSnapshot]):
    """Keep a shared snapshot current from Home Assistant entity state changes."""

    def __init__(self, hass: HomeAssistant, entry: ChargeWiseConfigEntry) -> None:
        """Initialize controller state from config-entry options."""
        self.entry = entry
        self.options = entry.options
        self.switches: dict[SwitchKey, bool] = {
            "enabled": False,
            "solar_enabled": False,
            "manual_override": False,
        }
        self.manual_current_a = float(self.options[CONF_MINIMUM_CURRENT_A])
        self.offpeak_current_a = self.manual_current_a
        self.offpeak_mode = "off"
        self.ev_first_mode = "off"
        self._ev_first_until: datetime | None = None
        self._offpeak_until: datetime | None = None
        self._offpeak_store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.offpeak")
        self.windows = windows_from_options(self.options.get(CONF_OFFPEAK_WINDOWS))
        self.ev_first_config = self._ev_first_config_from_options()
        self._ev_first_was_active = False
        self.forecast_accuracy = ForecastAccuracy()
        self._last_switch_command: tuple[bool, datetime] | None = None
        self._last_native_command: tuple[str, datetime] | None = None
        self._last_native_current_command: tuple[float, datetime] | None = None
        self._native_full_battery = False
        self._native_battery_store: Store[dict[str, bool]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.native_solar")
        self._startup = ChargeWiseStartupMonitor()
        self._last_current_command: tuple[float, datetime] | None = None
        self._unloading = False
        self.battery_configured = bool(self.options.get(CONF_BATTERY_POWER_ENTITY))
        self.ev_connected_configured = bool(charger_status_source(self.options))
        self.charger_observation = ChargerObservation()
        self._charging_power_detector = ChargingPowerDetector()
        self._under_drawing_detector = EvUnderDrawingDetector()
        self.house_load = HouseLoadProfile(
            float(self.options.get(CONF_HOUSE_LOAD_WINDOW_DAYS, DEFAULT_HOUSE_LOAD_WINDOW_DAYS)),
        )
        self._house_load_store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.house_load")
        self._ev_first_store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.ev_first")
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
            settle_hold_s=int(self.options.get(CONF_SETTLE_HOLD_S, DEFAULT_SETTLE_HOLD_S)),
            smoothing_window_s=int(self.options.get(CONF_SMOOTHING_WINDOW_S, DEFAULT_SMOOTHING_WINDOW_S)),
        )
        self.controller = ChargeWiseController(self._config)
        self._last_logged_decision: tuple[bool, ChargeWiseReason, float] | None = None

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
            offpeak_mode="off",
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
                CONF_CHARGER_CURRENT_ENTITY,
                CONF_CHARGER_POWER_ENTITY,
                CONF_CHARGER_STATUS_ENTITY,
                CONF_CHARGER_SWITCH_ENTITY,
                CONF_CURRENT_TARGET_ENTITY,
                CONF_HARDWARE_MAXIMUM_ENTITY,
                CONF_BATTERY_POWER_ENTITY,
                CONF_EV_CONNECTED_ENTITY,
                CONF_FORECAST_REMAINING_ENTITY,
                CONF_FORECAST_TODAY_ENTITY,
                CONF_BATTERY_LEVEL_ENTITY,
                CONF_SOLAR_POWER_ENTITY,
                CONF_SOLAR_ENERGY_ENTITY,
                CONF_NATIVE_SOLAR_ENTITY,
            )
            if self.options.get(key)
        }
        if self.ev_first_config is not None:
            entity_ids.add("sun.sun")
            self.house_load.restore(await self._house_load_store.async_load())
            stored = await self._ev_first_store.async_load()
            self._restore_ev_first(stored)
            self.forecast_accuracy.restore(
                (stored or {}).get("accuracy"),
                dt_util.now().date(),
                energy_counter=bool(self.options.get(CONF_SOLAR_ENERGY_ENTITY)),
            )
            await self._async_anchor_accuracy_to_midnight()
        if self.options.get(CONF_NATIVE_SOLAR_ENTITY):
            stored_native = await self._native_battery_store.async_load()
            self._native_full_battery = bool(stored_native and stored_native.get("full") is True)
        self._restore_offpeak(await self._offpeak_store.async_load())
        self._state_unsub = async_track_state_change_event(
            self.hass,
            entity_ids,
            self._handle_state_change,
        )
        await self._async_evaluate()

    async def _async_anchor_accuracy_to_midnight(self) -> None:
        """Start today's accuracy from the energy counter's recorded value at midnight, when it is known."""
        entity_id = self.options.get(CONF_SOLAR_ENERGY_ENTITY)
        tracker = self.forecast_accuracy
        if not entity_id or tracker.baseline_energy_kwh is not None or "recorder" not in self.hass.config.components:
            return
        midnight = dt_util.start_of_local_day()
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                partial(
                    state_changes_during_period,
                    self.hass,
                    midnight,
                    midnight + timedelta(minutes=1),
                    entity_id,
                    limit=1,
                )
            )
        except HomeAssistantError, SQLAlchemyError:
            LOGGER.debug("Could not read %s at midnight from the recorder", entity_id, exc_info=True)
            return
        first = (states.get(entity_id) or [None])[0]
        if first is None or first.last_updated > midnight + timedelta(seconds=1):
            return
        if (energy_kwh := self._state_energy_kwh(first)) is not None:
            tracker.anchor_to_day_start(midnight.date(), energy_kwh)

    async def async_stop(self) -> None:
        """Remove state and timer subscriptions."""
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None
        self._cancel_timer()
        if self.ev_first_config is not None:
            await self._house_load_store.async_save(self.house_load.as_dict())
            await self._ev_first_store.async_save(self._ev_first_as_dict())

    async def async_prepare_unload(self) -> bool:
        """Release native charger control before unloading an entry."""
        entity_id = self.options.get(CONF_NATIVE_SOLAR_ENTITY)
        if not entity_id:
            return True
        self._unloading = True
        changed = asyncio.Event()

        @callback
        def state_changed(_event: Event[EventStateChangedData]) -> None:
            changed.set()

        unsubscribe = async_track_state_change_event(
            self.hass, [entity_id, self.options[CONF_CHARGER_SWITCH_ENTITY]], state_changed
        )
        try:
            async with asyncio.timeout(SWITCH_COMMAND_GRACE_S):
                await self.async_set_switch("enabled", False)
                while not self.native_control_released():
                    changed.clear()
                    await self._async_evaluate()
                    if not self.native_control_released():
                        await changed.wait()
        except TimeoutError:
            LOGGER.error("Cannot unload Charge Wise: charger or native solar mode did not turn off")
            self._unloading = False
            return False
        finally:
            unsubscribe()
        return True

    def async_cancel_unload(self) -> None:
        """Allow charging again if platform unloading fails."""
        self._unloading = False

    def _ev_first_as_dict(self) -> dict[str, Any]:
        """Return the EV-first hold state that must survive a restart."""
        return {
            "date": dt_util.now().date().isoformat(),
            "mode": self.ev_first_mode,
            "until": self._ev_first_until.isoformat() if self._ev_first_until else None,
            "was_active": self._ev_first_was_active,
            "accuracy": self.forecast_accuracy.as_dict(),
        }

    def _restore_ev_first(self, data: dict[str, Any] | None) -> None:
        """Restore recurring mode across days, but never extend a one-time sunset deadline."""
        if not data:
            return
        if data.get("mode") == "on":
            self.ev_first_mode = "on"
        elif data.get("mode") == "on_once":
            value = data.get("until")
            until = dt_util.parse_datetime(value) if isinstance(value, str) else None
            now = dt_util.utcnow()
            if (
                until is not None
                and until.tzinfo is not None
                and until > now
                and dt_util.as_local(until).date() == dt_util.as_local(now).date()
            ):
                self.ev_first_mode = "on_once"
                self._ev_first_until = until
        if self.ev_first_mode != "off":
            self.controller.start_cooldown(dt_util.utcnow())
            if data.get("date") == dt_util.now().date().isoformat():
                self._ev_first_was_active = bool(data.get("was_active", False))

    def _reset_ev_first(self) -> None:
        """Forget the EV-first hold state."""
        self._ev_first_was_active = False

    async def async_set_switch(self, key: SwitchKey, value: bool, *, restoring: bool = False) -> None:
        """Turn a charging source on or off; a restored source waits through the safety cooldown."""
        if self._unloading and key == "enabled" and value:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="charger_unloading")
        if key == "enabled" and not value:
            self._startup.reset()
            self._last_current_command = None
            self._last_switch_command = None
        self.switches[key] = value
        if not restoring and key == "solar_enabled" and not value:
            self._reset_ev_first()
        if restoring and value:
            self.controller.start_cooldown(dt_util.utcnow())
        await self._async_evaluate()

    async def async_set_ev_first_mode(self, mode: str) -> None:
        """Select recurring EV-first sharing or sharing until today's sunset."""
        if mode not in {"off", "on", "on_once"}:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_ev_first_mode")
        if mode != "off" and self.ev_first_config is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="ev_first_not_configured")
        async with self._evaluation_lock:
            until = None
            if mode == "on_once":
                sun = self.hass.states.get("sun.sun")
                value = sun.attributes.get("next_setting") if sun is not None else None
                until = dt_util.parse_datetime(value) if isinstance(value, str) else None
                now = dt_util.utcnow()
                if (
                    sun is None
                    or sun.state not in {"above_horizon", "below_horizon"}
                    or until is None
                    or until.tzinfo is None
                    or until <= now
                    or dt_util.as_local(until).date() != dt_util.as_local(now).date()
                ):
                    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="ev_first_sunset_required")
            self.ev_first_mode = mode
            self._ev_first_until = until
            self._reset_ev_first()
            await self._ev_first_store.async_save(self._ev_first_as_dict())
            await self._async_evaluate_locked()

    def _restore_offpeak(self, stored: dict[str, Any] | None) -> None:
        """Restore the selected mode without extending a one-time request."""
        if not stored:
            return
        mode = stored.get("mode")
        if mode == "on":
            self.offpeak_mode = "on"
        elif mode == "on_once":
            value = stored.get("until")
            until = dt_util.parse_datetime(value) if isinstance(value, str) else None
            if until is not None and until.tzinfo is not None and until > dt_util.utcnow():
                self.offpeak_mode = "on_once"
                self._offpeak_until = until
        if self.offpeak_mode != "off":
            self.controller.start_cooldown(dt_util.utcnow())

    async def _async_save_offpeak(self) -> None:
        """Persist the mode and its original deadline immediately."""
        await self._offpeak_store.async_save(
            {"mode": self.offpeak_mode, "until": self._offpeak_until.isoformat() if self._offpeak_until else None},
        )

    async def async_set_offpeak_mode(self, mode: str) -> None:
        """Select recurring or one-time off-peak charging."""
        if mode not in {"off", "on", "on_once"}:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_offpeak_mode")
        async with self._evaluation_lock:
            until = next_period_end(self.windows, dt_util.now()) if mode == "on_once" else None
            if mode == "on_once" and until is None:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="offpeak_schedule_required")
            self.offpeak_mode = mode
            self._offpeak_until = until
            await self._async_save_offpeak()
            await self._async_evaluate_locked()

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
        if self._ev_first_until is not None and now >= self._ev_first_until:
            self.ev_first_mode = "off"
            self._ev_first_until = None
            self._reset_ev_first()
            await self._ev_first_store.async_save(self._ev_first_as_dict())
        if self._offpeak_until is not None and now >= self._offpeak_until:
            self.offpeak_mode = "off"
            self._offpeak_until = None
            await self._async_save_offpeak()
        self._observe_house_load(now)
        offpeak_active = (self.offpeak_mode != "off") and is_active(self.windows, local_now)
        settings = ControlSettings(
            enabled=self.switches["enabled"],
            solar_enabled=self.switches["solar_enabled"],
            offpeak_enabled=(self.offpeak_mode != "off"),
            manual_override=self.switches["manual_override"],
            manual_current_a=self.manual_current_a,
            offpeak_current_a=self.offpeak_current_a,
            offpeak_active=offpeak_active,
            offpeak_next_change=next_change(self.windows, local_now),
        )
        self._observe_forecast_accuracy(now)
        ev_first_result = self._ev_first_result(now)
        ev_first_active = self._ev_first_enabled() and ev_first_result is not None and ev_first_result.active
        battery_level = self._number_value(self.options.get(CONF_BATTERY_LEVEL_ENTITY))
        was_full = self._native_full_battery
        if battery_level is not None:
            if battery_level < float(
                self.options.get(CONF_NATIVE_SOLAR_RELEASE_PERCENT, DEFAULT_NATIVE_SOLAR_RELEASE_PERCENT)
            ):
                self._native_full_battery = False
            elif battery_level >= 100:
                self._native_full_battery = True
        if self.options.get(CONF_NATIVE_SOLAR_ENTITY) and was_full != self._native_full_battery:
            await self._native_battery_store.async_save({"full": self._native_full_battery})
        settings = replace(
            settings,
            native_solar=bool(
                self.options.get(CONF_NATIVE_SOLAR_ENTITY)
                and settings.solar_enabled
                and (not ev_first_active or (battery_level is not None and self._native_full_battery))
            ),
        )
        if self._ev_first_enabled():
            self._ev_first_was_active = ev_first_active
        self._ev_first_store.async_delay_save(self._ev_first_as_dict, _HOUSE_LOAD_SAVE_DELAY_S)
        readings = self._read_inputs(
            ev_first_active=ev_first_active,
            battery_reserve_w=ev_first_result.battery_reserve_w if ev_first_result else None,
        )
        decision = self.controller.evaluate(settings, readings, now)
        already_failed = self._startup.failed
        was_not_drawing = self._startup.not_drawing
        if self._startup.update(
            now,
            requested=decision.charger_enabled,
            native_solar=decision.reason is ChargeWiseReason.NATIVE_SOLAR,
            target_a=decision.requested_current_a,
            observed_a=readings.current_target_a,
            switch_on=readings.charger_enabled,
            charging=self.charger_observation.charging,
            session=self.charger_observation.session,
        ):
            if not already_failed:
                LOGGER.error("Charger did not confirm its current limit or start command")
            decision = replace(
                decision,
                status=ControllerStatus.ERROR,
                reason=ChargeWiseReason.CONTROL_FAILED,
                charger_enabled=False,
                requested_current_a=0.0,
                next_update_at=None,
            )
        elif self._startup.not_drawing:
            if not was_not_drawing:
                LOGGER.warning("Charger accepted charging commands but is not drawing power; charging remains enabled")
            decision = replace(decision, status=ControllerStatus.ERROR, reason=ChargeWiseReason.CONTROL_FAILED)
        elif was_not_drawing:
            LOGGER.info("Charger no-power condition cleared")
        self._log_decision_change(decision, readings)
        next_start_at = next_start(self.windows, local_now) if (self.offpeak_mode != "off") else None
        try:
            applied = await self._async_apply_decision(decision)
            self._startup.confirm_commands(
                target_a=decision.requested_current_a,
                observed_a=self._number_value(self.options[CONF_CURRENT_TARGET_ENTITY]),
                switch_on=self._entity_is_on(self.options[CONF_CHARGER_SWITCH_ENTITY]),
            )
        except HomeAssistantError:
            self._startup.fail()
            self._last_native_current_command = None
            LOGGER.exception("Failed to apply charger control decision")
            await self._async_fail_safe()
            self.async_set_updated_data(
                self._snapshot(
                    decision,
                    offpeak_active,
                    next_start_at,
                    ev_first_active,
                    ev_first_result,
                    status=ControllerStatus.ERROR,
                    reason=ChargeWiseReason.CONTROL_FAILED,
                    requested_current_a=0.0,
                ),
            )
            self._schedule_timer(decision)
            return

        if not applied:
            decision = replace(
                decision,
                status=ControllerStatus.WAITING,
                charger_enabled=False,
                requested_current_a=0.0,
                next_update_at=min(
                    deadline
                    for deadline in (decision.next_update_at, now + timedelta(seconds=SWITCH_COMMAND_GRACE_S))
                    if deadline is not None
                ),
            )
        self.async_set_updated_data(
            self._snapshot(decision, offpeak_active, next_start_at, ev_first_active, ev_first_result),
        )
        self._schedule_timer(decision)

    def _snapshot(
        self,
        decision: ControllerDecision,
        offpeak_active: bool,
        next_offpeak_start: datetime | None,
        ev_first_active: bool,
        ev_first_result: EvFirstResult | None,
        *,
        status: ControllerStatus | None = None,
        reason: ChargeWiseReason | None = None,
        requested_current_a: float | None = None,
    ) -> ChargeWiseSnapshot:
        """Combine a controller decision with user switches for entities."""
        measured_id = self.options.get(CONF_CHARGER_CURRENT_ENTITY)
        measured_state = self.hass.states.get(measured_id) if measured_id else None
        measured_a = (
            self._number_value(measured_id)
            if measured_state is not None
            and measured_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfElectricCurrent.AMPERE
            else None
        )
        offered_a = self._number_value(self.options[CONF_CURRENT_TARGET_ENTITY])
        if offered_a is not None:
            offered_a = min(offered_a, decision.requested_current_a)
        under_drawing = self._under_drawing_detector.update(
            dt_util.utcnow(),
            charging=(
                decision.charger_enabled
                and status != ControllerStatus.ERROR
                and self._entity_is_on(self.options[CONF_CHARGER_SWITCH_ENTITY])
                and self.charger_observation.charging is True
                and self.charger_observation.connected is not False
            ),
            offered_a=offered_a,
            measured_a=measured_a,
        )
        return ChargeWiseSnapshot(
            offpeak_mode=self.offpeak_mode,
            enabled=self.switches["enabled"],
            solar_enabled=self.switches["solar_enabled"],
            offpeak_enabled=(self.offpeak_mode != "off"),
            manual_override=self.switches["manual_override"],
            ev_first_enabled=self.ev_first_mode != "off",
            ev_first_mode=self.ev_first_mode,
            ev_first_active=ev_first_active,
            offpeak_active=offpeak_active,
            next_offpeak_start=next_offpeak_start,
            status=status or decision.status,
            reason=reason or decision.reason,
            restart_cooldown_end=(
                self.controller.cooldown_until if (reason or decision.reason) is ChargeWiseReason.COOLDOWN else None
            ),
            available_solar_w=(
                decision.available_solar_w
                if decision.available_solar_w is not None
                else self._available_solar_budget_w(ev_first_active, ev_first_result)
            ),
            requested_current_a=decision.requested_current_a if requested_current_a is None else requested_current_a,
            manual_current_a=self.manual_current_a,
            offpeak_current_a=self.offpeak_current_a,
            battery_protection_active=decision.battery_protection_active,
            average_house_load_w=self.house_load.overall_w,
            house_load_w=self._house_power_w(),
            battery_need_kwh=ev_first_result.battery_need_kwh if ev_first_result else None,
            forecast_surplus_kwh=ev_first_result.forecast_surplus_kwh if ev_first_result else None,
            vehicle_connected=self.charger_observation.connected,
            vehicle_charging=self.charger_observation.charging,
            ev_under_drawing=under_drawing,
            charger_session=self.charger_observation.session,
            charger_status_profile=self.charger_observation.profile,
            charger_raw_status=self.charger_observation.raw_status,
            charger_connection_source=charger_status_source(self.options),
            charger_charging_source=self.options.get(CONF_CHARGER_POWER_ENTITY)
            or self.options.get(CONF_CHARGER_STATUS_ENTITY),
            forecast_accuracy_percent=self._accuracy_percent(),
            forecast_accuracy_actual_kwh=self.forecast_accuracy.actual_kwh,
            forecast_accuracy_forecast_kwh=self.forecast_accuracy.tracked_forecast_kwh,
        )

    def _accuracy_percent(self) -> float | None:
        """Return the measured forecast accuracy in percent, or None while it is unknown."""
        ratio = self.forecast_accuracy.ratio
        return None if ratio is None else ratio * 100

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

    def _available_solar_budget_w(
        self,
        ev_first_active: bool,
        ev_first_result: EvFirstResult | None = None,
    ) -> float | None:
        """Return the same battery-aware budget used for Solar charging decisions."""
        return solar_budget_w(
            self._read_inputs(
                ev_first_active=ev_first_active,
                battery_reserve_w=ev_first_result.battery_reserve_w if ev_first_result else None,
            )
        )

    def _read_inputs(
        self,
        *,
        ev_first_active: bool = False,
        battery_reserve_w: float | None = None,
    ) -> ControllerInput:
        """Read and normalize the currently configured Home Assistant entities."""
        battery_power = self._battery_discharge_w()

        self.charger_observation = self._read_charger_observation()
        ev_connected = self.charger_observation.connected

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
            ev_first_blocked=self._ev_first_enabled() and not ev_first_active,
            battery_reserve_w=battery_reserve_w,
        )

    def _observe_forecast_accuracy(self, now: datetime) -> None:
        """Feed solar production and the forecast so far into the accuracy tracker."""
        if self.ev_first_config is None:
            return
        total = self._energy_kwh(self.options.get(CONF_FORECAST_TODAY_ENTITY))
        remaining = self._energy_kwh(self.options.get(CONF_FORECAST_REMAINING_ENTITY))
        forecast_so_far = None if total is None or remaining is None else max(0.0, total - remaining)
        self.forecast_accuracy.observe(
            dt_util.as_local(now),
            self._power_w(self.options.get(CONF_SOLAR_POWER_ENTITY)),
            forecast_so_far,
            self._energy_kwh(self.options.get(CONF_SOLAR_ENERGY_ENTITY)),
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
            release_margin_percent=float(
                self.options.get(CONF_EV_FIRST_RELEASE_MARGIN_PERCENT, DEFAULT_EV_FIRST_RELEASE_MARGIN_PERCENT),
            ),
        )

    def _read_charger_observation(self) -> ChargerObservation:
        """Combine explicit connection evidence with independently measured activity."""
        source = charger_status_source(self.options)
        state = self.hass.states.get(source) if source else None
        profile = self.options.get(CONF_CHARGER_STATUS_PROFILE, "auto")
        if not self.options.get(CONF_CHARGER_STATUS_ENTITY):
            profile = "ocpp"
        if source and source.startswith("binary_sensor."):
            raw = state.state if state is not None else None
            connected = True if raw == STATE_ON else False if raw == STATE_OFF else None
            observation = ChargerObservation(connected=connected, profile="binary", raw_status=raw)
        else:
            if profile == "auto":
                registered = er.async_get(self.hass).async_get(source) if source else None
                profile = registered.platform if registered is not None else "unknown"
            observation = classify_status(state.state if state is not None else None, profile, self.options)
        if power_entity := self.options.get(CONF_CHARGER_POWER_ENTITY):
            observation = replace(
                observation, charging=self._charging_power_detector.update(self._power_w(power_entity))
            )
        return observation

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
            if setting is not None and setting.tzinfo is not None:
                hours_until_sunset = (setting - now).total_seconds() / 3600
                if instant_w is not None or self.house_load.overall_w is not None:
                    house_use_kwh = self.house_load.expected_energy_kwh(
                        dt_util.as_local(now),
                        dt_util.as_local(setting),
                        instant_w if instant_w is not None else 0.0,
                    )
        return evaluate_ev_first(
            self.ev_first_config,
            was_active=self._ev_first_was_active,
            inputs=EvFirstInputs(
                forecast_remaining_kwh=self._energy_kwh(self.options.get(CONF_FORECAST_REMAINING_ENTITY)),
                battery_level_percent=self._number_value(self.options.get(CONF_BATTERY_LEVEL_ENTITY)),
                house_use_kwh=house_use_kwh,
                hours_until_sunset=hours_until_sunset,
                forecast_accuracy=self.forecast_accuracy.ratio or 1.0,
            ),
        )

    def _ev_first_enabled(self) -> bool:
        """Return whether the user allows the EV to share the battery's charging power."""
        return self.ev_first_mode != "off" and self.switches["solar_enabled"]

    def _energy_kwh(self, entity_id: str | None) -> float | None:
        """Return a finite energy reading converted to kWh."""
        if entity_id is None:
            return None
        return self._state_energy_kwh(self.hass.states.get(entity_id))

    @staticmethod
    def _state_energy_kwh(state: State | None) -> float | None:
        """Return a finite energy state converted to kWh."""
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
        factor = POWER_TO_W.get(unit)
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

    def native_control_released(self) -> bool:
        """Return whether the configured native control can safely be replaced or removed."""
        entity_id = self.options.get(CONF_NATIVE_SOLAR_ENTITY)
        if not entity_id:
            return True
        native_state = self.hass.states.get(entity_id)
        charger_state = self.hass.states.get(self.options[CONF_CHARGER_SWITCH_ENTITY])
        return (
            not self.switches["enabled"]
            and self._last_native_command is None
            and native_state is not None
            and native_state.state == self.options[CONF_NATIVE_SOLAR_OFF_OPTION]
            and charger_state is not None
            and charger_state.state == STATE_OFF
        )

    def _log_decision_change(self, decision: ControllerDecision, readings: ControllerInput) -> None:
        """Log, at debug level, each change of charger state, reason or requested current."""
        key = (decision.charger_enabled, decision.reason, decision.requested_current_a)
        if key == self._last_logged_decision:
            return
        self._last_logged_decision = key
        LOGGER.debug(
            "Decision: enabled=%s status=%s reason=%s request=%.1fA available=%s W grid=%s W "
            "charger=%s W battery_discharge=%s W charger_on=%s current=%s A next_update=%s",
            decision.charger_enabled,
            decision.status,
            decision.reason,
            decision.requested_current_a,
            decision.available_solar_w,
            readings.grid_power_w,
            readings.charger_power_w,
            readings.battery_discharge_w,
            readings.charger_enabled,
            readings.current_target_a,
            decision.next_update_at,
        )

    async def _async_apply_decision(self, decision: ControllerDecision) -> bool:
        """Apply current limit before enabling the charger; stop immediately when unsafe."""
        switch_entity = self.options[CONF_CHARGER_SWITCH_ENTITY]
        switch_state = self.hass.states.get(switch_entity)

        if self.options.get(CONF_NATIVE_SOLAR_ENTITY):
            native = decision.charger_enabled and decision.reason is ChargeWiseReason.NATIVE_SOLAR
            if not await self._async_set_native_solar(native):
                return False
            switch_state = self.hass.states.get(switch_entity)

        if not decision.charger_enabled:
            if (switch_state is None or switch_state.state != STATE_OFF) and self._switch_command_due(False):
                await self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    {ATTR_ENTITY_ID: switch_entity},
                    blocking=True,
                )
            return True

        if decision.reason is not ChargeWiseReason.NATIVE_SOLAR:
            current_entity = self.options[CONF_CURRENT_TARGET_ENTITY]
            current_state = self._number_value(current_entity)
            current_object = self.hass.states.get(current_entity)
            current_unavailable = current_object is None or current_object.state == STATE_UNAVAILABLE
            registered = er.async_get(self.hass).async_get(current_entity)
            ocpp_session = self.charger_observation.profile == "ocpp" or (
                registered is not None and registered.platform == "ocpp"
            )
            if current_unavailable and not ocpp_session:
                if self._entity_is_on(switch_entity):
                    await self._async_fail_safe()
                return False
            if not current_unavailable and (
                current_state is None or not isclose(current_state, decision.requested_current_a, abs_tol=0.01)
            ):
                now = dt_util.utcnow()
                command = self._last_current_command
                if (
                    command is None
                    or command[0] != decision.requested_current_a
                    or now - command[1] >= COMMAND_CONFIRMATION
                ):
                    self._last_current_command = (decision.requested_current_a, now)
                    self._startup.current_requested(now)
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {ATTR_ENTITY_ID: current_entity, "value": decision.requested_current_a},
                        blocking=True,
                    )
                confirmed = self._number_value(current_entity)
                if confirmed is None or not isclose(confirmed, decision.requested_current_a, abs_tol=0.01):
                    if self._entity_is_on(switch_entity):
                        await self._async_fail_safe()
                    return False
            if not current_unavailable:
                self._last_current_command = None

        if (switch_state is None or switch_state.state != STATE_ON) and self._switch_command_due(True):
            if decision.reason is not ChargeWiseReason.NATIVE_SOLAR:
                self._startup.start_requested(dt_util.utcnow())
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {ATTR_ENTITY_ID: switch_entity},
                blocking=True,
            )
        return not current_unavailable if decision.reason is not ChargeWiseReason.NATIVE_SOLAR else True

    async def _async_set_native_solar(self, enabled: bool) -> bool:
        """Stop the charger while changing ownership, then wait for the mode to be confirmed."""
        if not enabled:
            self._last_native_current_command = None
        entity_id = self.options[CONF_NATIVE_SOLAR_ENTITY]
        state = self.hass.states.get(entity_id)
        option = self.options[CONF_NATIVE_SOLAR_OPTION if enabled else CONF_NATIVE_SOLAR_OFF_OPTION]
        if state is None or state.state in ("unknown", STATE_UNAVAILABLE):
            raise HomeAssistantError(f"Native solar control {entity_id} is unavailable")
        if option not in state.attributes.get("options", []):
            raise HomeAssistantError(f"Native solar option is unavailable for {entity_id}")
        if self._last_native_command is not None:
            pending_option, sent_at = self._last_native_command
            if state.state == pending_option:
                self._last_native_command = None
            elif (dt_util.utcnow() - sent_at).total_seconds() >= SWITCH_COMMAND_GRACE_S:
                raise HomeAssistantError(f"Native solar control {entity_id} did not confirm its last command")
            else:
                await self._async_stop_for_native_change()
                return False
        if state.state == option:
            return True

        if enabled and not await self._async_prepare_native_current():
            return False

        if not await self._async_stop_for_native_change():
            return False

        now = dt_util.utcnow()
        self._last_native_command = (option, now)
        await self.hass.services.async_call(
            "select", "select_option", {ATTR_ENTITY_ID: entity_id, "option": option}, blocking=True
        )
        state = self.hass.states.get(entity_id)
        if state is not None and state.state == option:
            self._last_native_command = None
            return True
        return False

    async def _async_prepare_native_current(self) -> bool:
        """Confirm the native current limit once per target within a fixed response window."""
        entity_id = self.options[CONF_CURRENT_TARGET_ENTITY]
        current = self._number_value(entity_id)
        maximum = self.maximum_current_a
        now = dt_util.utcnow()
        command = self._last_native_current_command
        if current is None or (
            command is not None
            and now - command[1] >= COMMAND_CONFIRMATION
            and not isclose(current, maximum, abs_tol=0.01)
        ):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="native_current_confirmation_failed",
                translation_placeholders={"entity_id": entity_id},
            )
        if not isclose(current, maximum, abs_tol=0.01):
            if command is None or command[0] != maximum:
                self._last_native_current_command = (maximum, command[1] if command else now)
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {ATTR_ENTITY_ID: entity_id, "value": maximum},
                    blocking=True,
                )
            current = self._number_value(entity_id)
            if current is None or not isclose(current, maximum, abs_tol=0.01):
                if self._entity_is_on(self.options[CONF_CHARGER_SWITCH_ENTITY]):
                    await self._async_fail_safe()
                return False
        self._last_native_current_command = None
        return True

    async def _async_stop_for_native_change(self) -> bool:
        """Stop charging and confirm it is stopped before changing charger control."""
        switch_entity = self.options[CONF_CHARGER_SWITCH_ENTITY]
        switch = self.hass.states.get(switch_entity)
        if switch is None or switch.state != STATE_OFF:
            if self._switch_command_due(False):
                await self.hass.services.async_call(
                    "switch", "turn_off", {ATTR_ENTITY_ID: switch_entity}, blocking=True
                )
            switch = self.hass.states.get(switch_entity)
            if switch is None or switch.state != STATE_OFF:
                return False
        return True

    def _switch_command_due(self, turn_on: bool) -> bool:
        """Return False while an identical command is still waiting for the charger to report back."""
        now = dt_util.utcnow()
        last = self._last_switch_command
        if last is not None and last[0] == turn_on and (now - last[1]).total_seconds() < SWITCH_COMMAND_GRACE_S:
            return False
        self._last_switch_command = (turn_on, now)
        return True

    async def _async_fail_safe(self) -> None:
        """Try to disable charging after a failed target or switch command."""
        switch_entity = self.options[CONF_CHARGER_SWITCH_ENTITY]
        state = self.hass.states.get(switch_entity)
        if state is not None and state.state == STATE_OFF:
            return
        self._last_switch_command = (False, dt_util.utcnow())
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
        deadlines = [
            value
            for value in (
                decision.next_update_at,
                self._offpeak_until,
                self._ev_first_until,
                self._under_drawing_detector.next_update_at,
                self._startup.next_update_at,
                self._last_native_current_command[1] + COMMAND_CONFIRMATION
                if self._last_native_current_command is not None
                else None,
            )
            if value is not None
        ]
        if not deadlines:
            return
        delay = max(0.0, (min(deadlines) - dt_util.utcnow()).total_seconds())
        if delay:
            self._timer_unsub = async_call_later(self.hass, delay, self._handle_timer)

    def _cancel_timer(self) -> None:
        """Cancel the pending controller timer, if any."""
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None
