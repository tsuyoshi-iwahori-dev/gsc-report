import datetime
import re
import os


def _escape(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _inline(text):
    """**太字** をインライン変換"""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def _body_to_html(body):
    """本文テキストをリスト・段落HTMLに変換"""
    lines = body.split('\n')
    parts = []
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                parts.append('</ul>')
                in_list = False
            continue
        if line.startswith('- ') or line.startswith('・'):
            if not in_list:
                parts.append('<ul>')
                in_list = True
            item = line[2:] if line.startswith('- ') else line[1:]
            parts.append(f'<li>{_inline(_escape(item))}</li>')
        else:
            if in_list:
                parts.append('</ul>')
                in_list = False
            parts.append(f'<p>{_inline(_escape(line))}</p>')
    if in_list:
        parts.append('</ul>')
    return '\n'.join(parts)


def _convert_action_section(title, body):
    """優先度付きアクションセクション（6番）を3カラムグリッドHTMLに変換"""
    now_match = re.search(r'今すぐ[（(][^）)]*[）)][:：]?\s*\n(.*?)(?=今月中|来月以降|$)', body, re.DOTALL)
    month_match = re.search(r'今月中[:：]?\s*\n(.*?)(?=来月以降|今すぐ|$)', body, re.DOTALL)
    later_match = re.search(r'来月以降[:：]?\s*\n(.*?)(?=今すぐ|今月中|$)', body, re.DOTALL)

    now_html = _body_to_html(now_match.group(1).strip()) if now_match else ''
    month_html = _body_to_html(month_match.group(1).strip()) if month_match else ''
    later_html = _body_to_html(later_match.group(1).strip()) if later_match else ''

    return f'''
    <div class="ai-section-card ai-action-card">
        <div class="ai-section-header">6. {_escape(title)}</div>
        <div class="ai-action-grid">
            <div class="ai-action-now">
                <div class="ai-action-label">🔴 今すぐ（今週中）</div>
                <div class="ai-action-items">{now_html}</div>
            </div>
            <div class="ai-action-month">
                <div class="ai-action-label">🟡 今月中</div>
                <div class="ai-action-items">{month_html}</div>
            </div>
            <div class="ai-action-later">
                <div class="ai-action-label">🟢 来月以降</div>
                <div class="ai-action-items">{later_html}</div>
            </div>
        </div>
    </div>'''


def _convert_normal_section(num, title, body):
    return f'''
    <div class="ai-section-card">
        <div class="ai-section-header">{num}. {_escape(title)}</div>
        <div class="ai-section-body">{_body_to_html(body)}</div>
    </div>'''


def convert_ai_analysis_to_html(text):
    """AIたくま分析テキストをセクションカードHTMLに変換"""
    sections = re.split(r'\n(?=\d+\.\s)', text.strip())
    parts = []
    for section in sections:
        section = section.strip()
        m = re.match(r'^(\d+)\.\s*(.+?)[\n$]', section)
        if not m:
            continue
        num = m.group(1)
        title = m.group(2)
        body = section[m.end():].strip()
        if num == '6':
            parts.append(_convert_action_section(title, body))
        else:
            parts.append(_convert_normal_section(num, title, body))
    return '\n'.join(parts)


def _calc_progress(current, target, direction=''):
    if target == 0:
        return 0
    if direction == 'lower_is_better':
        progress = min(100, int(target / current * 100)) if current > 0 else 0
    else:
        progress = min(100, int(current / target * 100))
    return progress


def _bar_color(progress):
    if progress >= 100:
        return '#2e7d32'
    elif progress >= 70:
        return '#f59e0b'
    else:
        return '#e53e3e'


def build_goals_section(site_config, kw_rankings, ga4_data):
    goals = site_config.get('goals', '')
    if not goals:
        return '''
<div class="section" id="section-goals">
    <div class="section-title">🎯 KGI・KPI達成状況</div>
    <div style="color:#aaa;font-size:13px;padding:8px 0;">目標値未設定</div>
</div>'''

    kgi = goals.get('kgi', '未定')
    targets = goals.get('targets', [])

    # kgi未設定またはtargets空 → 目標値未設定として返す
    if kgi == '未定' or not targets:
        return '''
<div class="section" id="section-goals">
    <div class="section-title">🎯 KGI・KPI達成状況</div>
    <div style="color:#aaa;font-size:13px;padding:8px 0;">目標値未設定</div>
</div>'''

    has_annual   = any(t.get('source', '') in ('ga4_sessions_annual', 'manual_annual') for t in targets)
    only_kw      = all(t.get('source', '') == 'kw_ranking' for t in targets)

    # サブタイトル決定
    if only_kw:
        month_sub = '<div style="font-size:12px;color:#888;margin-bottom:12px;">最新KW順位 vs 目標値</div>'
    elif ga4_data:
        if has_annual and ga4_data.get('annual_period'):
            ga4_month_label = f"{ga4_data['annual_period']}累計"
            month_sub = f'<div style="font-size:12px;color:#888;margin-bottom:12px;">{ga4_month_label} vs 目標値</div>'
        elif ga4_data.get('month'):
            month_sub = f'<div style="font-size:12px;color:#888;margin-bottom:12px;">{ga4_data["month"]}実績 vs 目標値</div>'
        else:
            month_sub = '<div style="font-size:12px;color:#888;margin-bottom:12px;">GA4データなし</div>'
    else:
        month_sub = '<div style="font-size:12px;color:#888;margin-bottom:12px;">GA4データなし</div>'

    cards_html = ''
    for t in targets:
        source    = t.get('source', 'manual')
        label     = t.get('label', '')
        target_val = t.get('target', 0)
        unit      = t.get('unit', '')
        note      = t.get('note', '')
        direction = t.get('direction', '')

        # 現在値の取得
        current = None
        if source == 'ga4_sessions':
            if ga4_data:
                raw = ga4_data.get('sessions', ga4_data.get('セッション数'))
                if raw is not None:
                    try:
                        current = int(str(raw).replace(',', ''))
                    except Exception:
                        pass
        elif source == 'ga4_sessions_annual':
            if ga4_data:
                raw = ga4_data.get('sessions_annual')
                if raw is not None:
                    try:
                        current = int(str(raw).replace(',', ''))
                    except Exception:
                        pass
        elif source == 'manual':
            if ga4_data:
                raw = ga4_data.get('cv', ga4_data.get('CV数'))
                if raw is not None:
                    try:
                        current = int(str(raw).replace(',', ''))
                    except Exception:
                        pass
        elif source == 'manual_annual':
            if ga4_data:
                raw = ga4_data.get('cv_annual')
                if raw is not None:
                    try:
                        current = int(str(raw).replace(',', ''))
                    except Exception:
                        pass
        elif source == 'kw_ranking':
            keyword = t.get('keyword', '')
            current = kw_rankings.get(keyword) if kw_rankings else None
            if current is not None:
                try:
                    current = int(current)
                except Exception:
                    current = None

        target_int = int(target_val)
        note_suffix = f'（{note}）' if note else ''

        if source == 'kw_ranking':
            # KW順位専用カード
            if current is None:
                kw_disp    = '圏外'
                kw_status  = '<div style="font-size:11px;color:#aaa;margin-top:4px;">－</div>'
                kw_color   = '#888'
            elif current <= target_int:
                kw_disp   = f'{current}位'
                kw_status = '<div style="font-size:11px;color:#2e7d32;margin-top:4px;">✅ 達成</div>'
                kw_color  = '#2e7d32'
            else:
                kw_disp   = f'{current}位'
                kw_status = '<div style="font-size:11px;color:#e53e3e;margin-top:4px;">未達成</div>'
                kw_color  = '#e53e3e'

            cards_html += f'''
        <div style="background:#f8f9fc;border-radius:8px;padding:14px 16px;border:0.5px solid #e0e0dc;">
            <div style="font-size:12px;color:#666;margin-bottom:6px;">{label}</div>
            <div style="font-size:22px;font-weight:500;color:{kw_color};">{kw_disp}</div>
            <div style="font-size:11px;color:#888;margin-top:2px;">目標：{target_int}{unit}{note_suffix}</div>
            {kw_status}
        </div>'''
            continue

        if current is None:
            current_disp = '－'
            bar_html = ''
            status_html = '<div style="font-size:11px;color:#aaa;margin-top:4px;">GA4月次データが未取得のため表示できません</div>'
        else:
            if direction == 'lower_is_better':
                if current <= target_int:
                    progress = 100
                    status_label = '✅ 達成'
                else:
                    progress = int(target_int / current * 100) if current > 0 else 0
                    status_label = '未達成'
            else:
                progress = min(int(current / target_int * 100), 100) if target_int > 0 else 0
                status_label = '✅ 達成' if progress >= 100 else f'達成率 {progress}%'

            bar_color = '#2e7d32' if progress >= 100 else ('#f59e0b' if progress >= 70 else '#e53e3e')
            label_color = bar_color

            try:
                current_disp = f'{current:,}'
            except Exception:
                current_disp = str(current)

            bar_html = f'''
            <div style="margin-top:8px;background:#e0e0e0;border-radius:4px;height:6px;">
                <div style="background:{bar_color};border-radius:4px;height:6px;width:{progress}%;max-width:100%;"></div>
            </div>'''
            status_html = f'<div style="font-size:11px;color:{label_color};margin-top:4px;">{status_label}</div>'

        cards_html += f'''
        <div style="background:#f8f9fc;border-radius:8px;padding:14px 16px;border:0.5px solid #e0e0dc;">
            <div style="font-size:12px;color:#666;margin-bottom:6px;">{label}</div>
            <div style="font-size:22px;font-weight:500;">{current_disp}<span style="font-size:13px;font-weight:400;">{unit}</span></div>
            <div style="font-size:11px;color:#888;margin-top:2px;">目標：{target_int:,}{unit}{note_suffix}</div>
            {bar_html}
            {status_html}
        </div>'''

    return f'''
<div class="section" id="section-goals">
    <div class="section-title">🎯 KGI・KPI達成状況</div>
    <div style="font-size:12px;color:#555;margin-bottom:4px;">KGI: {kgi}</div>
    {month_sub}
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;">
        {cards_html}
    </div>
</div>'''


def generate_html(site_name, week_label, summary_rows, pages, insights,
                  current_queries, previous_queries, query_insights,
                  ai_analysis, ai_analysis_is_html,
                  site_config, kw_rankings, ga4_data):
    generated_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    curr = summary_rows[0] if summary_rows else {}
    prev = summary_rows[1] if len(summary_rows) > 1 else {}

    def _diff_html(curr_val, prev_val, unit='', is_position=False):
        if not prev_val:
            return ''
        if is_position:
            diff = round(curr_val - prev_val, 1)
            if diff < 0:
                return f'<span class="up">▲ {abs(diff)}位改善（前週 {prev_val}位）</span>'
            elif diff > 0:
                return f'<span class="down">▼ {diff}位悪化（前週 {prev_val}位）</span>'
            else:
                return f'<span class="neutral">横ばい（前週 {prev_val}位）</span>'
        else:
            if prev_val == 0:
                return ''
            rate = round((curr_val - prev_val) / prev_val * 100, 1)
            if rate > 0:
                return f'<span class="up">▲ {rate}%（前週 {prev_val:,}）</span>'
            elif rate < 0:
                return f'<span class="down">▼ {abs(rate)}%（前週 {prev_val:,}）</span>'
            else:
                return f'<span class="neutral">横ばい（前週 {prev_val:,}）</span>'

    # Chart data: summary_rows[0]=今週, [1]=1週前, ... を古い順（左が古い・右が今週）に並べる
    # reversed で [最古, ..., 1週前, 今週] の順にする
    _chart_rows = list(reversed(summary_rows))  # 例: 5件なら [4週前, 3週前, 2週前, 1週前, 今週]
    _n = len(_chart_rows)
    # ラベル: 左端が最も古い週、右端が今週
    _week_labels = []
    for _i in range(_n):
        _weeks_ago = _n - 1 - _i  # _i=0 → 最古(n-1週前), _i=n-1 → 0(今週)
        _week_labels.append('今週' if _weeks_ago == 0 else f'{_weeks_ago}週前')
    chart_labels_js = '[' + ','.join(f'"{l}"' for l in _week_labels) + ']'
    click_data_js  = '[' + ','.join(str(r.get('clicks', 0)) for r in _chart_rows) + ']'
    imp_data_js    = '[' + ','.join(str(r.get('impressions', 0)) for r in _chart_rows) + ']'
    pos_data_js    = '[' + ','.join(str(r.get('position', 0)) for r in _chart_rows) + ']'
    _pos_vals      = [r.get('position', 0) for r in _chart_rows]
    _pos_max       = max(_pos_vals) if _pos_vals else 50
    _pos_min       = min(_pos_vals) if _pos_vals else 1
    _pos_y_max     = round(_pos_max * 1.2 + 2)
    _pos_y_min     = max(0, round(_pos_min * 0.8 - 1))

    curr_clicks = curr.get('clicks', 0)
    curr_imp = curr.get('impressions', 0)
    curr_ctr = curr.get('ctr', 0)
    curr_pos = curr.get('position', 0)
    prev_clicks = prev.get('clicks', 0)
    prev_imp = prev.get('impressions', 0)
    prev_ctr = prev.get('ctr', 0)
    prev_pos = prev.get('position', 0)

    # GSC KPI cards
    gsc_perf_html = f'''
<div class="performance-section" id="section-gsc-performance">
    <div class="section-title">📊 GSCパフォーマンス</div>
    <div style="font-size:12px;color:#888;margin-bottom:12px;">対象期間：{week_label}</div>
    <div class="performance-grid">
        <div class="kpi">
            <div class="kpi-label">クリック数</div>
            <div class="kpi-value">{curr_clicks:,}</div>
            <div class="kpi-diff">{_diff_html(curr_clicks, prev_clicks)}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">表示回数</div>
            <div class="kpi-value">{curr_imp:,}</div>
            <div class="kpi-diff">{_diff_html(curr_imp, prev_imp)}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">CTR</div>
            <div class="kpi-value">{curr_ctr}%</div>
            <div class="kpi-diff">{_diff_html(curr_ctr, prev_ctr, '%')}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">平均順位</div>
            <div class="kpi-value">{curr_pos}位</div>
            <div class="kpi-diff">{_diff_html(curr_pos, prev_pos, is_position=True)}</div>
        </div>
    </div>
    <div class="chart-row">
        <div class="chart-box">
            <div class="chart-box-title">クリック数推移</div>
            <canvas id="chart-clicks" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-box-title">表示回数推移</div>
            <canvas id="chart-imp" height="120"></canvas>
        </div>
        <div class="chart-box">
            <div class="chart-box-title">平均順位推移</div>
            <canvas id="chart-pos" height="120"></canvas>
        </div>
    </div>
</div>'''

    # GA performance section（ga4_data の有無にかかわらず必ず出力）
    if isinstance(ga4_data, dict) and ga4_data:
        latest = ga4_data
        month_label = latest.get('month', '')
        sessions = latest.get('sessions', latest.get('セッション数', ''))
        cv = latest.get('cv', latest.get('CV数', latest.get('コンバージョン数', '')))
        try:
            sessions_fmt = f"{int(str(sessions).replace(',', '')):,}" if sessions else '-'
        except Exception:
            sessions_fmt = str(sessions)
        try:
            cv_fmt = f"{int(str(cv).replace(',', '')):,}" if cv else '-'
        except Exception:
            cv_fmt = str(cv)
        ga_html = f'''
<div class="section" id="section-ga-performance">
    <div class="section-title">📊 GAパフォーマンス</div>
    <div style="font-size:12px;color:#888;margin-bottom:12px;">{month_label}累計</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="kpi">
            <div class="kpi-label">月間セッション数</div>
            <div class="kpi-value">{sessions_fmt}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">月間CV数</div>
            <div class="kpi-value">{cv_fmt}</div>
        </div>
    </div>
</div>'''
    else:
        ga_html = '''
<div class="section" id="section-ga-performance">
    <div class="section-title">📊 GAパフォーマンス</div>
    <div style="color:#aaa;font-size:13px;padding:8px 0;">GA4月次データが未取得のため表示できません</div>
</div>'''

    # SEO insights
    all_insights = list(insights) + list(query_insights)
    if isinstance(ai_analysis, list):
        all_insights += ai_analysis

    def _insight_class(level):
        level_str = level if isinstance(level, str) else level.decode('utf-8', errors='replace')
        if '🔴' in level_str:
            return 'red', '⚠'
        elif '⚠' in level_str or '🟡' in level_str:
            return 'amber', '!'
        elif '🟢' in level_str or '✅' in level_str:
            return 'green', chr(10003)
        else:
            return 'neutral', '•'

    insights_html = ''
    for ins in all_insights:
        level = ins.get('level', '')
        cls, icon = _insight_class(level)
        title = _escape(ins.get('title', ''))
        detail = _escape(ins.get('detail', '')).replace('\n', '<br>')
        insights_html += f'''
        <div class="insight {cls}">
            <div class="insight-icon">{icon}</div>
            <div class="insight-body">
                <div class="insight-title">{title}</div>
                <div class="insight-desc">{detail}</div>
            </div>
        </div>'''

    seo_summary_html = f'''
<div class="section" id="section-seo-summary">
    <div class="section-title">SEOサマリ</div>
    {insights_html if insights_html else '<div style="color:#aaa;font-size:13px;padding:8px 0;">今週は特筆すべき異常値はありませんでした。</div>'}
</div>'''

    # Query comparison
    all_q = sorted(
        set(list(current_queries.keys()) + list(previous_queries.keys())),
        key=lambda q: current_queries.get(q, {}).get('clicks', 0),
        reverse=True
    )[:20]

    def _pill(status):
        if '🔴' in status or '減少' in status:
            return f'<span class="pill pill-red">{status}</span>'
        elif '✅' in status or '増加' in status or '🆕' in status:
            return f'<span class="pill pill-green">{status}</span>'
        elif '❌' in status:
            return f'<span class="pill pill-red">{status}</span>'
        else:
            return f'<span class="pill">{status}</span>'

    query_rows_html = ''
    for q in all_q:
        curr_q = current_queries.get(q, {})
        prev_q = previous_queries.get(q, {})
        curr_cl = curr_q.get('clicks', '-')
        prev_cl = prev_q.get('clicks', '-')
        curr_pos = curr_q.get('position', '-')
        prev_pos = prev_q.get('position', '-')
        curr_ctr_q = f"{curr_q.get('ctr', '-')}%"
        prev_ctr_q = f"{prev_q.get('ctr', '-')}%"

        if q not in previous_queries:
            status = '🆕 新出現'
        elif q not in current_queries:
            status = '❌ 消滅'
        elif isinstance(curr_cl, int) and isinstance(prev_cl, int) and prev_cl > 0:
            rate = round((curr_cl - prev_cl) / prev_cl * 100, 1)
            if rate > 0:
                status = '✅ 増加'
            elif rate < 0:
                status = '🔴 減少'
            else:
                status = '－ 横ばい'
        else:
            status = '－'

        prev_cl_disp = prev_cl if q in previous_queries else '-'
        prev_pos_disp = prev_pos if q in previous_queries else '-'
        prev_ctr_disp = prev_ctr_q if q in previous_queries else '-'

        query_rows_html += f'''
            <tr>
                <td>{_escape(q)}</td>
                <td>{curr_cl}</td><td>{prev_cl_disp}</td>
                <td>{curr_pos}</td><td>{prev_pos_disp}</td>
                <td>{curr_ctr_q}</td><td>{prev_ctr_disp}</td>
                <td>{_pill(status)}</td>
            </tr>'''

    # New / lost query tables
    new_queries = sorted(
        [q for q in current_queries
         if q not in previous_queries
         and current_queries[q].get('clicks', 0) >= 2
         and current_queries[q].get('impressions', 0) >= 10],
        key=lambda q: current_queries[q].get('clicks', 0), reverse=True
    )[:10]
    lost_queries = sorted(
        [q for q in previous_queries
         if q not in current_queries
         and previous_queries[q].get('clicks', 0) >= 2
         and previous_queries[q].get('impressions', 0) >= 10],
        key=lambda q: previous_queries[q].get('clicks', 0), reverse=True
    )[:10]

    def _query_detail_rows(qs, data):
        rows = ''
        for q in qs:
            d = data.get(q, {})
            rows += f'''
            <tr>
                <td>{_escape(q)}</td>
                <td>{d.get('clicks', 0)}</td>
                <td>{d.get('impressions', 0)}</td>
                <td>{d.get('ctr', 0)}%</td>
                <td>{d.get('position', 0)}位</td>
            </tr>'''
        return rows

    query_section_html = f'''
        <div class="section" id="section-query">
            <div class="section-title">🔍 クエリ</div>
            <div style="margin-bottom:14px;">
                <div style="font-size:12px;font-weight:500;color:#555;margin-bottom:8px;">今週 vs 前週（上位20件）</div>
                <div style="overflow-x:auto;">
                    <table style="min-width:600px;">
                        <thead>
                            <tr>
                                <th>クエリ</th>
                                <th>今週CL</th><th>前週CL</th>
                                <th>今週順位</th><th>前週順位</th>
                                <th>今週CTR</th><th>前週CTR</th>
                                <th>判定</th>
                            </tr>
                        </thead>
                        <tbody>{query_rows_html}</tbody>
                    </table>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px;">
                <div style="background:#e1f5ee;border-radius:8px;padding:12px 14px;border:0.5px solid #b2dfdb;">
                    <div style="font-size:12px;font-weight:600;color:#0f6e56;margin-bottom:8px;">🆕 新出現クエリ（{len(new_queries)}件）</div>
                    <table><thead><tr><th>クエリ</th><th>CL</th><th>IMP</th><th>CTR</th><th>順位</th></tr></thead><tbody>{_query_detail_rows(new_queries, current_queries)}</tbody></table>
                </div>
                <div style="background:#fcebeb;border-radius:8px;padding:12px 14px;border:0.5px solid #ffcdd2;">
                    <div style="font-size:12px;font-weight:600;color:#a32d2d;margin-bottom:8px;">❌ 消滅クエリ（{len(lost_queries)}件）</div>
                    <table><thead><tr><th>クエリ</th><th>CL</th><th>IMP</th><th>CTR</th><th>順位</th></tr></thead><tbody>{_query_detail_rows(lost_queries, previous_queries)}</tbody></table>
                </div>
            </div>
        </div>
        '''

    # AI analysis section
    ai_section_html = ''
    if ai_analysis and not isinstance(ai_analysis, list):
        if bool(ai_analysis_is_html):
            ai_content = str(ai_analysis)
        else:
            ai_content = convert_ai_analysis_to_html(str(ai_analysis).strip())
        if ai_content:
            ai_section_html = f'''
<div class="section" id="section-ai">
    <div class="section-title">🤖 AI分析（たくま）</div>
    {ai_content}
</div>'''

    # Weekly GSC table
    weekly_rows_html = ''
    for row in summary_rows:
        weekly_rows_html += f'''
        <tr>
            <td>{_escape(row.get("label", ""))}</td>
            <td>{row.get("clicks", 0):,}</td>
            <td>{row.get("impressions", 0):,}</td>
            <td>{row.get("ctr", 0)}%</td>
            <td>{row.get("position", 0)}位</td>
        </tr>'''

    weekly_gsc_html = f'''
<div class="section" id="section-weekly-gsc">
    <div class="section-title">週次GSC比較</div>
    <table>
        <thead>
            <tr><th>期間</th><th>クリック数</th><th>表示回数</th><th>CTR</th><th>平均順位</th></tr>
        </thead>
        <tbody>{weekly_rows_html}</tbody>
    </table>
</div>'''

    # Pages table
    def _page_pill(p):
        ctr = p.get('ctr', 0)
        if ctr >= 3.0:
            return '<span class="pill pill-green">良好</span>'
        else:
            return '<span class="pill pill-amber">改善余地</span>'

    page_rows_html = ''
    for p in pages[:20]:
        url = p.get('page', '')
        display_url = url.replace('https://www.', '').replace('https://', '')
        page_rows_html += f'''
        <tr>
            <td class="url" title="{_escape(url)}">{_escape(display_url)}</td>
            <td>{p.get("clicks", 0)}</td>
            <td>{p.get("impressions", 0):,}</td>
            <td>{p.get("ctr", 0)}%</td>
            <td>{p.get("position", 0)}位</td>
            <td>{_page_pill(p)}</td>
        </tr>'''

    pages_html = f'''
<div class="section" id="section-pages">
    <div class="section-title">クリック上位ページ（先週 top20）</div>
    <table>
        <thead>
            <tr><th>ページURL</th><th>クリック</th><th>表示回数</th><th>CTR</th><th>順位</th><th>判定</th></tr>
        </thead>
        <tbody>{page_rows_html}</tbody>
    </table>
</div>'''

    # Goals section
    goals_html = build_goals_section(site_config, kw_rankings, ga4_data)

    # Strategy section
    if site_name == 'レンタルPCネット':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>法人向けパソコンレンタル領域における専門性を軸とした第一想起ブランドの確立</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>テクニカルSEOの徹底によるクローラビリティの最大化</li>
      <li>法人ユーザーのビジネス課題を解決する一次情報の拡充</li>
      <li>タイトル・ディスクリプションのABテストによるクリック率向上</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>主要ページの改修で検索順位を1ページ目へ底上げ</li>
      <li>法人PC特有の悩みに即したコンテンツで潜在層への流入を拡大</li>
      <li>専門性による信頼担保で比較検討層のCVRを向上</li>
    </ul>
  </div>
</section>'''
    elif site_name == 'ラビット探偵社':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>CVR・アクセス量・ブランディングの3軸を連動させ、月間CV600件（2027年6月）の達成を目指す</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>エリア×探偵ページの拡充（浮気調査＋エリアKWで最も成約に近い層を確実に獲得）</li>
      <li>お悩み・知識系コラムの量産（再検索KWを網羅しセッション数を大量獲得）</li>
      <li>トップページのビッグKW上位表示と動線最適化によるブランディング強化</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>エリア特化KWの上位表示による高CVRユーザーの獲得</li>
      <li>コラム施策によるサイト全体のSEO評価底上げと流入拡大</li>
      <li>3施策の相乗効果で月間CV数を現状154件から600件へ拡大</li>
    </ul>
  </div>
</section>'''
    elif site_name == '3大セキュリティ':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>セキュリティ領域における専門性・独自性の高いコンテンツを継続的に積み上げ、ドメイン評価の向上と検索露出の拡大を目指す</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>AI Overviewsへの引用を意識したGEO最適化（結論ファースト・構造化データ・表リスト）の実施</li>
      <li>新規・リライトKWの戦略的選定により、最新のセキュリティニーズと検索意図の変化に対応</li>
      <li>SEO／GEO／UX最適化を組み合わせた記事入稿・調整で検索エンジンとAI双方の評価を強化</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>専門性の高いコンテンツ蓄積によりアルゴリズム変動に強いドメイン評価基盤を構築</li>
      <li>AI Overviewsへの引用増加による新たな検索接点の獲得</li>
      <li>対策KWの順位改善と流入増加によるCV数の向上</li>
    </ul>
  </div>
</section>'''
    elif site_name == '田所商店':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>味噌ラーメンを探すユーザーとの検索接点を広げ、店舗への来店検討につなげる</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>味噌ラーメン・地域名＋味噌ラーメン・味噌文化など周辺KWで未認知層との接点を拡大</li>
      <li>店舗ページ・GBP・メニュー・構造化データを整備し、来店検討しやすい受け皿を構築</li>
      <li>店舗ページ遷移・メニュー遷移・CTAクリックを計測し、来店検討行動を可視化</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>味噌ラーメン関連KWの表示・クリック数増加による新規流入の拡大</li>
      <li>店舗ページのOrganicセッション・PV向上による認知から検討への転換率アップ</li>
      <li>GBP接点・CTAクリック増加による来店数の向上</li>
    </ul>
  </div>
</section>'''
    elif site_name == '表参道デンタルクリニック':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>対策KW周辺の関連情報を拡充し、「歯科専門サイト」としての専門性評価による地盤強化</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>主軸KW（ガミースマイルなど）を支える周辺キーワードのランディングページ拡充</li>
      <li>関連ページ間の内部リンク構造を整備し、主要ページの評価を底上げ</li>
      <li>サイト全体のテーマ性を高め、Googleの専門性・権威性評価を強化</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>周辺KW獲得による専門性の一貫性向上で「この分野ならこのサイト」という信頼蓄積</li>
      <li>アルゴリズム変動時も安定した順位を維持できる評価基盤の構築</li>
      <li>複数ページからの内部リンクで主要ページのCVRを向上</li>
    </ul>
  </div>
</section>'''
    elif site_name == 'クルーズプラネット':
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul>
      <li>関心度の高いツアー条件系・船名系キーワードを優先的に対策し、AI Overviews普及下でもCVを獲得できるサイト構造へ強化する</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul>
      <li>「国内クルーズ」「日本一周クルーズ」「飛鳥クルーズ」など優先度の高いLPの最適化・新規作成</li>
      <li>旅行タイプページ・店舗ページなどテンプレート単位でのSEO最適化</li>
      <li>購買意欲の高いユーザーへのアプローチを強化し、CV行動を促進するLP改善</li>
    </ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul>
      <li>現在上位表示できていないKW群の約半数が5〜10位まで上昇</li>
      <li>AI Overviews普及によるセッション減少下でも、平均CVR0.53%から0.6%への向上</li>
      <li>計画的なロードマップ実行による2026年11月までの段階的な成果創出</li>
    </ul>
  </div>
</section>'''
    else:
        strategy_html = '''
<section id="strategy">
  <h2>📌 戦略方針・主要施策・期待効果</h2>
  <div class="strategy-block">
    <h3>戦略方針</h3>
    <ul><li class="empty-item">－</li></ul>
  </div>
  <div class="strategy-block">
    <h3>主要施策</h3>
    <ul><li class="empty-item">－</li></ul>
  </div>
  <div class="strategy-block">
    <h3>期待効果</h3>
    <ul><li class="empty-item">－</li></ul>
  </div>
</section>'''

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_escape(site_name)} GSC週次レポート {_escape(week_label)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:15px;color:#1a1a1a;background:#f5f5f3;}}
.wrap{{max-width:1080px;margin:0 auto;padding:24px 16px;}}
.header{{background:#fff;border:0.5px solid #e0e0dc;border-radius:12px;padding:18px 24px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;}}
.header-title{{font-size:17px;font-weight:500;}}
.header-sub{{font-size:13px;color:#888;margin-top:4px;}}
.badge{{font-size:12px;padding:3px 10px;border-radius:20px;background:#e1f5ee;color:#0f6e56;}}
.nav-links{{background:#fff;border:0.5px solid #e0e0dc;border-radius:10px;padding:10px 16px;margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,0.06);}}
.nav-links a{{font-size:13px;color:#185fa5;text-decoration:none;padding:4px 10px;border-radius:20px;background:#f0f4ff;border:0.5px solid #c5d3f0;white-space:nowrap;transition:background 0.15s;}}
.nav-links a:hover{{background:#dce6ff;}}
.up{{color:#0f6e56;}}.down{{color:#a32d2d;}}.neutral{{color:#888;}}
.section{{background:#fff;border:0.5px solid #e0e0dc;border-radius:12px;padding:18px 24px;margin-bottom:16px;}}
.section-title{{font-size:15px;font-weight:500;margin-bottom:12px;}}
.performance-section{{background:#fff;border:0.5px solid #e0e0dc;border-radius:12px;padding:18px 24px;margin-bottom:16px;}}
.performance-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}}
.kpi{{background:#f8f9fc;border:0.5px solid #e0e0dc;border-radius:8px;padding:16px;}}
.kpi-label{{font-size:12px;color:#888;margin-bottom:6px;}}
.kpi-value{{font-size:26px;font-weight:500;}}
.kpi-diff{{font-size:12px;margin-top:4px;}}
.insight{{display:flex;gap:10px;padding:12px 14px;border-radius:8px;margin-bottom:8px;}}
.insight:last-child{{margin-bottom:0;}}
.insight.red{{background:#fcebeb;}}.insight.amber{{background:#faeeda;}}.insight.green{{background:#e1f5ee;}}
.insight-icon{{font-size:16px;flex-shrink:0;margin-top:1px;}}
.insight-title{{font-size:14px;font-weight:500;margin-bottom:3px;}}
.insight.red .insight-title{{color:#a32d2d;}}.insight.amber .insight-title{{color:#854f0b;}}.insight.green .insight-title{{color:#0f6e56;}}
.insight-desc{{font-size:13px;color:#555;line-height:1.6;}}
.insight-action{{font-size:13px;margin-top:5px;padding:4px 8px;background:rgba(0,0,0,0.05);border-radius:4px;}}
table{{width:100%;border-collapse:collapse;font-size:14px;}}
th{{text-align:left;padding:8px 10px;color:#888;border-bottom:0.5px solid #e0e0dc;font-weight:400;}}
td{{padding:8px 10px;border-bottom:0.5px solid #e0e0dc;}}
tr:last-child td{{border-bottom:none;}}
.url{{color:#185fa5;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.pill{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;border:0.5px solid #e0e0dc;}}
.pill-red{{background:#fcebeb;color:#a32d2d;}}.pill-amber{{background:#faeeda;color:#854f0b;}}.pill-green{{background:#e1f5ee;color:#0f6e56;}}
.footer{{text-align:center;font-size:12px;color:#aaa;padding:16px 0;}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-top:14px;}}
.chart-box{{background:#fff;border:0.5px solid #e0e0dc;border-radius:12px;padding:16px;}}
.chart-box-title{{font-size:14px;font-weight:500;color:#1a1a1a;margin-bottom:10px;}}
.ai-section-card{{background:#f8f9fc;border-radius:8px;padding:16px 18px;margin-bottom:10px;border-left:3px solid #185fa5;}}
.ai-section-card:last-child{{margin-bottom:0;}}
.ai-section-header{{font-size:15px;font-weight:600;color:#185fa5;margin-bottom:8px;}}
.ai-section-body{{font-size:14px;line-height:1.8;color:#333;}}
.ai-section-body p{{margin-bottom:6px;}}
.ai-section-body p:last-child{{margin-bottom:0;}}
.ai-section-body ul{{margin:6px 0 6px 16px;}}
.ai-section-body li{{margin-bottom:4px;}}
.ai-action-card{{border-left-color:#854f0b;background:#fdf8f0;}}
.ai-action-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:8px;}}
.ai-action-now{{background:#fcebeb;border-radius:6px;padding:12px;}}
.ai-action-month{{background:#faeeda;border-radius:6px;padding:12px;}}
.ai-action-later{{background:#e1f5ee;border-radius:6px;padding:12px;}}
.ai-action-label{{font-size:12px;font-weight:600;margin-bottom:6px;}}
.ai-action-items{{font-size:13px;line-height:1.7;color:#333;}}
.ai-action-items ul{{margin-left:14px;}}
.ai-action-items li{{margin-bottom:3px;}}
#strategy{{background:#fff;border:0.5px solid #e0e0dc;border-radius:12px;padding:18px 24px;margin-bottom:16px;}}
#strategy h2{{font-size:16px;font-weight:500;margin-bottom:12px;}}
.strategy-block{{background:#f8f9fc;border-left:3px solid #185fa5;border-radius:8px;padding:16px 20px;margin-bottom:10px;}}
.strategy-block:last-child{{margin-bottom:0;}}
.strategy-block h3{{font-size:15px;font-weight:600;color:#185fa5;margin-bottom:8px;}}
.strategy-block ul{{margin:0 0 0 16px;}}
.strategy-block li{{font-size:14px;line-height:1.8;color:#333;margin-bottom:4px;}}
.empty-item{{color:#aaa;}}
</style>
</head>
<body>
<div class="wrap">

<div class="header">
    <div>
        <div class="header-title">{_escape(site_name)} — GSC週次レポート</div>
        <div class="header-sub">対象期間：{_escape(week_label)}　／　生成日時：{generated_at}</div>
    </div>
    <span class="badge">自動生成</span>
</div>

<div class="nav-links">
    <a href="#section-goals">🎯 KGI・KPI</a>
    <a href="#strategy">📌 戦略方針</a>
    <a href="#section-gsc-performance">📊 GSCパフォーマンス</a>
    <a href="#section-ga-performance">📊 GAパフォーマンス</a>
    <a href="#section-seo-summary">🔍 SEOサマリ</a>
    {'<a href="#section-ai">🤖 AI分析</a>' if ai_section_html else ''}
    <a href="#section-query">🔍 クエリ</a>
    <a href="#section-weekly-gsc">📋 週次GSC</a>
    <a href="#section-pages">📄 ページ一覧</a>
</div>

{goals_html}
{strategy_html}
<div style="margin: 8px 0 16px; display: flex; gap: 8px; flex-wrap: wrap;">
  <a href="https://tsuyoshi-iwahori-dev.github.io/gsc-report/dashboard/"
     target="_blank"
     style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#185fa5;background:#f0f4f8;border:0.5px solid #c0d0e0;border-radius:6px;padding:6px 12px;text-decoration:none;">
    📋 施策ダッシュボードを見る →
  </a>
  <a href="https://tsuyoshi-iwahori-dev.github.io/gsc-report/article/"
     target="_blank"
     style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#185fa5;background:#f0f4f8;border:0.5px solid #c0d0e0;border-radius:6px;padding:6px 12px;text-decoration:none;">
    📝 新規記事パフォーマンスを見る →
  </a>
</div>
{gsc_perf_html}
{ga_html}
{seo_summary_html}
{ai_section_html}
{query_section_html}

{weekly_gsc_html}
{pages_html}

<div class="footer">自動生成レポート — GSC Weekly Report</div>

</div>
<button onclick="window.scrollTo({{top:0,behavior:'smooth'}})" style="position:fixed;bottom:24px;right:24px;background:#1F3864;color:#fff;border:none;border-radius:50%;width:44px;height:44px;font-size:18px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.2);z-index:999;opacity:0.85;display:flex;align-items:center;justify-content:center;">▲</button>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
(function(){{
  var labels = {chart_labels_js};
  var tickStyle = {{font:{{size:11}},color:'#888'}};
  var gridStyle = {{color:'rgba(0,0,0,0.05)'}};
  var baseOpts = {{
    plugins:{{legend:{{display:false}}}},
    scales:{{
      x:{{ticks:tickStyle,grid:gridStyle}},
      y:{{ticks:tickStyle,grid:gridStyle,beginAtZero:true}}
    }}
  }};
  new Chart(document.getElementById('chart-clicks'),{{
    type:'line',
    data:{{labels:labels,datasets:[{{
      label:'クリック数',data:{click_data_js},
      borderColor:'#2563eb',backgroundColor:'rgba(37,99,235,0.1)',
      borderWidth:2,pointRadius:3,pointBackgroundColor:'#2563eb',tension:0.3,fill:true
    }}]}},
    options:JSON.parse(JSON.stringify(baseOpts))
  }});
  new Chart(document.getElementById('chart-imp'),{{
    type:'line',
    data:{{labels:labels,datasets:[{{
      label:'表示回数',data:{imp_data_js},
      borderColor:'#059669',backgroundColor:'rgba(5,150,105,0.1)',
      borderWidth:2,pointRadius:3,pointBackgroundColor:'#059669',tension:0.3,fill:true
    }}]}},
    options:JSON.parse(JSON.stringify(baseOpts))
  }});
  new Chart(document.getElementById('chart-pos'),{{
    type:'line',
    data:{{labels:labels,datasets:[{{
      label:'平均順位',data:{pos_data_js},
      borderColor:'#d97706',backgroundColor:'rgba(217,119,6,0.1)',
      borderWidth:2,pointRadius:3,pointBackgroundColor:'#d97706',tension:0.3,fill:'start'
    }}]}},
    options:{{
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:tickStyle,grid:gridStyle}},
        y:{{
          reverse:true,
          ticks:{{font:{{size:11}},color:'#888',callback:function(value){{return value+'位';}}}},
          grid:{{color:'rgba(0,0,0,0.05)'}}
        }}
      }}
    }}
  }});
}})();
</script>
</body>
</html>'''


def save_html(html, site_name, week_label):
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports', site_name)
    os.makedirs(output_dir, exist_ok=True)
    filename = f"report_{week_label.replace('〜', '_')}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  ✅ HTMLレポート生成：gsc-report/reports/{site_name}/{filename}')
    return filepath
