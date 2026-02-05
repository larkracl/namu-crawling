import time
import sqlite3
import traceback
import sys
from datetime import datetime, timedelta

# Selenium 관련 라이브러리
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
        
        print(f"\n[{now_str}] 실시간 트렌드 TOP {len(current_trends)}")
        print("-" * 40)
        for i, k in enumerate(current_trends):
            print(f"{i+1}위: {k}")
        print("-" * 40)

    except Exception as e:
        print(f"DB Error: {e}")
        traceback.print_exc()

# ==========================================
# [Crawler Layer]
# ==========================================
def fetch_trends():
    driver = None
    try:
        print("[Debug] 크롬 옵션 설정 중...")
        chrome_options = Options()
        
        # [Linux/Ubuntu Headless 필수 설정]
        chrome_options.add_argument("--headless=new") # 최신 헤드리스 모드
        chrome_options.add_argument("--no-sandbox") # 리눅스 권한 문제 방지
        chrome_options.add_argument("--disable-dev-shm-usage") # 메모리 공유 이슈 방지
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080") # 화면 크기가 없으면 요소가 렌더링 안 될 수 있음
        chrome_options.add_argument("--remote-debugging-port=9222") # 디버깅 포트 (충돌 방지용)
        
        # 봇 탐지 회피를 위한 User-Agent 및 언어 설정
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("accept-language=ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7")
        
        # WebDriver 설치 및 실행
        print("[Debug] ChromeDriver 설치 및 실행 시도...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        target_url = "https://namu.wiki/w/%EB%82%98%EB%AC%B4%EC%9C%84%ED%82%A4:%EB%8C%80%EB%AC%B8"
        print(f"[Debug] 페이지 접속 시도: {target_url}")
        
        driver.get(target_url)
        
        # 페이지 로딩 대기 (Cloudflare 챌린지 등이 있을 수 있으므로 넉넉히)
        time.sleep(7) 

        # 현재 페이지 제목 확인 (디버깅용)
        print(f"[Debug] 현재 페이지 제목: {driver.title}")

        # 요소 찾기
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/Go?q=']")
        print(f"[Debug] 발견된 후보 요소 개수: {len(elements)}")
        
        trend_list = []
        seen = set()
        
        for el in elements:
            try:
                # 텍스트 추출 시도 (숨겨진 요소일 경우 빈 문자열일 수 있음)
                word = el.get_attribute("textContent").strip()
                if word and word not in seen and not word.isdigit():
                    trend_list.append(word)
                    seen.add(word)
                if len(trend_list) >= 10: break
            except Exception as e:
                print(f"[Debug] 요소 텍스트 추출 중 에러: {e}")
                continue
        
        if not trend_list:
            print("[Debug] 경고: 수집된 트렌드가 0개입니다.")
            # 페이지 소스 일부 출력하여 차단 여부 확인
            print("[Debug] 페이지 소스 일부(500자):")
            print(driver.page_source[:500])
            
        return trend_list

    except Exception as e:
        print(f"\n[Critical Error] 크롤링 실패")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Msg: {e}")
        traceback.print_exc() # 상세 에러 스택 출력
        return []
    finally:
        if driver:
            try:
                driver.quit()
                print("[Debug] 드라이버 종료 완료")
            except:
                pass

# ==========================================
# [Main Execution Loop]
# ==========================================
if __name__ == "__main__":
    # 버퍼링 없이 출력 강제 (리눅스 로그 확인용)
    sys.stdout.reconfigure(line_buffering=True)
    
    init_db()
    print("=== 나무위키 실시간 검색어 수집기 (Ubuntu CLI Ver) ===")
    print("수집기 작동 시작... (종료하려면 Ctrl+C)")

    while True:
        try:
            trends = fetch_trends()
            if trends:
                sync_trends_to_db(trends)
            else:
                print("데이터 수집 실패 (재시도 대기)")

            # 시간 계산 및 대기
            now = datetime.now()
            minutes_to_add = 2 - (now.minute % 2)
            next_target = now + timedelta(minutes=minutes_to_add)
            next_target = next_target.replace(second=0, microsecond=0)
            if next_target <= now: next_target += timedelta(minutes=2)
            
            wait_seconds = (next_target - now).total_seconds()
            print(f"다음 업데이트: {next_target.strftime('%H:%M:%S')} ({int(wait_seconds)}초 대기)")
            
            time.sleep(wait_seconds)
            
        except KeyboardInterrupt:
            print("\n프로그램을 종료합니다.")
            break
        except Exception as main_e:
            print(f"Main Loop Error: {main_e}")
            time.sleep(60) # 에러 발생 시 1분 대기

