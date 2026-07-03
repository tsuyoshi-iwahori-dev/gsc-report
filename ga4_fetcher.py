"""
ga4_fetcher.py — GA4 APIから直接データ取得

取得内容:
- 当月のオーガニックセッション数
- 当月のCV数（cv_configに応じてキーイベントor指定イベント）

依存ライブラリ:
  pip install google-analytics-data google-auth
"""

import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
]


def _get_credentials(token_file):
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    # access_token のスコープ不足を避けるため、常に refresh_token でリフレッシュする
    # （Node.js 側と同じパターン: refresh_token のみ信頼し fresh token を取得）
    if creds.refresh_token:
        creds.refresh(Request())
    return creds


def _build_client(creds):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    return BetaAnalyticsDataClient(credentials=creds)


def _get_period():
    """当月1日〜昨日の日付を返す"""
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    first_day = today.replace(day=1)
    # 昨日が先月以前になる場合（月初日に実行した場合）は先月全体を対象にする
    if yesterday < first_day:
        last_month = today - datetime.timedelta(days=1)
        first_day = last_month.replace(day=1)
        yesterday = last_month
    return first_day.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")


def _period_label(start_str, end_str):
    s = datetime.date.fromisoformat(start_str)
    e = datetime.date.fromisoformat(end_str)
    return f"{s.year}年{s.month}月{s.day}日〜{e.month}月{e.day}日"


def _fetch_organic_sessions(client, property_id, start_date, end_date, page_filter=None):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
        FilterExpression, Filter, FilterExpressionList,
    )
    from urllib.parse import urlparse

    organic_filter = FilterExpression(
        filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="Organic Search",
            ),
        )
    )

    if page_filter:
        path_prefix = urlparse(page_filter).path
        page_path_filter = FilterExpression(
            filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.CONTAINS,
                    value=path_prefix,
                ),
            )
        )
        dimension_filter = FilterExpression(
            and_group=FilterExpressionList(expressions=[organic_filter, page_path_filter])
        )
        dimensions = [Dimension(name="sessionDefaultChannelGroup"), Dimension(name="pagePath")]
    else:
        dimension_filter = organic_filter
        dimensions = [Dimension(name="sessionDefaultChannelGroup")]

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=dimensions,
        metrics=[Metric(name="sessions")],
        dimension_filter=dimension_filter,
    )
    response = client.run_report(request)
    total = 0
    for row in response.rows:
        try:
            total += int(row.metric_values[0].value)
        except (ValueError, IndexError):
            pass
    return total


def _build_organic_and_page_filter(page_filter=None):
    """オーガニック絞り込み + オプションのpage_filterをAND結合したFilterExpressionを返す"""
    from google.analytics.data_v1beta.types import (
        FilterExpression, Filter, FilterExpressionList,
    )
    from urllib.parse import urlparse

    organic = FilterExpression(
        filter=Filter(
            field_name="sessionDefaultChannelGroup",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="Organic Search",
            ),
        )
    )
    if not page_filter:
        return organic

    path_prefix = urlparse(page_filter).path
    page_path = FilterExpression(
        filter=Filter(
            field_name="pagePath",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.CONTAINS,
                value=path_prefix,
            ),
        )
    )
    return FilterExpression(
        and_group=FilterExpressionList(expressions=[organic, page_path])
    )


def _fetch_cv_key_events(client, property_id, start_date, end_date, page_filter=None):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )
    dims = [Dimension(name="sessionDefaultChannelGroup")]
    if page_filter:
        dims.append(Dimension(name="pagePath"))

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=dims,
        metrics=[Metric(name="keyEvents")],
        dimension_filter=_build_organic_and_page_filter(page_filter),
    )
    response = client.run_report(request)
    total = 0
    for row in response.rows:
        try:
            total += int(row.metric_values[0].value)
        except (ValueError, IndexError):
            pass
    return total


def _fetch_cv_events(client, property_id, start_date, end_date, event_names, page_filter=None):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
        FilterExpression, Filter, FilterExpressionList,
    )
    # event_names のいずれかに一致するフィルター（OR条件）
    or_filters = [
        FilterExpression(
            filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value=name,
                ),
            )
        )
        for name in event_names
    ]
    event_filter = (
        FilterExpression(or_group=FilterExpressionList(expressions=or_filters))
        if len(or_filters) > 1 else or_filters[0]
    )

    # オーガニック絞り込みとAND結合
    organic = _build_organic_and_page_filter(page_filter)
    dimension_filter = FilterExpression(
        and_group=FilterExpressionList(expressions=[organic, event_filter])
    )

    dims = [Dimension(name="sessionDefaultChannelGroup"), Dimension(name="eventName")]
    if page_filter:
        dims.append(Dimension(name="pagePath"))

    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=dims,
        metrics=[Metric(name="eventCount")],
        dimension_filter=dimension_filter,
    )
    response = client.run_report(request)
    total = 0
    for row in response.rows:
        try:
            total += int(row.metric_values[0].value)
        except (ValueError, IndexError):
            pass
    return total


def _fetch_organic_sessions_by_page(client, property_id, start_date, end_date, top_n=100):
    """ページ単位のオーガニックセッション数を取得（降順TOP N）"""
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
        FilterExpression, Filter, OrderBy,
    )
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="sessions")],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="sessionDefaultChannelGroup",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value="Organic Search",
                ),
            )
        ),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=top_n,
    )
    response = client.run_report(request)
    pages = []
    for row in response.rows:
        try:
            pages.append({
                "page": row.dimension_values[0].value,
                "sessions": int(row.metric_values[0].value),
            })
        except (ValueError, IndexError):
            pass
    return pages


def fetch_page_sessions_comparison(site, token_file, start_curr, end_curr, start_prev, end_prev, top_n=5):
    """
    現在期間 vs 前期間のページ別オーガニックセッション数を比較し、
    減少幅の大きい順に TOP N を返す。

    Returns:
        list of {"page": str, "current": int, "prev": int, "diff": int}
        または {"error": str}
    """
    property_id = site.get("ga4_property_id")
    if not property_id:
        return {"error": "ga4_property_id が未設定"}
    try:
        creds = _get_credentials(token_file)
        client = _build_client(creds)

        curr_pages = {p["page"]: p["sessions"]
                      for p in _fetch_organic_sessions_by_page(client, property_id, start_curr, end_curr)}
        prev_pages = {p["page"]: p["sessions"]
                      for p in _fetch_organic_sessions_by_page(client, property_id, start_prev, end_prev)}

        all_pages = set(list(curr_pages.keys()) + list(prev_pages.keys()))
        diffs = []
        for page in all_pages:
            c = curr_pages.get(page, 0)
            p = prev_pages.get(page, 0)
            diffs.append({"page": page, "current": c, "prev": p, "diff": c - p})

        # 減少幅（diff が最も負）の順にソートし TOP N を返す
        diffs.sort(key=lambda x: x["diff"])
        return diffs[:top_n]

    except Exception as e:
        return {"error": str(e)}


def fetch_ga4_data(site, token_file):
    """
    GA4 APIから当月のオーガニックセッション数とCV数を取得する。

    Args:
        site: sites_config.json の1クライアント分のdict
        token_file: 使用するtokenファイルのパス

    Returns:
        {
            "sessions": int or None,
            "cv": int or None,
            "period": str,
            "error": str or None,
        }
    """
    property_id = site.get("ga4_property_id")
    cv_config = site.get("ga4_cv_config", {})

    if not property_id:
        return {"sessions": None, "cv": None, "period": "", "error": "ga4_property_id が未設定"}

    try:
        start_date, end_date = _get_period()
        period_label = _period_label(start_date, end_date)
        creds = _get_credentials(token_file)
        client = _build_client(creds)

        page_filter = site.get("page_filter")
        sessions = _fetch_organic_sessions(client, property_id, start_date, end_date, page_filter)

        cv_type = cv_config.get("type", "key_events")
        if cv_type == "key_events":
            cv = _fetch_cv_key_events(client, property_id, start_date, end_date, page_filter)
        elif cv_type == "events":
            event_names = cv_config.get("event_names", [])
            cv = _fetch_cv_events(client, property_id, start_date, end_date, event_names, page_filter)
        else:
            cv = 0

        return {"sessions": sessions, "cv": cv, "period": period_label, "error": None}

    except Exception as e:
        return {"sessions": None, "cv": None, "period": "", "error": str(e)}


def _last_month_range():
    """先月1日〜先月末日の日付を (start, end, year, month) で返す"""
    today = datetime.date.today()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start = datetime.date(year, month, 1)
    end   = datetime.date(year, month, last_day)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), year, month


def fetch_ga4_monthly_data(site, token_file):
    """
    GA4 APIから先月月次データ＋当年累計を直接取得する。

    Returns:
        {
            "month":            "2026年6月" など,
            "sessions":         int,
            "cv":               int,
            "sessions_annual":  int,
            "cv_annual":        int,
            "annual_period":    "2026年1月〜6月" など,
            "error":            str or None,
        }
    """
    property_id = site.get("ga4_property_id")
    cv_config   = site.get("ga4_cv_config", {})
    page_filter = site.get("page_filter")

    if not property_id:
        return {"error": "ga4_property_id が未設定"}

    try:
        creds  = _get_credentials(token_file)
        client = _build_client(creds)

        last_start, last_end, year, month = _last_month_range()

        # 先月単月
        sessions = _fetch_organic_sessions(client, property_id, last_start, last_end, page_filter)
        cv_type  = cv_config.get("type", "key_events")
        if cv_type == "key_events":
            cv = _fetch_cv_key_events(client, property_id, last_start, last_end, page_filter)
        elif cv_type == "events":
            event_names = cv_config.get("event_names", [])
            cv = _fetch_cv_events(client, property_id, last_start, last_end, event_names, page_filter)
        else:
            cv = 0

        # 当年1月1日〜先月末日の累計
        import calendar
        annual_start = datetime.date(year, 1, 1).strftime("%Y-%m-%d")
        annual_end   = last_end  # 先月末日と同じ

        sessions_annual = _fetch_organic_sessions(client, property_id, annual_start, annual_end, page_filter)
        if cv_type == "key_events":
            cv_annual = _fetch_cv_key_events(client, property_id, annual_start, annual_end, page_filter)
        elif cv_type == "events":
            cv_annual = _fetch_cv_events(client, property_id, annual_start, annual_end, event_names, page_filter)
        else:
            cv_annual = 0

        annual_period = f"{year}年1月〜{month}月"

        return {
            "month":           f"{year}年{month}月",
            "sessions":        sessions,
            "cv":              cv,
            "sessions_annual": sessions_annual,
            "cv_annual":       cv_annual,
            "annual_period":   annual_period,
            "error":           None,
        }

    except Exception as e:
        return {"error": str(e)}
