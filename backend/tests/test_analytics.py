from app.analytics import AnalyticsConfigurationError, fetch_analytics_summary


def test_fetch_analytics_summary_requires_property_id(monkeypatch):
    monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)

    try:
        fetch_analytics_summary()
    except AnalyticsConfigurationError as exc:
        assert str(exc) == "GA4_PROPERTY_ID is not configured"
    else:
        raise AssertionError("Expected AnalyticsConfigurationError")
