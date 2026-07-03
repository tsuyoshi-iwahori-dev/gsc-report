"""
dashboard_fetcher.py — 施策URLごとにGSC・GA4データを週次取得し dashboard_data.json を生成する

実行方法:
  python dashboard_fetcher.py               # 差分取得（新しい週のみ）
  python dashboard_fetcher.py --full        # 全週再取得（施策日変更後などに使用）
  python dashboard_fetcher.py --dry-run     # GitHubアップロードをスキップ

依存: gsc_fetcher.py, ga4_fetcher.py, github_uploader.py, sites_config.json
"""

import argparse
import datetime
import json
import os
from urllib.parse import urlparse

from gsc_fetcher import get_search_console_service, get_date_range
from github_uploader import upload_to_github

施策データ_PATH = os.path.join(os.path.dirname(__file__), '..', '施策データ.json')
SITES_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'sites_config.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
OUTPUT_PATH = os.path.join(OUTPUT_DIR, 'dashboard_data.json')

DEFAULT_TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')
DEFAULT_WEEKS = 12


def _actions_changed(new_actions, old_actions):
    """actions の日付・ラベルセットが変化したか比較する"""
    def normalize(actions):
        return sorted((a.get('date', ''), a.get('label', '')) for a in (actions or []))
    return normalize(new_actions) != normalize(old_actions)


def _get_existing_page(existing_output, client_name, url):
    """既存 dashboard_data.json から対象 URL のページデータを返す"""
    pages = existing_output.get("clients", {}).get(client_name, {}).get("pages", [])
    for p in pages:
        if p.get("url") == url:
            return p
    return None


def _load_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(path, encoding='cp932') as f:
            return json.load(f)


def _load_sites_config():
    data = _load_json(SITES_CONFIG_PATH)
    if isinstance(data, list):
        return {s['name']: s for s in data}
    return {}


def _get_weeks(oldest_date_str=None):
    """週リストを生成する（新しい順、get_date_range と同じ木〜水区切り）。
    oldest_date_str が指定されていればその2ヶ月前から。なければ過去3ヶ月。
    戻り値: [(start_str, end_str), ...] 新しい順
    """
    today = datetime.date.today()
    # 直近の水曜 (get_date_range と同じロジック)
    days_since_wed = (today.weekday() - 2) % 7
    if days_since_wed == 0:
        days_since_wed = 7
    last_wed = today - datetime.timedelta(days=days_since_wed)

    if oldest_date_str:
        try:
            oldest = datetime.date.fromisoformat(oldest_date_str)
        except ValueError:
            oldest = today - datetime.timedelta(weeks=12)
        cutoff = oldest - datetime.timedelta(days=60)
    else:
        cutoff = today - datetime.timedelta(weeks=12)

    weeks = []
    w = 0
    while True:
        end = last_wed - datetime.timedelta(weeks=w)
        start = end - datetime.timedelta(days=6)
        if end < cutoff:
            break
        weeks.append((str(start), str(end)))
        w += 1
        if w > 52:  # 上限
            break
    return weeks  # 新しい順


def _fetch_gsc_page_week(service, property_url, start_date, end_date, page_url):
    """指定URLのGSCデータ（クリック・表示・CTR・順位）を1週分取得"""
    from googleapiclient.errors import HttpError
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['page'],
        'rowLimit': 1,
        'dimensionFilterGroups': [{
            'filters': [{
                'dimension': 'page',
                'operator': 'equals',
                'expression': page_url,
            }]
        }],
    }
    try:
        result = service.searchanalytics().query(
            siteUrl=property_url, body=body
        ).execute()
        rows = result.get('rows', [])
        if not rows:
            return {'clicks': 0, 'impressions': 0, 'ctr': 0.0, 'position': 0.0}
        r = rows[0]
        return {
            'clicks': int(r.get('clicks', 0)),
            'impressions': int(r.get('impressions', 0)),
            'ctr': round(r.get('ctr', 0) * 100, 2),
            'position': round(r.get('position', 0), 1),
        }
    except HttpError as e:
        print(f"      GSC page fetch error: {e}")
        return {'clicks': 0, 'impressions': 0, 'ctr': 0.0, 'position': 0.0}


def _fetch_gsc_kw_position(service, property_url, start_date, end_date, page_url, keyword):
    """指定URL × キーワードの平均順位を取得"""
    from googleapiclient.errors import HttpError
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query'],
        'rowLimit': 1,
        'dimensionFilterGroups': [{
            'filters': [
                {
                    'dimension': 'page',
                    'operator': 'equals',
                    'expression': page_url,
                },
                {
                    'dimension': 'query',
                    'operator': 'equals',
                    'expression': keyword,
                },
            ]
        }],
    }
    try:
        result = service.searchanalytics().query(
            siteUrl=property_url, body=body
        ).execute()
        rows = result.get('rows', [])
        if not rows:
            return None
        return round(rows[0].get('position', 0), 1)
    except HttpError as e:
        print(f"      GSC kw fetch error: {e}")
        return None


def _fetch_ga4_page_week(creds, property_id, start_date, end_date, page_url):
    """指定URLパスのオーガニックセッション数を1週分取得"""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric,
            FilterExpression, Filter, FilterExpressionList,
        )
        client = BetaAnalyticsDataClient(credentials=creds)
        path = urlparse(page_url).path or '/'

        and_filters = FilterExpression(
            and_group=FilterExpressionList(expressions=[
                FilterExpression(
                    filter=Filter(
                        field_name="sessionDefaultChannelGroup",
                        string_filter=Filter.StringFilter(
                            match_type=Filter.StringFilter.MatchType.EXACT,
                            value="Organic Search",
                        ),
                    )
                ),
                FilterExpression(
                    filter=Filter(
                        field_name="pagePath",
                        string_filter=Filter.StringFilter(
                            match_type=Filter.StringFilter.MatchType.EXACT,
                            value=path,
                        ),
                    )
                ),
            ])
        )
        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimensions=[Dimension(name="pagePath")],
            metrics=[Metric(name="sessions")],
            dimension_filter=and_filters,
        )
        response = client.run_report(request)
        total = 0
        for row in response.rows:
            try:
                total += int(row.metric_values[0].value)
            except (ValueError, IndexError):
                pass
        return total
    except Exception as e:
        print(f"      GA4 page fetch error: {e}")
        return None


def _get_ga4_creds(token_file):
    # ga4_fetcher._get_credentials と同じパターン（常にrefresh_tokenで新トークン取得）
    from ga4_fetcher import _get_credentials
    try:
        return _get_credentials(token_file)
    except Exception:
        return None


def run_dashboard_fetcher(dry_run=False, full=False):
    print("\n===== dashboard_fetcher 開始 =====")
    if full:
        print("  モード: 全週再取得 (--full)")
    else:
        print("  モード: 差分取得（新規週 + actions変更ページのみ再取得）")

    施策データ = _load_json(施策データ_PATH)
    if not 施策データ:
        print("  施策データが空のためスキップ")
        return

    # 既存データを読み込む（差分更新用）
    existing_output = {}
    if not full and os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, encoding='utf-8') as f:
                existing_output = json.load(f)
            print(f"  既存データ読み込み完了: {OUTPUT_PATH}")
        except Exception as e:
            print(f"  ⚠ 既存データ読み込み失敗（フル取得に切り替え）: {e}")
            existing_output = {}

    sites_config = _load_sites_config()

    # クライアント別にグループ化
    grouped = {}
    for item in 施策データ:
        client = item.get('client', '')
        grouped.setdefault(client, []).append(item)

    output = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "clients": {},
    }

    for client_name, pages in grouped.items():
        print(f"\n  [{client_name}] {len(pages)}件")
        site_cfg = sites_config.get(client_name, {})
        token_file = site_cfg.get('token_file', DEFAULT_TOKEN_FILE)
        property_url = site_cfg.get('property', '')
        property_id = site_cfg.get('ga4_property_id')

        if not property_url:
            print(f"    ⚠ property_url未設定のためスキップ")
            output["clients"][client_name] = {"pages": [], "error": "property_url未設定"}
            continue

        try:
            service = get_search_console_service(token_file)
        except Exception as e:
            print(f"    ⚠ GSC認証失敗: {e}")
            output["clients"][client_name] = {"pages": [], "error": str(e)}
            continue

        ga4_creds = _get_ga4_creds(token_file) if property_id else None

        client_pages = []
        for page_item in pages:
            page_url = page_item.get('url', '').rstrip('/')
            if not page_url:
                continue
            # trailing slash ありなしを GSC URL に合わせる（元のまま使う）
            page_url_gsc = page_item.get('url', '')

            actions = page_item.get('actions', [])
            oldest_date = None
            for a in actions:
                d = a.get('date', '')
                if d and (oldest_date is None or d < oldest_date):
                    oldest_date = d

            weeks = _get_weeks(oldest_date)
            keywords = [k for k in (page_item.get('keywords') or []) if k][:3]

            # 既存ページデータと actions の変更を検知
            existing_page = _get_existing_page(existing_output, client_name, page_url_gsc)
            actions_differ = _actions_changed(actions, existing_page.get("actions") if existing_page else None)

            force_full_page = full or actions_differ
            if actions_differ and not full:
                print(f"    {page_url_gsc} → actions変更検知: 全週再取得")
            elif force_full_page:
                print(f"    {page_url_gsc} → 全週取得 ({len(weeks)}週, KW:{len(keywords)}個)")
            else:
                print(f"    {page_url_gsc} → 差分取得 ({len(weeks)}週, KW:{len(keywords)}個)")

            # 既存週データをキャッシュとして使う（force_full_page=True の場合はリセット）
            existing_weekly: dict = {}
            if not force_full_page and existing_page:
                for w in existing_page.get("weekly_data", []):
                    # GA4設定済みで sessions=None（取得失敗）の週はキャッシュから除外して再取得
                    if ga4_creds and property_id and w.get("sessions") is None:
                        continue
                    existing_weekly[w["week"]] = w

            # 取得が必要な週（既存にない週のみ）
            valid_week_starts = {s for s, _ in weeks}
            weeks_to_fetch = [(s, e) for s, e in weeks if s not in existing_weekly]

            if weeks_to_fetch:
                print(f"      API取得: {len(weeks_to_fetch)}週 / キャッシュ利用: {len(existing_weekly)}週")
            else:
                print(f"      全週キャッシュ利用 ({len(existing_weekly)}週)")

            new_weekly = []
            for start_date, end_date in weeks_to_fetch:
                row = {'week': start_date}

                # GSC ページデータ
                gsc = _fetch_gsc_page_week(service, property_url, start_date, end_date, page_url_gsc)
                row.update(gsc)

                # GA4 ページセッション
                if ga4_creds and property_id:
                    sessions = _fetch_ga4_page_week(ga4_creds, property_id, start_date, end_date, page_url_gsc)
                    row['sessions'] = sessions
                else:
                    row['sessions'] = None

                # KW順位
                kw_positions = {}
                for kw in keywords:
                    pos = _fetch_gsc_kw_position(service, property_url, start_date, end_date, page_url_gsc, kw)
                    kw_positions[kw] = pos
                row['kw_positions'] = kw_positions

                new_weekly.append(row)

            # 既存キャッシュ + 新規取得をマージして古い順にソート
            all_weekly = list(existing_weekly.values()) + new_weekly
            all_weekly.sort(key=lambda x: x["week"])
            # 今回の対象週範囲内のみ残す
            weekly_data = [w for w in all_weekly if w["week"] in valid_week_starts]

            client_pages.append({
                "url": page_item.get('url', ''),
                "title": page_item.get('title', ''),
                "keywords": keywords,
                "actions": actions,
                "weekly_data": weekly_data,
            })

        output["clients"][client_name] = {"pages": client_pages}

    # 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  dashboard_data.json 保存完了: {OUTPUT_PATH}")

    # GitHub アップロード
    if not dry_run:
        try:
            url = upload_to_github(OUTPUT_PATH, 'dashboard')
            if url:
                print(f"  GitHub アップロード完了: {url}")
        except Exception as e:
            print(f"  ⚠ GitHubアップロードエラー: {e}")

    # ダッシュボード HTML 生成
    try:
        from dashboard_generator import generate_dashboard
        output_html_dir = os.path.join(OUTPUT_DIR, 'dashboard')
        generate_dashboard(output, output_html_dir, dry_run=dry_run)
    except Exception as e:
        print(f"  ⚠ dashboard_generator エラー: {e}")

    print("===== dashboard_fetcher 完了 =====")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='GitHubアップロードをスキップ')
    parser.add_argument('--full', action='store_true', help='既存キャッシュを無視して全週分再取得する')
    args = parser.parse_args()
    run_dashboard_fetcher(dry_run=args.dry_run, full=args.full)
