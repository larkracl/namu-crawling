import sqlite3

def drop_explainer_table():
    conn = sqlite3.connect("namu_trends.db")
    cursor = conn.cursor()
    
    # 테이블 삭제
    cursor.execute("DROP TABLE IF EXISTS keyword_explanations")
    
    conn.commit()
    conn.close()
    print("✅ keyword_explanations 테이블이 성공적으로 삭제되었습니다!")

if __name__ == "__main__":
    drop_explainer_table()
