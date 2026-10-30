"""Tests for the learned house consumption profile."""

from datetime import UTC, datetime, timedelta

from custom_components.charge_wise.utils.house_load import HouseLoadProfile

START = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)


def test_first_reading_seeds_the_average() -> None:
    """The current reading is the estimate until there is history."""
    profile = HouseLoadProfile(3)
    profile.observe(800, START)

    assert profile.overall_w == 800
    assert profile.expected_energy_kwh(START, START + timedelta(hours=2), 800) == 1.6


def test_average_adapts_towards_new_readings() -> None:
    """Held readings pull the hour and overall averages toward them, longer holds more."""
    profile = HouseLoadProfile(3)
    profile.observe(500, START)
    profile.observe(1500, START + timedelta(minutes=30))
    profile.observe(1500, START + timedelta(hours=3))

    assert profile.overall_w is not None
    assert 500 < profile.overall_w < 1500
    hour_ten = profile.hourly_w[10]
    assert hour_ten is not None
    assert 500 < hour_ten < 1500


def test_unseen_hours_use_the_overall_average() -> None:
    """Hours without data fall back to the overall average, then to the supplied reading."""
    profile = HouseLoadProfile(3)
    assert profile.expected_energy_kwh(START, START + timedelta(hours=1), 600) == 0.6

    profile.observe(1000, START)
    profile.observe(1000, START + timedelta(minutes=10))
    assert profile.expected_energy_kwh(START + timedelta(hours=5), START + timedelta(hours=6), 0) == 1


def test_unavailable_reading_pauses_learning() -> None:
    """A gap in readings is not credited to any average."""
    profile = HouseLoadProfile(3)
    profile.observe(1000, START)
    profile.observe(None, START + timedelta(minutes=5))
    profile.observe(5000, START + timedelta(hours=4))

    assert profile.hourly_w[12] is None
    assert profile.overall_w is not None
    assert profile.overall_w == 1000


def test_roundtrip_and_malformed_storage() -> None:
    """Stored averages restore; junk is ignored."""
    profile = HouseLoadProfile(3)
    profile.observe(700, START)
    profile.observe(700, START + timedelta(hours=1))
    restored = HouseLoadProfile(3)
    restored.restore(profile.as_dict())

    assert restored.overall_w == profile.overall_w
    assert restored.hourly_w == profile.hourly_w

    broken = HouseLoadProfile(3)
    broken.restore({"overall_w": "x", "hourly_w": [1]})
    broken.restore(None)
    assert broken.overall_w is None
