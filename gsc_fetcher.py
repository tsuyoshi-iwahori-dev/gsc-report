import os
import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import config
from config import CREDENTIALS_FILE, TOKEN_FILE, ROW_LIMIT

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def authenticate(token_file=TOKEN_FILE):
    """Google認証を行い、credentialsを返す"""
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
    return creds


def get_search_console_service(token_file=TOKEN_FILE):
    """Search Console APIサービスを返す"""
    creds = authenticate(token_file)
    return build('searchconsole', 'v1', credentials=creds)


def get_date_range(weeks_ago=0):
    """
    取得期間：直近の木曜〜水曜（GSC遅延対策）
    例）6/16（月）実行 → 6/4（木）〜6/10（水）
    weeks_ago=1 → 5/28（木）〜6/3（水）
    """
    today = datetime.date.today()
    # 直近の水曜を求める（当日が水曜の場合は先週の水曜）
    days_since_wed = (today.weekday() - 2) % 7
    if days_since_wed == 0:
        days_since_wed = 7
    last_wed = today - datetime.timedelta(days=days_since_wed)
    # weeks_ago週前の木〜水
    end_date = last_wed - datetime.timedelta(weeks=weeks_ago)
    start_date = end_date - datetime.timedelta(days=6)
    return str(start_date), str(end_date)


def fetch_summary(service, property_url, start_date, end_date):
    """サイト全体のサマリーデータを取得"""
    result = service.searchanalytics().query(
        siteUrl=property_url,
        body={
            'startDate': start_date,
            'endDate': end_date,
            'rowLimit': 1,
        }
    ).execute()
    rows = result.get('rows', [{}])
    row = rows[0] if rows else {}
    return {
        'clicks': int(row.get('clicks', 0)),
        'impressions': int(row.get('impressions', 0)),
        'ctr': round(row.get('ctr', 0) * 100, 2),
        'position': round(row.get('position', 0), 1),
    }


def fetch_queries(service, property_url, start_date, end_date, page_filter=None):
    """クエリ別データを取得"""
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query'],
        'rowLimit': ROW_LIMIT,
        'orderBy': [{'fieldName': 'clicks', 'sortOrder': 'DESCENDING'}],
    }
    if page_filter:
        body['dimensionFilterGroups'] = [{
            'filters': [{
                'dimension': 'page',
                'operator': 'contains',
                'expression': page_filter,
            }]
        }]
    result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
    rows = result.get('rows', [])
    return [
        {
            'query': r['keys'][0],
            'clicks': int(r.get('clicks', 0)),
            'impressions': int(r.get('impressions', 0)),
            'ctr': round(r.get('ctr', 0) * 100, 2),
            'position': round(r.get('position', 0), 1),
        }
        for r in rows
    ]


def fetch_pages(service, property_url, start_date, end_date, page_filter=None):
    """ページ別データを取得"""
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['page'],
        'rowLimit': ROW_LIMIT,
        'orderBy': [{'fieldName': 'clicks', 'sortOrder': 'DESCENDING'}],
    }
    if page_filter:
        body['dimensionFilterGroups'] = [{
            'filters': [{
                'dimension': 'page',
                'operator': 'contains',
                'expression': page_filter,
            }]
        }]
    result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
    rows = result.get('rows', [])
    return [
        {
            'page': r['keys'][0],
            'clicks': int(r.get('clicks', 0)),
            'impressions': int(r.get('impressions', 0)),
            'ctr': round(r.get('ctr', 0) * 100, 2),
            'position': round(r.get('position', 0), 1),
        }
        for r in rows
    ]


def fetch_index_coverage(service, property_url):
    """
    インデックスカバレッジのエラー数を取得する
    戻り値: {"error": N, "warning": N, "excluded": N, "valid": N}
    """
    try:
        result = service.searchanalytics().query(
            siteUrl=property_url,
            body={
                'startDate': '2000-01-01',
                'endDate': '2099-12-31',
                'type': 'index',
                'rowLimit': 1,
            }
        ).execute()
        counts = result.get('indexStatusCountsPerCrawlStatus', {})
        try:
            sitemaps = service.sitemaps().list(siteUrl=property_url).execute()
            sitemap_count = len(sitemaps.get('sitemap', []))
        except Exception:
            sitemap_count = 0
        return {
            'error': int(counts.get('error', 0)),
            'warning': int(counts.get('softError', 0)),
            'excluded': int(counts.get('notIndexed', 0)),
            'valid': int(counts.get('indexed', 0)),
            'sitemap': sitemap_count,
        }
    except Exception as e:
        print(f"  ⚠ インデックスカバレッジ取得失敗: {e}")
        return {'error': 0, 'warning': 0, 'excluded': 0, 'valid': 0}


def fetch_queries_for_comparison(service, property_url, start_date, end_date, limit=500, page_filter=None):
    """比較用クエリデータを取得（上位20件）"""
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query'],
        'rowLimit': limit,
        'orderBy': [{'fieldName': 'clicks', 'sortOrder': 'DESCENDING'}],
    }
    if page_filter:
        body['dimensionFilterGroups'] = [{
            'filters': [{
                'dimension': 'page',
                'operator': 'contains',
                'expression': page_filter,
            }]
        }]
    result = service.searchanalytics().query(siteUrl=property_url, body=body).execute()
    rows = result.get('rows', [])
    return {
        r['keys'][0]: {
            'clicks': int(r.get('clicks', 0)),
            'impressions': int(r.get('impressions', 0)),
            'ctr': round(r.get('ctr', 0) * 100, 2),
            'position': round(r.get('position', 0), 1),
        }
        for r in rows
    }
