"""
Supabase 데이터베이스 연결 및 설정
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional

# 환경 변수 로드 (.env 파일 - 로컬 개발용)
load_dotenv()

# Streamlit Cloud Secrets 또는 환경 변수에서 로드
try:
    import streamlit as st
    # Streamlit Cloud Secrets 우선 (배포 환경)
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))
except:
    # Streamlit이 없는 경우 (일반 Python 스크립트)
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase 클라이언트 초기화
supabase: Optional[Client] = None

try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase 연결 성공")
    else:
        print("⚠️ Supabase 환경 변수가 설정되지 않았습니다.")
except Exception as e:
    print(f"❌ Supabase 연결 실패: {e}")

def get_supabase_client() -> Client:
    """Supabase 클라이언트 반환"""
    if supabase is None:
        raise Exception("Supabase 클라이언트가 초기화되지 않았습니다. .env 파일을 확인하세요.")
    return supabase

def test_connection() -> bool:
    """Supabase 연결 테스트"""
    try:
        client = get_supabase_client()
        # 간단한 쿼리로 연결 테스트
        result = client.table("users").select("count", count="exact").limit(0).execute()
        print(f"✅ Supabase 연결 테스트 성공 (users 테이블 확인)")
        return True
    except Exception as e:
        print(f"❌ Supabase 연결 테스트 실패: {e}")
        return False
