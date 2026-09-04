"""S_time is NULL below 20 timestamps; never silently 0."""

from src.temporal.activity import MIN_TS, hour_histogram, s_time, timezone_estimate


def test_s_time_null_below_floor_and_real_at_floor():
    thin_hist = None
    thick = hour_histogram([12] * MIN_TS)
    assert s_time(thin_hist, thick) is None
    val = s_time(thick, thick)
    assert val is not None
    assert val > 0.99


def test_s_time_missing_is_none_not_zero():
    assert s_time(None, hour_histogram([3] * 30)) is None


def test_timezone_estimate_skips_thin_aliases():
    assert timezone_estimate(list(range(10))) is None
    est = timezone_estimate([20] * 30)
    assert est is not None
    assert "Not a location claim" in est["wording"]
    assert est["tz_confidence"] > 0.9
