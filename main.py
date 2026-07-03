import argparse
import json
import os
from datetime import datetime

from config import SITES, WEEKS_TO_COMPARE, CREDENTIALS_FILE, TOKEN_FILE
from ga4_fetcher import fetch_ga4_data, fetch_ga4_monthly_data
from gsc_fetcher import get_search_console_service, get_date_range, fetch_summary, fetch_pages, fetch_queries_for_comparison
from sheets_writer import get_sheets_client, write_summary, write_queries, write_pages, write_comparison, write_query_comparison, write_insights
from analyzer import analyze, format_insights
from ai_analyzer import analyze_with_ai
from report_generator import generate_html, save_html
from github_uploader import upload_to_github, update_index


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(path, encoding="cp932") as f:
            return json.load(f)


def get_ga4_monthly_data(site, token_file):
    """GA4 APIから先月月次データ＋当年累計を直接取得する（スプシ不要）"""
    result = fetch_ga4_monthly_data(site, token_file)
    if result.get("error"):
        print(f"  ⚠ GA4月次データ取得エラー: {result['error']}")
        return None
    return result


def _make_date_range_fn(week_start_str):
    """--week-start 指定時に get_date_range の代替となる関数を返す"""
    import datetime as _dt
    base = _dt.date.fromisoformat(week_start_str)  # 例: 2026-06-18（木）
    def _date_range(weeks_ago=0):
        start = base - _dt.timedelta(weeks=weeks_ago)
        end   = start + _dt.timedelta(days=6)
        return str(start), str(end)
    return _date_range


def main():
    parser = argparse.ArgumentParser(description="GSC週次レポート自動生成")
    parser.add_argument("--site", help="特定クライアントのnameを指定（省略時は全クライアント実行）")
    parser.add_argument("--week-start", dest="week_start",
                        help="過去週再生成用：週の開始日（木曜）を YYYY-MM-DD で指定（例: 2026-06-18）")
    args = parser.parse_args()

    if args.week_start:
        _get_date_range = _make_date_range_fn(args.week_start)
        print(f"[週指定モード] week-start={args.week_start}")
    else:
        _get_date_range = get_date_range

    sites_config = load_json("sites_config.json")
    kw_path = os.path.join(os.path.dirname(__file__), '..', 'kw-rankings.json')
    try:
        with open(kw_path, encoding='utf-8') as f:
            all_kw_data = json.load(f)
    except Exception:
        all_kw_data = {}

    gc = get_sheets_client()

    report_urls = []
    site_reports = []

    for site in SITES:
        site_name = site["name"]

        if args.site and args.site != site_name:
            continue

        print(f"\n{'='*50}")
        print(f"[{site_name}] 処理開始")
        print(f"{'='*50}")

        try:
            token_file = site.get("token_file", TOKEN_FILE)
            property_url = site["property"]
            sheet_id = site.get("sheet_id", "")
            page_filter = site.get("page_filter", None)

            _site_config = next((s for s in sites_config if s['name'] == site_name), {})
            _kw_rankings = all_kw_data.get("rankings", {}).get(site_name, {})

            # GA4データ取得（当月 Organic Sessions + CV）
            print("  GA4データ取得中...")
            ga4_data = fetch_ga4_data(_site_config, token_file)
            if ga4_data.get("error"):
                print(f"  ⚠ GA4取得エラー: {ga4_data['error']}")
                ga4_data = None
            else:
                ga4_data["month"] = ga4_data.pop("period", "")

            # GA4月次データ取得（先月実績＋当年累計）
            print("  GA4月次データ取得中...")
            monthly = get_ga4_monthly_data(_site_config, token_file)
            if monthly and ga4_data is not None:
                ga4_data.update({
                    "month":           monthly["month"],
                    "sessions":        monthly["sessions"],
                    "cv":              monthly["cv"],
                    "sessions_annual": monthly["sessions_annual"],
                    "cv_annual":       monthly["cv_annual"],
                    "annual_period":   monthly["annual_period"],
                })
            elif monthly and ga4_data is None:
                ga4_data = monthly

            # GSCサービス初期化
            service = get_search_console_service(token_file)

            # スプシを開く（sheet_idが空の場合はスキップ）
            spreadsheet = gc.open_by_key(sheet_id) if sheet_id else None

            # 複数週の日付範囲を取得
            curr_start, curr_end = _get_date_range(weeks_ago=0)
            prev_start, prev_end = _get_date_range(weeks_ago=1)
            week_label = f"{curr_start}〜{curr_end}"

            print(f"  対象期間: {week_label}")

            # データ取得（WEEKS_TO_COMPARE週分のサマリー）
            print("  GSCデータ取得中...")
            summary_rows = []
            for w in range(WEEKS_TO_COMPARE):
                s, e = _get_date_range(weeks_ago=w)
                row = fetch_summary(service, property_url, s, e)
                row['label'] = f'今週（{s}〜{e}）' if w == 0 else f'{w}週前（{s}〜{e}）'
                summary_rows.append(row)

            current_pages = fetch_pages(service, property_url, curr_start, curr_end, page_filter)

            current_q_comp = fetch_queries_for_comparison(service, property_url, curr_start, curr_end, 500, page_filter)
            previous_q_comp = fetch_queries_for_comparison(service, property_url, prev_start, prev_end, 500, page_filter)

            current_summary = summary_rows[0]
            previous_summary = summary_rows[1] if len(summary_rows) > 1 else {}

            # スプシに書き込み
            if spreadsheet:
                print("  スプシ書き込み中...")
                write_summary(spreadsheet, summary_rows)
                write_pages(spreadsheet, week_label, current_pages)
                write_comparison(spreadsheet, week_label, current_summary, previous_summary)
                write_query_comparison(spreadsheet, week_label, current_q_comp, previous_q_comp)
            else:
                print("  スプシスキップ（sheet_id未設定）")

            # ルールベース分析
            insights = analyze(summary_rows, current_q_comp, current_pages)
            query_insights = []
            try:
                from analyzer import analyze_queries
                query_insights = analyze_queries(current_q_comp, previous_q_comp)
            except Exception:
                pass

            # AI分析
            ai_analysis = ""
            ai_analysis_is_html = False
            try:
                print("  AI分析中...")
                ai_insights = analyze_with_ai(
                    site_name, week_label, summary_rows,
                    current_q_comp, previous_q_comp, current_pages
                )
                if ai_insights:
                    ai_analysis = ai_insights
                    ai_analysis_is_html = False
            except Exception as e:
                print(f"  ⚠ AI分析スキップ: {e}")

            # insightsをスプシに書き込み
            if spreadsheet:
                all_insights = insights + (ai_insights if isinstance(ai_analysis, list) and ai_analysis else [])
                write_insights(spreadsheet, week_label, all_insights)

            # HTMLレポート生成
            print("  HTMLレポート生成中...")
            html = generate_html(
                site_name=site_name,
                week_label=week_label,
                summary_rows=summary_rows,
                pages=current_pages,
                insights=insights,
                current_queries=current_q_comp,
                previous_queries=previous_q_comp,
                query_insights=query_insights,
                ai_analysis=ai_analysis,
                ai_analysis_is_html=ai_analysis_is_html,
                site_config=_site_config,
                kw_rankings=_kw_rankings,
                ga4_data=ga4_data,
            )

            # ローカルに保存
            html_path = save_html(html, site_name, week_label)
            print(f"  ローカル保存: {html_path}")

            # GitHubにアップロード
            print("  GitHubアップロード中...")
            report_url = upload_to_github(html_path, site_name)

            if report_url:
                report_urls.append(f"{site_name}: {report_url}")
                site_reports.append({
                    "name": site_name,
                    "url": report_url,
                    "week": week_label,
                })
                print(f"  完了: {report_url}")
            else:
                print(f"  ⚠ アップロード失敗")

        except Exception as e:
            print(f"  ✗ エラーが発生しました（スキップ）: {e}")
            import traceback
            traceback.print_exc()
            continue

    # index.html を更新
    if site_reports:
        print("\nindex.html を更新中...")
        update_index(site_reports)

    # URL一覧を保存
    os.makedirs("reports", exist_ok=True)
    today = datetime.today().strftime("%Y%m%d")
    urls_path = f"reports/report_urls_{today}.txt"
    with open(urls_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_urls))

    print(f"\nレポートURL一覧を {urls_path} に保存しました。")
    for url_line in report_urls:
        print(f"  {url_line}")

    # 施策ダッシュボードデータ生成
    try:
        from dashboard_fetcher import run_dashboard_fetcher
        run_dashboard_fetcher()
    except Exception as e:
        print(f"\n⚠ dashboard_fetcher エラー: {e}")

    # 新規記事パフォーマンスデータ生成
    try:
        import json, os as _os
        _articles_path = _os.path.join(_os.path.dirname(__file__), '..', '新規記事データ.json')
        _articles = json.load(open(_articles_path, encoding='utf-8')) if _os.path.exists(_articles_path) else []
        if _articles:
            from article_fetcher import run_article_fetcher
            run_article_fetcher()
        else:
            print("\n新規記事データが空のため article_fetcher をスキップ")
    except Exception as e:
        print(f"\n⚠ article_fetcher エラー: {e}")


if __name__ == "__main__":
    main()
