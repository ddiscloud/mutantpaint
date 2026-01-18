"""
Supabase에 우편함 및 랜덤박스 테이블 생성
"""
from supabase_config import get_supabase_client

def create_mailbox_tables():
    """우편함 및 랜덤박스 테이블 생성"""
    client = get_supabase_client()
    
    # SQL 파일 읽기
    with open('create_mailbox_tables.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # SQL 실행 (Supabase Python client는 raw SQL 직접 실행 불가)
    # 대신 직접 테이블을 확인하고 샘플 데이터만 삽입
    
    print("📋 SQL 파일 내용:")
    print(sql)
    print("\n" + "="*60)
    print("⚠️  위의 SQL을 Supabase 대시보드의 SQL Editor에서 직접 실행하세요.")
    print("="*60)
    print("\n📍 실행 방법:")
    print("1. Supabase 대시보드 접속 (https://app.supabase.com)")
    print("2. 프로젝트 선택")
    print("3. SQL Editor 메뉴 클릭")
    print("4. 위의 SQL 코드 복사 & 붙여넣기")
    print("5. 'Run' 버튼 클릭")

if __name__ == "__main__":
    create_mailbox_tables()
