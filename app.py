from flask import Flask, render_template, request
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('namu_trends.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    period = request.args.get('period', 'daily') # daily, weekly, monthly
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # 기간 설정 로직
    if period == 'daily':
        start_date = target_date + " 00:00:00"
        end_date = target_date + " 23:59:59"
        title = f"{target_date} 일간 순위"
    elif period == 'weekly':
        # 선택한 날짜가 포함된 주의 월요일부터 일요일까지
        dt = datetime.strptime(target_date, '%Y-%m-%d')
        start = dt - timedelta(days=dt.weekday())
        end = start + timedelta(days=6)
        start_date = start.strftime('%Y-%m-%d 00:00:00')
        end_date = end.strftime('%Y-%m-%d 23:59:59')
        title = f"{start.strftime('%m/%d')} ~ {end.strftime('%m/%d')} 주간 순위"
    else: # monthly
        start_date = target_date[:7] + "-01 00:00:00"
        end_date = target_date[:7] + "-31 23:59:59"
        title = f"{target_date[:7]} 월간 순위"

    # 등장 횟수(히트수) 기준 쿼리
    query = """
        SELECT k.name, COUNT(tl.id) as hits
        FROM trend_logs tl
        JOIN keywords k ON tl.keyword_id = k.id
        WHERE tl.created_at BETWEEN ? AND ?
        GROUP BY k.id
        ORDER BY hits DESC
        LIMIT 20
    """
    rankings = cursor.execute(query, (start_date, end_date)).fetchall()
    conn.close()

    return render_template('index.html', rankings=rankings, title=title, period=period, date=target_date)

if __name__ == '__main__':
    # 외부 접속 허용을 위해 0.0.0.0으로 실행
    app.run(host='0.0.0.0', port=5000)
