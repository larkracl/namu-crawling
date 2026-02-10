from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('namu_trends.db')
    conn.row_factory = sqlite3.Row
    return conn

# 데이터를 가져와서 공동 순위까지 계산해주는 핵심 함수
def fetch_rankings_data(period, target_date):
    # 기간 설정 로직
    if period == 'daily':
        start_date = target_date + " 00:00:00"
        end_date = target_date + " 23:59:59"
    elif period == 'weekly':
        dt = datetime.strptime(target_date, '%Y-%m-%d')
        start = dt - timedelta(days=dt.weekday())
        end = start + timedelta(days=6)
        start_date = start.strftime('%Y-%m-%d 00:00:00')
        end_date = end.strftime('%Y-%m-%d 23:59:59')
    else: # monthly
        start_date = target_date[:7] + "-01 00:00:00"
        end_date = target_date[:7] + "-31 23:59:59"

    query = """
    SELECT k.name, SUM(CAST((strftime('%s', COALESCE(tl.last_seen_at, datetime('now', 'localtime'))) - strftime('%s', tl.created_at)) / 300 AS INTEGER) + 1) as hits, (SELECT link_url FROM keyword_explanations WHERE keyword_id = k.id ORDER BY id DESC LIMIT 1) as link
    FROM trend_logs tl
    JOIN keywords k ON tl.keyword_id = k.id
    WHERE tl.created_at BETWEEN ? AND ?
    GROUP BY k.id
    ORDER BY hits DESC
    LIMIT 20
"""

    conn = get_db_connection()
    raw_data = conn.execute(query, (start_date, end_date)).fetchall()
    conn.close()

    # [공동 순위 로직 적용] 1, 2, 2, 4 순위 만들기
    rankings = []
    current_rank = 1
    for i, row in enumerate(raw_data):
        # 이전 항목과 횟수가 다르면 현재 인덱스(+1)를 순위로 정함
        if i > 0 and row['hits'] < raw_data[i-1]['hits']:
            current_rank = i + 1

        total_minutes = row['hits'] * 5
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if hours > 0:
            time_display = f"{hours}시간 {minutes}분"
        else:
            time_display = f"{minutes}분"
        
        rankings.append({
            "name": row['name'],
            "hits": time_display,
            "rank": current_rank,
            "link": row['link']
        })
    return rankings

# 1. 일반 웹 페이지 접속용
@app.route('/')
def index():
    period = request.args.get('period', 'daily')
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    # 초기 데이터를 가져와서 페이지를 먼저 띄워줌
    rankings = fetch_rankings_data(period, target_date)
    
    # 제목 설정
    if period == 'daily': title = f"{target_date} 일간 순위"
    elif period == 'weekly': title = "주간 순위"
    else: title = f"{target_date[:7]} 월간 순위"

    return render_template('index.html', rankings=rankings, title=title, period=period, date=target_date)

# 2. 실시간 데이터 갱신용 (JS가 호출함)
@app.route('/api/data')
def api_data():
    period = request.args.get('period', 'daily')
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    rankings = fetch_rankings_data(period, target_date)
    return jsonify(rankings)

@app.route('/api/realtime')
def api_realtime():
    conn = get_db_connection()
    # current_rankings 테이블에서 현재 1~10위를 가져옴
    query = """
        SELECT cr.rank, k.name 
        FROM current_rankings cr
        JOIN keywords k ON cr.keyword_id = k.id
        ORDER BY cr.rank ASC
    """
    data = conn.execute(query).fetchall()
    conn.close()
    return jsonify([{"rank": r['rank'], "name": r['name']} for r in data])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


