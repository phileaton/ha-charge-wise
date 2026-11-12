"""Deadline invariants for charger startup monitoring."""

from datetime import datetime, timedelta

from custom_components.charge_wise.utils.charger_startup import ChargeWiseStartupMonitor


def test_changing_targets_does_not_extend_an_unconfirmed_command() -> None:
    """Noisy current requests cannot keep an unresponsive charger alive indefinitely."""
    monitor = ChargeWiseStartupMonitor()
    now = datetime.fromisoformat("2026-11-12T12:00:00+00:00")
    monitor.current_requested(now)
    for elapsed, target in ((0, 10), (20, 12), (29, 14)):
        monitor.current_requested(now + timedelta(seconds=elapsed))
        assert not monitor.update(
            now + timedelta(seconds=elapsed),
            requested=True,
            native_solar=False,
            target_a=target,
            observed_a=6,
            switch_on=True,
            charging=True,
            session=None,
        )
    assert monitor.update(
        now + timedelta(seconds=30),
        requested=True,
        native_solar=False,
        target_a=16,
        observed_a=6,
        switch_on=True,
        charging=True,
        session=None,
    )
    assert monitor.failed
    assert monitor.next_update_at is None


def test_native_solar_has_no_startup_power_deadline() -> None:
    """A charger may wait indefinitely for solar under its own control."""
    monitor = ChargeWiseStartupMonitor()
    now = datetime.fromisoformat("2026-11-12T12:00:00+00:00")
    assert not monitor.update(
        now,
        requested=True,
        native_solar=True,
        target_a=32,
        observed_a=None,
        switch_on=False,
        charging=False,
        session=None,
    )
    assert monitor.next_update_at is None


def test_no_power_grace_begins_when_the_charger_reports_enabled() -> None:
    """Time spent waiting for a start acknowledgement does not shorten the power grace."""
    monitor = ChargeWiseStartupMonitor()
    now = datetime.fromisoformat("2026-11-12T12:00:00+00:00")
    assert not monitor.update(
        now,
        requested=True,
        native_solar=False,
        target_a=32,
        observed_a=32,
        switch_on=False,
        charging=False,
        session=None,
    )
    assert monitor.next_update_at is None
    monitor.start_requested(now)
    assert monitor.next_update_at == now + timedelta(seconds=30)
    assert not monitor.update(
        now + timedelta(seconds=20),
        requested=True,
        native_solar=False,
        target_a=32,
        observed_a=32,
        switch_on=True,
        charging=False,
        session=None,
    )
    assert monitor.next_update_at == now + timedelta(seconds=320)
    assert not monitor.update(
        now + timedelta(seconds=301),
        requested=True,
        native_solar=False,
        target_a=32,
        observed_a=32,
        switch_on=True,
        charging=False,
        session=None,
    )
    assert not monitor.not_drawing
    assert not monitor.update(
        now + timedelta(seconds=320),
        requested=True,
        native_solar=False,
        target_a=32,
        observed_a=32,
        switch_on=True,
        charging=False,
        session=None,
    )
    assert monitor.not_drawing
    assert monitor.next_update_at is None


def test_current_confirmation_waits_until_a_limit_command_is_sent() -> None:
    """A charger ownership handoff may finish before a new current command is sent."""
    monitor = ChargeWiseStartupMonitor()
    now = datetime.fromisoformat("2026-11-12T12:00:00+00:00")
    assert not monitor.update(
        now,
        requested=True,
        native_solar=False,
        target_a=16,
        observed_a=32,
        switch_on=False,
        charging=False,
        session=None,
    )
    assert monitor.next_update_at is None
    monitor.current_requested(now + timedelta(seconds=25))
    assert not monitor.update(
        now + timedelta(seconds=35),
        requested=True,
        native_solar=False,
        target_a=16,
        observed_a=32,
        switch_on=False,
        charging=False,
        session=None,
    )
    assert monitor.next_update_at == now + timedelta(seconds=55)
    assert monitor.update(
        now + timedelta(seconds=55),
        requested=True,
        native_solar=False,
        target_a=16,
        observed_a=32,
        switch_on=False,
        charging=False,
        session=None,
    )
