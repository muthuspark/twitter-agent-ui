import os
from dataclasses import dataclass
from typing import Any


class AnalyticsConfigurationError(Exception):
    pass


class AnalyticsDataError(Exception):
    pass


@dataclass(frozen=True)
class AnalyticsSummary:
    start_date: str
    end_date: str
    metrics: dict[str, int | float]
    acquisition: list[dict[str, Any]]
    pages: list[dict[str, Any]]
    campaigns: list[dict[str, Any]]
    landing_pages: list[dict[str, Any]]
    funnel_events: list[dict[str, Any]]
    recommendations: list[str]


def _metric_value(row: Any, index: int) -> int | float:
    raw = row.metric_values[index].value
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return 0
    if number.is_integer():
        return int(number)
    return round(number, 2)


def _dimension_value(row: Any, index: int, fallback: str = "(not set)") -> str:
    try:
        value = row.dimension_values[index].value
    except (AttributeError, IndexError):
        return fallback
    return value or fallback


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0
    return round(float(numerator) / float(denominator), 4)


def _run_report(client: Any, property_id: str, request_factory: Any, **kwargs: Any) -> Any:
    return client.run_report(request_factory(property=f"properties/{property_id}", **kwargs))


def _build_recommendations(
    metrics: dict[str, int | float],
    campaigns: list[dict[str, Any]],
    landing_pages: list[dict[str, Any]],
    funnel_events: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    sessions = int(metrics.get("sessions") or 0)
    conversions = int(metrics.get("conversions") or 0)
    if sessions and not conversions:
        recommendations.append("No conversions are recorded yet. Define signup, demo, and activation events as key events in GA4.")

    direct_sessions = sum(row["sessions"] for row in campaigns if row["sourceMedium"].lower() == "(direct) / (none)")
    if sessions and _rate(direct_sessions, sessions) >= 0.35:
        recommendations.append("Direct traffic is high. Add UTM links to posts, replies, newsletters, and partner links before judging channel quality.")

    named_campaigns = [row for row in campaigns if row["campaign"] not in {"(not set)", "(organic)", "(referral)"}]
    if not named_campaigns:
        recommendations.append("No named campaigns are visible. Start tagging every marketing link with utm_source, utm_medium, utm_campaign, and utm_content.")

    if landing_pages:
        best_page = max(landing_pages, key=lambda row: (row["conversions"], row["sessions"]))
        if best_page["sessions"] and best_page["conversions"] == 0:
            recommendations.append(f"{best_page['landingPage']} is getting traffic but no conversions. Review the page CTA and signup path.")

    event_names = {row["eventName"] for row in funnel_events}
    expected_events = {"sign_up", "login", "generate_lead", "purchase", "first_visit"}
    if event_names and not (event_names & expected_events):
        recommendations.append("Funnel events are mostly generic. Add product events for signup, workspace creation, data connection, and first useful question.")

    if not recommendations:
        recommendations.append("Attribution and conversion tracking are active. Compare campaign conversion rate weekly and double down on the highest-quality source.")
    return recommendations


def fetch_analytics_summary(
    *,
    property_id: str | None = None,
    start_date: str = "28daysAgo",
    end_date: str = "yesterday",
    limit: int = 8,
) -> AnalyticsSummary:
    resolved_property_id = property_id or os.environ.get("GA4_PROPERTY_ID", "").strip()
    if not resolved_property_id:
        raise AnalyticsConfigurationError("GA4_PROPERTY_ID is not configured")

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
    except ImportError as exc:
        raise AnalyticsConfigurationError(
            "google-analytics-data is not installed. Run: pip install -r backend/requirements.txt"
        ) from exc

    try:
        client = BetaAnalyticsDataClient()
        date_ranges = [DateRange(start_date=start_date, end_date=end_date)]
        summary_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            metrics=[
                Metric(name="activeUsers"),
                Metric(name="sessions"),
                Metric(name="screenPageViews"),
                Metric(name="conversions"),
                Metric(name="engagementRate"),
            ],
        )
        acquisition_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions"), Metric(name="activeUsers"), Metric(name="conversions")],
            limit=limit,
        )
        pages_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="screenPageViews"), Metric(name="activeUsers"), Metric(name="conversions")],
            limit=limit,
        )
        campaign_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            dimensions=[Dimension(name="sessionSourceMedium"), Dimension(name="sessionCampaignName")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers"),
                Metric(name="conversions"),
                Metric(name="engagementRate"),
            ],
            limit=limit,
        )
        landing_page_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            dimensions=[Dimension(name="landingPagePlusQueryString")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="activeUsers"),
                Metric(name="conversions"),
                Metric(name="engagementRate"),
            ],
            limit=limit,
        )
        funnel_response = _run_report(
            client,
            resolved_property_id,
            RunReportRequest,
            date_ranges=date_ranges,
            dimensions=[Dimension(name="eventName")],
            metrics=[Metric(name="eventCount"), Metric(name="activeUsers"), Metric(name="conversions")],
            limit=limit,
        )
    except Exception as exc:
        raise AnalyticsDataError(f"Google Analytics Data API request failed: {exc}") from exc

    summary_row = summary_response.rows[0] if summary_response.rows else None
    metrics = {
        "activeUsers": _metric_value(summary_row, 0) if summary_row else 0,
        "sessions": _metric_value(summary_row, 1) if summary_row else 0,
        "screenPageViews": _metric_value(summary_row, 2) if summary_row else 0,
        "conversions": _metric_value(summary_row, 3) if summary_row else 0,
        "engagementRate": _metric_value(summary_row, 4) if summary_row else 0,
    }

    acquisition = [
        {
            "channel": _dimension_value(row, 0),
            "sessions": _metric_value(row, 0),
            "activeUsers": _metric_value(row, 1),
            "conversions": _metric_value(row, 2),
            "conversionRate": _rate(_metric_value(row, 2), _metric_value(row, 0)),
        }
        for row in acquisition_response.rows
    ]
    pages = [
        {
            "path": _dimension_value(row, 0, "/"),
            "views": _metric_value(row, 0),
            "activeUsers": _metric_value(row, 1),
            "conversions": _metric_value(row, 2),
            "conversionRate": _rate(_metric_value(row, 2), _metric_value(row, 0)),
        }
        for row in pages_response.rows
    ]
    campaigns = [
        {
            "sourceMedium": _dimension_value(row, 0),
            "campaign": _dimension_value(row, 1),
            "sessions": _metric_value(row, 0),
            "activeUsers": _metric_value(row, 1),
            "conversions": _metric_value(row, 2),
            "engagementRate": _metric_value(row, 3),
            "conversionRate": _rate(_metric_value(row, 2), _metric_value(row, 0)),
        }
        for row in campaign_response.rows
    ]
    landing_pages = [
        {
            "landingPage": _dimension_value(row, 0, "/"),
            "sessions": _metric_value(row, 0),
            "activeUsers": _metric_value(row, 1),
            "conversions": _metric_value(row, 2),
            "engagementRate": _metric_value(row, 3),
            "conversionRate": _rate(_metric_value(row, 2), _metric_value(row, 0)),
        }
        for row in landing_page_response.rows
    ]
    funnel_events = [
        {
            "eventName": _dimension_value(row, 0),
            "eventCount": _metric_value(row, 0),
            "activeUsers": _metric_value(row, 1),
            "conversions": _metric_value(row, 2),
        }
        for row in funnel_response.rows
    ]

    return AnalyticsSummary(
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
        acquisition=acquisition,
        pages=pages,
        campaigns=campaigns,
        landing_pages=landing_pages,
        funnel_events=funnel_events,
        recommendations=_build_recommendations(metrics, campaigns, landing_pages, funnel_events),
    )
