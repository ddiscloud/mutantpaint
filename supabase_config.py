"""
Supabase 데이터베이스 연결 및 설정
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional
import sys
import io

# UTF-8 인코딩 설정 (Windows에서 한글 출력)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 환경 변수 로드 (.env 파일 - 로컬 개발용)
load_dotenv()

# Streamlit Cloud Secrets 또는 환경 변수에서 로드
SUPABASE_URL = None
SUPABASE_KEY = None
SUPABASE_SERVICE_ROLE_KEY = None

try:
    import streamlit as st
    # Streamlit Cloud Secrets 우선 (배포 환경)
    if hasattr(st, 'secrets'):
        try:
            SUPABASE_URL = st.secrets["SUPABASE_URL"]
        except:
            pass
        try:
            SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
        except:
            pass
        try:
            SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
        except:
            pass
except:
    pass

# 환경 변수 폴백 (로컬 개발용)
if not SUPABASE_URL:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_SERVICE_ROLE_KEY:
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Supabase 클라이언트 초기화
supabase: Optional[Client] = None

try:
    if SUPABASE_URL and SUPABASE_KEY:
        # 서비스 역할 키가 있으면 사용 (RLS 우회)
        api_key = SUPABASE_SERVICE_ROLE_KEY if SUPABASE_SERVICE_ROLE_KEY else SUPABASE_KEY
        supabase = create_client(SUPABASE_URL, api_key)
        print("OK: Supabase connection successful")
    else:
        print("WARNING: Supabase environment variables not set")
except Exception as e:
    print(f"ERROR: Supabase connection failed: {e}")

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
