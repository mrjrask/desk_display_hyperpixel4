import datetime

import pytz

from utils import timestamp_to_datetime


def test_timestamp_to_datetime_from_epoch():
    tz = pytz.timezone("US/Central")
    dt = timestamp_to_datetime(1_700_000_000, tz)

    assert dt.tzinfo is not None
    assert dt.year == 2023


def test_timestamp_to_datetime_from_iso_string_with_tz():
    tz = pytz.timezone("US/Central")
    dt = timestamp_to_datetime("2024-01-02T03:04:05+00:00", tz)

    assert dt.tzinfo is not None
    assert dt.hour == 21  # previous day in Central Time


def test_timestamp_to_datetime_from_iso_string_z_suffix():
    tz = pytz.timezone("US/Central")
    dt = timestamp_to_datetime("2024-07-04T12:30:00Z", tz)

    assert dt.tzinfo is not None
    assert dt.year == 2024


def test_timestamp_to_datetime_rejects_empty_strings():
    tz = pytz.timezone("US/Central")
    assert timestamp_to_datetime("  ", tz) is None


def test_timestamp_to_datetime_handles_non_numeric_strings():
    tz = pytz.timezone("US/Central")
    assert timestamp_to_datetime("not-a-date", tz) is None
