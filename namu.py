import time
import sqlite3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# ==========================================
# [Database Layer]
# ==========================================
def init_db():
    conn = sqlite3.connect("namu_trends.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            total_hits INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword_id INTEGER,
            created_at DATETIME,
            last_seen_at DATETIME DEFAULT NULL,
            FOREIGN KEY (keyword_id) REFERENCES keywords(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_rankings (
            rank INTEGER PRIMARY KEY,
            keyword_id INTEGER,
            FOREIGN KEY (keyword_id) REFERENCES keywords(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_name ON keywords(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_active ON trend_logs(last_seen_at)")
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE trend_logs SET last_seen_at = ? WHERE last_seen_at IS NULL", (now_str,))
    cursor.execute("DELETE FROM current_rankings")
    conn.commit()
    conn.close()

def sync_trends_to_db(current_trends):
    try:
        conn = sqlite3.connect("namu_trends.db")
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            SELECT k.name, tl.id FROM trend_logs tl 
            JOIN keywords k ON tl.keyword_id = k.id WHERE tl.last_seen_at IS NULL
        """)
        active_sessions = {row[0]: row[1] for row in cursor.fetchall()}
        keyword_ids = {}

        for keyword in current_trends:
            cursor.execute("SELECT id FROM keywords WHERE name = ?", (keyword,))
            row = cursor.fetchone()
            if row:
                k_id = row[0]
                cursor.execute("UPDATE keywords SET total_hits = total_hits + 1 WHERE id = ?", (k_id,))
            else:
                cursor.execute("INSERT INTO keywords (name, total_hits) VALUES (?, 1)", (keyword,))
                k_id = cursor.lastrowid
            keyword_ids[keyword] = k_id

            if keyword in active_sessions:
                del active_sessions[keyword]
            else:
                cursor.execute("INSERT INTO trend_logs (keyword_id, created_at) VALUES (?, ?)", (k_id, now_str))

        for keyword, log_id in active_sessions.items():
            cursor.execute("UPDATE trend_logs SET last_seen_at = ? WHERE id = ?", (now_str, log_id))

        cursor.execute("DELETE FROM current_rankings")
        for i, keyword in enumerate(current_trends):
            if keyword in keyword_ids:
                cursor.execute("INSERT INTO current_rankings (rank, keyword_id) VALUES (?, ?)", 
                               (i + 1, keyword_ids[keyword]))
        conn.commit()
        conn.close()
        
        # 콘솔 출력 (UI 대체)
        print(f"\n[{now_str}] 실시간 트렌드 TOP 10")
        print("-" * 40)
        for i, k in enumerate(current_trends):
            print(f"{i+1}위: {k}")
        print("-" * 40)

    except Exception as e:
        print(f"DB Error: {e}")

# ==========================================
# [Crawler Layer]
# ==========================================
def fetch_trends():
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # WSL/Ubuntu 24.04 환경에 맞춰 자동 설치
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get("https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84%ED%82%A4:%EB%8C%80%EB%AC%B8")
        time.sleep(5) 

        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/Go?q=']")
        trend_list = []
        seen = set()
        for el in elements:
            word = el.get_attribute("textContent").strip()
            if word and word not in seen and not word.isdigit():
                trend_list.append(word)
                seen.add(word)
            if len(trend_list) >= 10: break
        
        return trend_list

    except Exception as e:
        print(f"Crawling Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

# ==========================================
# [Main Execution Loop]
# ==========================================
if __name__ == "__main__":
    init_db()
    print("수집기 작동 시작... (종료하려면 Ctrl+C)")

    while True:
        trends = fetch_trends()
        if trends:
            sync_trends_to_db(trends)
        else:
            print("데이터 수집 실패")

        # 시간 계산 및 대기
        now = datetime.now()
        minutes_to_add = 2 - (now.minute % 2)
        next_target = now + timedelta(minutes=minutes_to_add)
        next_target = next_target.replace(second=0, microsecond=0)
        if next_target <= now: next_target += timedelta(minutes=2)
        
        wait_seconds = (next_target - now).total_seconds()
        print(f"다음 업데이트: {next_target.strftime('%H:%M:%S')} ({int(wait_seconds)}초 대기)", flush=True)
        
        time.sleep(wait_seconds)
