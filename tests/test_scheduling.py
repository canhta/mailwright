import pytest

from mailwright.poller.scheduling import humanize_seconds, parse_duration, should_poll_now


def test_should_poll_now_when_never_polled():
    assert should_poll_now(interval_seconds=300, paused=False, last_poll_at=None, now=1000) is True


def test_should_not_poll_when_paused_even_if_never_polled():
    assert should_poll_now(interval_seconds=300, paused=True, last_poll_at=None, now=1000) is False


def test_should_not_poll_before_interval_elapsed():
    assert should_poll_now(interval_seconds=300, paused=False, last_poll_at=900, now=1100) is False


def test_should_poll_once_interval_elapsed():
    assert should_poll_now(interval_seconds=300, paused=False, last_poll_at=900, now=1200) is True


def test_should_not_poll_when_paused_and_interval_elapsed():
    assert should_poll_now(interval_seconds=300, paused=True, last_poll_at=900, now=1200) is False


def test_parse_duration_bare_seconds():
    assert parse_duration("300") == 300


def test_parse_duration_seconds_suffix():
    assert parse_duration("45s") == 45


def test_parse_duration_minutes_suffix():
    assert parse_duration("5m") == 300


def test_parse_duration_hours_suffix():
    assert parse_duration("2h") == 7200


def test_parse_duration_rejects_garbage():
    with pytest.raises(ValueError):
        parse_duration("banana")


def test_parse_duration_rejects_zero_or_negative():
    with pytest.raises(ValueError):
        parse_duration("0")
    with pytest.raises(ValueError):
        parse_duration("-5m")


def test_humanize_seconds_under_a_minute():
    assert humanize_seconds(45) == "45s"


def test_humanize_seconds_whole_minutes():
    assert humanize_seconds(300) == "5m"


def test_humanize_seconds_minutes_and_seconds():
    assert humanize_seconds(90) == "1m30s"


def test_humanize_seconds_whole_hours():
    assert humanize_seconds(7200) == "2h"
