import time
import sqlite3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def init_explainer_db():
    conn = sqlite3.connect("namu_trends.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword_id INTEGER,
            link_url TEXT UNIQUE, 
            title TEXT,
            created_at DATETIME,
            FOREIGN KEY (keyword_id) REFERENCES keywords(id)
        )
    """)
    conn.commit()
    conn.close()

def fetch_explanations():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = "/data/data/com.termux/files/usr/bin/chromium"
    service = Service("/data/data/com.termux/files/usr/bin/chromedriver")
    
    driver = None
    conn = None
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        conn = sqlite3.connect("namu_trends.db")
        cursor = conn.cursor()

        # [핵심 수정] 최근 2일 이내에 로그(trend_logs)에 기록된 키워드만 가져오기
        print(f"[{datetime.now()}] 활성 키워드 목록(최근 2일) 불러오는 중...")
        cursor.execute("""
            SELECT DISTINCT k.id, k.name 
            FROM keywords k
            JOIN trend_logs tl ON k.id = tl.keyword_id
            WHERE tl.created_at >= datetime('now', '-2 days', 'localtime')
               OR tl.last_seen_at >= datetime('now', '-2 days', 'localtime')
        """)
        active_keywords = cursor.fetchall()
        print(f"[Debug] 대조 대상 키워드 개수: {len(active_keywords)}개")

        driver.get("https://arca.live/b/namuhotnow")
        time.sleep(7) 
        
        articles = driver.find_elements(By.CSS_SELECTOR, "a.vrow.column")
        
        match_count = 0
        for article in articles:
            try:
                title_el = article.find_element(By.CSS_SELECTOR, ".title")
                title = title_el.text.strip()
                link = article.get_attribute("href")
                
                # 활성화된 키워드들하고만 대조!
                for k_id, k_name in active_keywords:
                    if k_name in title:
                        cursor.execute("""
                            INSERT OR IGNORE INTO keyword_explanations (keyword_id, link_url, title, created_at)
                            VALUES (?, ?, ?, ?)
                        """, (k_id, link, title, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        match_count += 1
            except: continue
            
        conn.commit()
        print(f"[{datetime.now()}] 매칭 완료! 새로 추가된 링크: {match_count}개")

    except Exception as e:
        print(f"Explainer Error: {e}")
    finally:
        if conn: conn.close()
        if driver: driver.quit()

if __name__ == "__main__":
    init_explainer_db()
    while True:
        fetch_explanations()
        print("15분 대기 중...")
        time.sleep(900)
