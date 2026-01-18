"""
Supabase 데이터베이스 함수들
streamlit_app.py에서 사용할 DB 관련 함수들을 제공합니다.
"""
import json
from typing import Dict, Optional, List
from datetime import datetime
from supabase_config import get_supabase_client
import sys
import io

# UTF-8 인코딩 설정 (Windows에서 한글 출력)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ============================================================================
# 마스터 데이터 함수 (읽기 전용)
# ============================================================================

def load_master_colors() -> dict:
    """Supabase에서 색상 마스터 데이터 로드"""
    try:
        client = get_supabase_client()
        response = client.table("master_colors").select("*").execute()
        
        # 딕셔너리 형식으로 변환 (기존 JSON 구조와 동일하게)
        colors = {}
        for color in response.data:
            colors[color["id"]] = {
                "grade": color["grade"],
                "name": color["name"],
                "hex": color["hex"]
            }
        return colors
    except Exception as e:
        print(f"❌ 색상 데이터 로드 실패: {e}")
        return {}


def load_master_patterns() -> dict:
    """Supabase에서 패턴 마스터 데이터 로드"""
    try:
        client = get_supabase_client()
        response = client.table("master_patterns").select("*").execute()
        
        patterns = {}
        for pattern in response.data:
            patterns[pattern["id"]] = {
                "grade": pattern["grade"],
                "layout": pattern["layout"]
            }
        return patterns
    except Exception as e:
        print(f"❌ 패턴 데이터 로드 실패: {e}")
        return {}


def load_master_skills() -> dict:
    """Supabase에서 스킬 마스터 데이터 로드"""
    try:
        client = get_supabase_client()
        response = client.table("master_skills").select("*").execute()
        
        skills = {}
        for skill in response.data:
            # skill_data JSONB 필드가 전체 정보를 담고 있음
            skills[skill["id"]] = skill["skill_data"]
        return skills
    except Exception as e:
        print(f"❌ 스킬 데이터 로드 실패: {e}")
        return {}


# ============================================================================
# 사용자 게임 데이터 함수
# ============================================================================

def save_game_data(username: str, data: dict) -> bool:
    """게임 데이터를 Supabase에 저장 또는 업데이트"""
    try:
        client = get_supabase_client()
        
        # 먼저 해당 사용자의 데이터가 있는지 확인
        existing = client.table("game_data").select("id").eq("username", username).execute()
        
        if existing.data and len(existing.data) > 0:
            # 이미 있으면 UPDATE
            record_id = existing.data[0]["id"]
            client.table("game_data").update({
                "data": data,
                "updated_at": datetime.now().isoformat()
            }).eq("id", record_id).execute()
        else:
            # 없으면 INSERT
            client.table("game_data").insert({
                "username": username,
                "data": data
            }).execute()
        
        return True
    except Exception as e:
        print(f"❌ 게임 데이터 저장 실패 ({username}): {e}")
        return False


def load_game_data(username: str) -> Optional[dict]:
    """Supabase에서 게임 데이터 로드"""
    try:
        client = get_supabase_client()
        response = client.table("game_data").select("data").eq("username", username).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]["data"]
        return None
    except Exception as e:
        print(f"❌ 게임 데이터 로드 실패 ({username}): {e}")
        return None


def check_user_exists(username: str) -> bool:
    """사용자 존재 여부 확인"""
    try:
        client = get_supabase_client()
        response = client.table("users").select("id").eq("username", username).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"❌ 사용자 확인 실패: {e}")
        return False


def create_user(username: str, password_hash: str) -> bool:
    """새 사용자 생성"""
    try:
        client = get_supabase_client()
        client.table("users").insert({
            "username": username,
            "password_hash": password_hash
        }).execute()
        print(f"✅ 사용자 '{username}' 생성 완료")
        return True
    except Exception as e:
        error_msg = str(e)
        if "duplicate" in error_msg.lower() or "unique" in error_msg.lower():
            print(f"⚠️ 사용자 '{username}' 이미 존재함")
        else:
            print(f"❌ 사용자 생성 실패 ({username}): {e}")
        return False


def get_user_password_hash(username: str) -> Optional[str]:
    """사용자 비밀번호 해시 조회"""
    try:
        client = get_supabase_client()
        response = client.table("users").select("password_hash").eq("username", username).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]["password_hash"]
        return None
    except Exception as e:
        print(f"❌ 비밀번호 해시 조회 실패: {e}")
        return None


# ============================================================================
# 시즌 히스토리 함수
# ============================================================================

def load_season_history() -> dict:
    """Supabase에서 시즌 히스토리 로드"""
    try:
        client = get_supabase_client()
        response = client.table("season_history").select("season_data").order("created_at", desc=True).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]["season_data"]
        return {}
    except Exception as e:
        print(f"❌ 시즌 히스토리 로드 실패: {e}")
        return {}


def save_season_history(season_data: dict) -> bool:
    """시즌 히스토리를 Supabase에 저장"""
    try:
        client = get_supabase_client()
        client.table("season_history").insert({
            "season_data": season_data
        }).execute()
        return True
    except Exception as e:
        print(f"❌ 시즌 히스토리 저장 실패: {e}")
        return False


def get_all_user_data() -> List[Dict]:
    """모든 사용자의 게임 데이터 조회 (관리자용)"""
    try:
        client = get_supabase_client()
        response = client.table("game_data").select("username, data").execute()
        return response.data
    except Exception as e:
        print(f"❌ 모든 사용자 데이터 조회 실패: {e}")
        return []


# ============================================================================
# 사용자 관리 함수 (관리자용)
# ============================================================================

def get_all_users() -> List[Dict]:
    """모든 사용자 정보 조회"""
    try:
        client = get_supabase_client()
        response = client.table("users").select("id, username, created_at, updated_at").order("created_at", desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"사용자 목록 조회 실패: {e}")
        return []


def get_user_info(username: str) -> Optional[Dict]:
    """특정 사용자의 상세 정보 조회"""
    try:
        client = get_supabase_client()
        response = client.table("users").select("*").eq("username", username).execute()
        
        if response.data and len(response.data) > 0:
            user = response.data[0]
            # 비밀번호 해시는 제외
            user.pop("password_hash", None)
            return user
        return None
    except Exception as e:
        print(f"사용자 정보 조회 실패 ({username}): {e}")
        return None


def delete_user(username: str) -> bool:
    """사용자 계정 삭제"""
    try:
        client = get_supabase_client()
        
        # game_data와 season_history 먼저 삭제
        client.table("game_data").delete().eq("username", username).execute()
        client.table("season_history").delete().eq("username", username).execute()
        
        # 사용자 계정 삭제
        response = client.table("users").delete().eq("username", username).execute()
        print(f"사용자 '{username}' 삭제 완료")
        return True
    except Exception as e:
        print(f"사용자 삭제 실패 ({username}): {e}")
        return False


def get_user_game_stats(username: str) -> Optional[Dict]:
    """사용자의 게임 통계 조회"""
    try:
        client = get_supabase_client()
        
        # 게임 데이터
        game_response = client.table("game_data").select("data").eq("username", username).execute()
        game_data = None
        if game_response.data and len(game_response.data) > 0:
            game_data = game_response.data[0].get("data", {})
        
        # 시즌 히스토리
        season_response = client.table("season_history").select("data").eq("username", username).execute()
        season_data = None
        if season_response.data and len(season_response.data) > 0:
            season_data = season_response.data[0].get("data", {})
        
        return {
            "game_data": game_data,
            "season_history": season_data
        }
    except Exception as e:
        print(f"게임 통계 조회 실패 ({username}): {e}")
        return None

# ============================================================================
# 초기화 함수
# ============================================================================

def init_supabase_db():
    """Supabase 데이터베이스 초기화 (연결 테스트)"""
    try:
        client = get_supabase_client()
        # 간단한 쿼리로 연결 테스트
        client.table("master_colors").select("count", count="exact").limit(0).execute()
        print("✅ Supabase 데이터베이스 초기화 완료")
        return True
    except Exception as e:
        print(f"❌ Supabase 데이터베이스 초기화 실패: {e}")
        return False
