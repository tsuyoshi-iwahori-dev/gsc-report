import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

import config
from config import TOKEN_FILE

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/webmasters.readonly',
]


def get_sheets_client(token_file=None):
    """gspreadクライアントを返す"""
    token_path = token_file if token_file else TOKEN_FILE
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return gspread.authorize(creds)


def get_or_create_sheet(spreadsheet, title):
    """シートを取得。なければ作成する"""
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=20)


def write_summary(spreadsheet, summary_rows):
    """
    サマリーシートに週次比較データを書き込む
    summary_rows: [{"label": "先週", "clicks": 100, ...}, ...]
    """
    ws = get_or_create_sheet(spreadsheet, 'サマリー')
    header = ['期間', 'クリック数', '表示回数', 'CTR(%)', '平均掲載順位']
    rows = [header]
    for r in summary_rows:
        rows.append([
            r.get('label', ''),
            r.get('clicks', 0),
            r.get('impressions', 0),
            r.get('ctr', 0),
            r.get('position', 0),
        ])
    ws.clear()
    ws.update('A1', rows)
    print('  ✅ サマリーシート書き込み完了')


def write_queries(spreadsheet, week_label, queries):
    """クエリ別データをシートに書き込む"""
    ws = get_or_create_sheet(spreadsheet, 'クエリ_' + week_label)
    header = ['クエリ', 'クリック数', '表示回数', 'CTR(%)', '平均掲載順位']
    rows = [header] + [
        [q.get('query', ''), q.get('clicks', 0), q.get('impressions', 0), q.get('ctr', 0), q.get('position', 0)]
        for q in queries
    ]
    ws.clear()
    ws.update('A1', rows)
    print(f'  ✅ クエリシート（{week_label}）書き込み完了')


def write_pages(spreadsheet, week_label, pages):
    """ページ別データをシートに書き込む"""
    ws = get_or_create_sheet(spreadsheet, 'ページ_' + week_label)
    header = ['ページ', 'クリック数', '表示回数', 'CTR(%)', '平均掲載順位']
    rows = [header] + [
        [p.get('page', ''), p.get('clicks', 0), p.get('impressions', 0), p.get('ctr', 0), p.get('position', 0)]
        for p in pages
    ]
    ws.clear()
    ws.update('A1', rows)
    print(f'  ✅ ページシート（{week_label}）書き込み完了')


def write_comparison(spreadsheet, week_label, current, previous):
    """
    前週比較シートを書き込む
    current / previous: fetch_summary()の戻り値
    """
    ws = get_or_create_sheet(spreadsheet, '前週比較')
    header = ['指標', '今週', '前週', '変化率(%)']
    metrics = [
        ('クリック数', 'clicks'),
        ('表示回数', 'impressions'),
        ('CTR(%)', 'ctr'),
        ('平均掲載順位', 'position'),
    ]
    rows = [header]
    for label, key in metrics:
        curr_val = current.get(key, 0)
        prev_val = previous.get(key, 0)
        rate = _calc_rate(curr_val, prev_val)
        rows.append([label, curr_val, prev_val, rate])
    ws.clear()
    ws.update('A1', rows)
    print('  ✅ 前週比較シート書き込み完了')


def write_insights(spreadsheet, week_label, insights):
    """SEO分析コメントをシートに書き込む"""
    ws = get_or_create_sheet(spreadsheet, 'SEO分析コメント')
    header = ['週', '優先度', 'タイトル', '詳細', 'アクション']
    rows = [header]
    for ins in insights:
        rows.append([
            week_label,
            ins.get('level', ''),
            ins.get('title', ''),
            ins.get('detail', ''),
            ins.get('action', ''),
        ])
    ws.clear()
    ws.update('A1', rows)
    print('  ✅ SEO分析コメントシート書き込み完了')


def write_report_url(spreadsheet, week_label, drive_url):
    """レポートURLをシートに追記する（週次で蓄積）"""
    ws = get_or_create_sheet(spreadsheet, 'レポートURL')
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    ws.append_row([week_label, now, drive_url])
    print('  ✅ レポートURLシート書き込み完了')


def write_query_comparison(spreadsheet, week_label, current_queries, previous_queries):
    """
    クエリ比較シートを書き込む
    current_queries / previous_queries: fetch_queries_for_comparison()の戻り値
    """
    ws = get_or_create_sheet(spreadsheet, 'クエリ比較')
    header = ['クエリ', '今週CL', '前週CL', '今週IMP', '前週IMP', '今週CTR', '前週CTR', '今週順位', '前週順位', '判定']
    all_queries = list(set(list(current_queries.keys()) + list(previous_queries.keys())))

    rows_data = []
    for q in all_queries:
        curr = current_queries.get(q, {})
        prev = previous_queries.get(q, {})
        curr_cl = curr.get('clicks', 0)
        prev_cl = prev.get('clicks', 0)

        if q not in previous_queries:
            status = '🆕 新出現'
        elif q not in current_queries:
            status = '❌ 消滅'
        else:
            rate = _calc_rate(curr_cl, prev_cl)
            if isinstance(rate, (int, float)) and rate > 0:
                status = '✅ 改善'
            elif isinstance(rate, (int, float)) and rate < 0:
                status = '🔴 悪化'
            else:
                status = '－ 横ばい'

        rows_data.append([
            q,
            curr.get('clicks', ''),
            prev.get('clicks', ''),
            curr.get('impressions', ''),
            prev.get('impressions', ''),
            curr.get('ctr', ''),
            prev.get('ctr', ''),
            curr.get('position', ''),
            prev.get('position', ''),
            status,
        ])

    rows_data.sort(key=lambda r: r[1] if isinstance(r[1], int) else 0, reverse=True)
    ws.clear()
    ws.update('A1', [header] + rows_data)
    print('  ✅ クエリ比較シート書き込み完了')


def _calc_rate(current, previous):
    """変化率計算（%）"""
    if previous == 0:
        return 'N/A'
    return round((current - previous) / previous * 100, 1)
