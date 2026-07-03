import sys
import io
from io import TextIOWrapper
import json

sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import config
from config import SITES, WEEKS_TO_COMPARE
from gsc_fetcher import get_search_console_service, get_date_range, fetch_summary, fetch_pages, fetch_queries_for_comparison
from report_generator import generate_html, save_html
from github_uploader import upload_to_github


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'サイト名が必要です'}))
        sys.exit(1)

    ai_text = sys.stdin.read().strip()
    if not ai_text:
        print(json.dumps({'error': 'AIたくま分析テキストが空です'}))
        sys.exit(1)

    site_name = sys.argv[1]
    site = next((s for s in SITES if s.get('name') == site_name), None)
    if not site:
        print(json.dumps({'error': 'サイトが見つかりません: ' + site_name}), file=sys.stderr)
        sys.exit(1)

    print(f'▶ {site_name} AIたくま分析レポート生成開始', file=sys.stderr)

    service = get_search_console_service(site.get('token_file'))
    property_url = site['property']
    page_filter = site.get('page_filter', None)

    summary_rows = []
    for w in range(WEEKS_TO_COMPARE):
        start, end = get_date_range(weeks_ago=w)
        row = fetch_summary(service, property_url, start, end)
        label = f'今週（{start}〜{end}）' if w == 0 else f'{w}週前（{start}〜{end}）'
        row['label'] = label
        summary_rows.append(row)

    curr_start, curr_end = get_date_range(weeks_ago=0)
    prev_start, prev_end = get_date_range(weeks_ago=1)
    week_label = f'{curr_start}〜{curr_end}'

    current_pages = fetch_pages(service, property_url, curr_start, curr_end, page_filter)
    current_q_comp = fetch_queries_for_comparison(service, property_url, curr_start, curr_end, 500, page_filter)
    previous_q_comp = fetch_queries_for_comparison(service, property_url, prev_start, prev_end, 500, page_filter)

    html = generate_html(
        site_name=site_name,
        week_label=week_label,
        summary_rows=summary_rows,
        pages=current_pages,
        insights=[],
        current_queries=current_q_comp,
        previous_queries=previous_q_comp,
        query_insights=[],
        ai_analysis=ai_text,
        ai_analysis_is_html=False,
        site_config={},
        kw_rankings=[],
        ga4_data={},
    )

    html_path = save_html(html, site_name, week_label)
    print(f'  ✅ HTMLレポート保存: {html_path}', file=sys.stderr)

    url = upload_to_github(html_path, site_name)
    if not url:
        print(json.dumps({'error': 'GitHubアップロード失敗'}))
        sys.exit(1)

    print(f'  ✅ GitHubアップロード完了: {url}', file=sys.stderr)
    print(json.dumps({'success': True, 'url': url}))


if __name__ == '__main__':
    main()
