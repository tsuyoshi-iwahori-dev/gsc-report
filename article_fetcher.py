"""
article_fetcher.py — 新規記事データ.json の記事ごとに GSC・GA4 の週次データを取得し
                     article_data.json を生成する

実行方法:
  python article_fetcher.py               # 差分取得（未取得週のみ）
  python article_fetcher.py --full        # 全週再取得
  python article_fetcher.py --dry-run     # GitHub アップロードをスキップ
"""

import argparse
import datetime
import json
import os
from urllib.parse import urlparse

from gsc_fetcher import get_search_console_service
from github_uploader import upload_to_github

ARTICLES_PATH   = os.path.join(os.path.dirname(__file__), '..', '新規記事データ.json')
SITES_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'sites_config.json')
OUTPUT_DIR      = os.path.join(os.path.dirname(__file__), 'reports')
OUTPUT_PATH     = os.path.join(OUTPUT_DIR, 'article_data.json')
DEFAULT_TOKEN   = os.path.join(os.path.dirname(__file__), 'token.json')


# ── 共通ユーティリティ ────────────────────────────────────────────────────────

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


def _get_weeks_from(published_at_str):
    """
    公開日以降の週リストを生成（木〜水区切り、新しい順）。
    公開日を含む週から直近の完結した週まで。
    """
    try:
        pub = datetime.date.fromisoformat(published_at_str)
    except ValueError:
        pub = datetime.date.today() - datetime.timedelta(weeks=4)

    today = datetime.date.today()
    days_since_wed = (today.weekday() - 2) % 7
    if days_since_wed == 0:
        days_since_wed = 7
    last_wed = today - datetime.timedelta(days=days_since_wed)

    weeks = []
    w = 0
    while True:
        end = last_wed - datetime.timedelta(weeks=w)
        start = end - datetime.timedelta(days=6)
        if end < pub:
            break
        weeks.append((str(start), str(end)))
        w += 1
        if w > 104:  # 最大2年
            break

    return weeks  # 新しい順


def _get_ga4_creds(token_file):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    try:
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception:
        return None


# ── GSC フェッチ ─────────────────────────────────────────────────────────────

def _fetch_gsc_page_week(service, property_url, start_date, end_date, page_url):
    from googleapiclient.errors import HttpError
    body = {
        'startDate': start_date,
        'endDate':   end_date,
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
        result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
        rows = result.get('rows', [])
        if not rows:
            return {'clicks': 0, 'impressions': 0, 'ctr': 0.0, 'position': 0.0}
        r = rows[0]
        return {
            'clicks':      int(r.get('clicks', 0)),
            'impressions': int(r.get('impressions', 0)),
            'ctr':         round(r.get('ctr', 0) * 100, 2),
            'position':    round(r.get('position', 0), 1),
        }
    except HttpError as e:
        print(f"      GSC page fetch error: {e}")
        return {'clicks': 0, 'impressions': 0, 'ctr': 0.0, 'position': 0.0}


def _fetch_top_keywords(service, property_url, page_url, days=28):
    """過去 days 日間のクエリ別クリック数上位3件を返す"""
    from googleapiclient.errors import HttpError
    today    = datetime.date.today()
    end_date = (today - datetime.timedelta(days=3)).isoformat()   # GSC遅延考慮
    start_date = (today - datetime.timedelta(days=3 + days - 1)).isoformat()
    body = {
        'startDate': start_date,
        'endDate':   end_date,
        'dimensions': ['query'],
        'rowLimit': 3,
        'orderBy': [{'fieldName': 'clicks', 'sortOrder': 'DESCENDING'}],
        'dimensionFilterGroups': [{
            'filters': [{
                'dimension': 'page',
                'operator': 'equals',
                'expression': page_url,
            }]
        }],
    }
    try:
        result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
        return [row['keys'][0] for row in result.get('rows', []) if row.get('keys')]
    except HttpError as e:
        print(f"      GSC top_keywords fetch error: {e}")
        return []


def _fetch_gsc_kw_position(service, property_url, start_date, end_date, page_url, keyword):
    from googleapiclient.errors import HttpError
    body = {
        'startDate': start_date,
        'endDate':   end_date,
        'dimensions': ['query'],
        'rowLimit': 1,
        'dimensionFilterGroups': [{
            'filters': [
                {'dimension': 'page',  'operator': 'equals', 'expression': page_url},
                {'dimension': 'query', 'operator': 'equals', 'expression': keyword},
            ]
        }],
    }
    try:
        result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
        rows = result.get('rows', [])
        if not rows:
            return None
        return round(rows[0].get('position', 0), 1)
    except HttpError as e:
        print(f"      GSC kw fetch error: {e}")
        return None


# ── GA4 フェッチ ─────────────────────────────────────────────────────────────

def _fetch_ga4_page_week(creds, property_id, start_date, end_date, page_url):
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


# ── メイン ───────────────────────────────────────────────────────────────────

def run_article_fetcher(dry_run=False, full=False):
    print("\n===== article_fetcher 開始 =====")

    articles = _load_json(ARTICLES_PATH)
    if not articles:
        print("  新規記事データが空のためスキップ")
        return

    print(f"  記事数: {len(articles)}")
    if full:
        print("  モード: 全週再取得 (--full)")
    else:
        print("  モード: 差分取得（未取得週のみ）")

    # 既存データ読み込み
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

    # クライアントごとにグループ化
    grouped = {}
    for item in articles:
        c = item.get('client', '')
        grouped.setdefault(c, []).append(item)

    output = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "clients": {},
    }

    for client_name, client_articles in grouped.items():
        print(f"\n  [{client_name}] {len(client_articles)}件")
        site_cfg    = sites_config.get(client_name, {})
        token_file  = site_cfg.get('token_file', DEFAULT_TOKEN)
        if not os.path.isabs(token_file):
            token_file = os.path.join(os.path.dirname(__file__), token_file)
        property_url = site_cfg.get('property', '')
        property_id  = site_cfg.get('ga4_property_id')

        if not property_url:
            print(f"    ⚠ property_url 未設定のためスキップ")
            output["clients"][client_name] = {"articles": [], "error": "property_url未設定"}
            continue

        try:
            service = get_search_console_service(token_file)
        except Exception as e:
            print(f"    ⚠ GSC認証失敗: {e}")
            output["clients"][client_name] = {"articles": [], "error": str(e)}
            continue

        ga4_creds = _get_ga4_creds(token_file) if property_id else None

        # 既存クライアントデータ
        existing_client = existing_output.get("clients", {}).get(client_name, {})
        existing_articles_map = {}
        for a in existing_client.get("articles", []):
            existing_articles_map[a.get("url", "")] = a

        result_articles = []
        # 新規記事データ.json 更新用フラグ
        articles_json_dirty = False

        for article in client_articles:
            page_url     = article.get("url", "").rstrip('/')
            page_url_raw = article.get("url", "")
            published_at = article.get("published_at", "")
            top_keywords = [k for k in (article.get("top_keywords") or []) if k][:3]
            title        = article.get("title", "")

            if not page_url or not published_at:
                print(f"    ⚠ url/published_at 未設定のためスキップ: {page_url_raw}")
                continue

            weeks = _get_weeks_from(published_at)
            if not weeks:
                print(f"    ⚠ 対象週なし（公開日が未来?）: {page_url_raw}")
                continue

            # ── KW 再計算（毎回実行） ──────────────────────────────────────────
            try:
                new_kws = _fetch_top_keywords(service, property_url, page_url_raw)
            except Exception as e:
                print(f"      ⚠ KW再計算スキップ: {e}")
                new_kws = top_keywords

            kw_changed = bool(new_kws) and new_kws != top_keywords
            if kw_changed:
                old_str = ', '.join(top_keywords) or '(なし)'
                new_str = ', '.join(new_kws)
                print(f"      KW更新: [{old_str}] → [{new_str}]")
                top_keywords = new_kws
                # 新規記事データ.json の該当エントリも更新
                for art_entry in articles:
                    if art_entry.get("url") == page_url_raw and art_entry.get("client") == client_name:
                        art_entry["top_keywords"] = new_kws
                        articles_json_dirty = True
                        break

            print(f"    {page_url_raw} ({len(weeks)}週, KW:{len(top_keywords)}個)")

            # 既存キャッシュ
            existing_article = existing_articles_map.get(page_url_raw, {})
            existing_weekly: dict = {}
            # KWが変わった場合は全週再取得（kw_positions の整合性確保）
            if not full and not kw_changed and existing_article:
                for w in existing_article.get("weekly_data", []):
                    existing_weekly[w["week"]] = w
            elif kw_changed and existing_article:
                print(f"      KW変更のため週次データを全週再取得します")

            valid_week_starts = {s for s, _ in weeks}
            weeks_to_fetch = [(s, e) for s, e in weeks if s not in existing_weekly]

            if weeks_to_fetch:
                print(f"      API取得: {len(weeks_to_fetch)}週 / キャッシュ: {len(existing_weekly)}週")
            else:
                print(f"      全週キャッシュ利用 ({len(existing_weekly)}週)")

            new_weekly = []
            for w_num, (start_date, end_date) in enumerate(reversed(weeks_to_fetch)):
                # published_at からの経過週番号（1始まり）
                all_starts_sorted = sorted(valid_week_starts)
                try:
                    week_number = all_starts_sorted.index(start_date) + 1
                except ValueError:
                    week_number = 0

                row = {'week': start_date, 'week_number': week_number}

                gsc = _fetch_gsc_page_week(service, property_url, start_date, end_date, page_url_raw)
                row.update(gsc)

                if ga4_creds and property_id:
                    row['sessions'] = _fetch_ga4_page_week(ga4_creds, property_id, start_date, end_date, page_url_raw)
                else:
                    row['sessions'] = None

                kw_positions = {}
                for kw in top_keywords:
                    kw_positions[kw] = _fetch_gsc_kw_position(service, property_url, start_date, end_date, page_url_raw, kw)
                row['kw_positions'] = kw_positions

                new_weekly.append(row)

            # キャッシュ + 新規をマージし古い順にソート
            all_starts_sorted = sorted(valid_week_starts)

            # week_number を再計算（キャッシュ分も含む）
            def with_week_number(w):
                try:
                    w['week_number'] = all_starts_sorted.index(w['week']) + 1
                except ValueError:
                    pass
                return w

            all_weekly = [with_week_number(dict(w)) for w in list(existing_weekly.values()) + new_weekly]
            all_weekly.sort(key=lambda x: x["week"])
            weekly_data = [w for w in all_weekly if w["week"] in valid_week_starts]

            result_articles.append({
                "url":          page_url_raw,
                "title":        title,
                "published_at": published_at,
                "top_keywords": top_keywords,
                "weekly_data":  weekly_data,
            })

        output["clients"][client_name] = {"articles": result_articles}

        # KW 更新があれば 新規記事データ.json を同期保存
        if articles_json_dirty:
            try:
                with open(ARTICLES_PATH, 'w', encoding='utf-8') as f:
                    json.dump(articles, f, ensure_ascii=False, indent=2)
                print(f"    新規記事データ.json を更新しました")
            except Exception as e:
                print(f"    ⚠ 新規記事データ.json 保存失敗: {e}")

    # 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  article_data.json 保存完了: {OUTPUT_PATH}")

    # GitHub アップロード
    if not dry_run:
        try:
            url = upload_to_github(OUTPUT_PATH, 'article')
            if url:
                print(f"  GitHub アップロード完了: {url}")
        except Exception as e:
            print(f"  ⚠ GitHubアップロードエラー: {e}")

    # HTML 生成
    try:
        from article_generator import generate_article_pages
        output_html_dir = os.path.join(OUTPUT_DIR, 'article')
        generate_article_pages(output, output_html_dir, dry_run=dry_run)
    except Exception as e:
        print(f"  ⚠ article_generator エラー: {e}")

    print("===== article_fetcher 完了 =====")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='GitHubアップロードをスキップ')
    parser.add_argument('--full', action='store_true', help='既存キャッシュを無視して全週再取得')
    args = parser.parse_args()
    run_article_fetcher(dry_run=args.dry_run, full=args.full)
