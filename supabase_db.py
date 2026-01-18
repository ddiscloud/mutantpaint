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


def delete_user(username: str) -> tuple:
    """사용자 계정 삭제
    
    Returns:
        (success: bool, message: str)
    """
    try:
        client = get_supabase_client()
        
        # game_data 삭제
        try:
            client.table("game_data").delete().eq("username", username).execute()
            print(f"✅ '{username}'의 게임 데이터 삭제 완료")
        except Exception as e:
            print(f"⚠️ 게임 데이터 삭제 실패: {e}")
        
        # season_history 삭제
        try:
            client.table("season_history").delete().eq("username", username).execute()
            print(f"✅ '{username}'의 시즌 데이터 삭제 완료")
        except Exception as e:
            print(f"⚠️ 시즌 데이터 삭제 실패: {e}")
        
        # 사용자 계정 삭제
        response = client.table("users").delete().eq("username", username).execute()
        print(f"✅ 사용자 '{username}' 삭제 완료")
        return True, f"사용자 '{username}'이(가) 정상적으로 삭제되었습니다."
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 사용자 삭제 실패 ({username}): {e}")
        return False, f"삭제 중 오류 발생: {error_msg}"


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


def get_user_instances(username: str) -> List[Dict]:
    """사용자의 모든 개체 조회"""
    try:
        client = get_supabase_client()
        response = client.table("game_data").select("data").eq("username", username).execute()
        
        if response.data and len(response.data) > 0:
            game_data = response.data[0].get("data", {})
            instances = game_data.get("instances", [])
            return instances if isinstance(instances, list) else []
        return []
    except Exception as e:
        print(f"개체 목록 조회 실패 ({username}): {e}")
        return []


def delete_user_instance(username: str, instance_id: str) -> tuple:
    """사용자의 특정 개체 삭제
    
    Returns:
        (success: bool, message: str)
    """
    try:
        client = get_supabase_client()
        response = client.table("game_data").select("data").eq("username", username).execute()
        
        if not response.data or len(response.data) == 0:
            return False, f"사용자 '{username}'의 게임 데이터를 찾을 수 없습니다."
        
        game_data = response.data[0].get("data", {})
        instances = game_data.get("instances", [])
        
        # 개체 찾기
        original_count = len(instances)
        instances = [inst for inst in instances if inst.get("id") != instance_id]
        
        if len(instances) == original_count:
            return False, f"ID '{instance_id}'인 개체를 찾을 수 없습니다."
        
        # 업데이트
        game_data["instances"] = instances
        client.table("game_data").update({
            "data": game_data
        }).eq("username", username).execute()
        
        print(f"✅ 사용자 '{username}'의 개체 '{instance_id}' 삭제 완료")
        return True, f"개체가 정상적으로 삭제되었습니다."
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 개체 삭제 실패 ({username}, {instance_id}): {e}")
        return False, f"삭제 중 오류 발생: {error_msg}"


def update_user_mutation_settings(username: str, mutation_bonus: float, max_chain_mutations: int) -> tuple:
    """사용자의 돌연변이 설정 변경
    
    Args:
        username: 사용자명
        mutation_bonus: 돌연변이 확률 보너스 (0.0 ~ 0.5)
        max_chain_mutations: 최대 연쇄 돌연변이 횟수 (3, 4, 5)
    
    Returns:
        (success: bool, message: str)
    """
    try:
        client = get_supabase_client()
        response = client.table("game_data").select("data").eq("username", username).execute()
        
        if not response.data or len(response.data) == 0:
            return False, f"사용자 '{username}'의 게임 데이터를 찾을 수 없습니다."
        
        game_data = response.data[0].get("data", {})
        
        # 값 유효성 검사
        if mutation_bonus < 0 or mutation_bonus > 0.5:
            return False, "돌연변이 보너스는 0.0 ~ 0.5 사이여야 합니다."
        
        if max_chain_mutations not in [3, 4, 5]:
            return False, "최대 연쇄 횟수는 3, 4, 5 중 하나여야 합니다."
        
        # 업데이트
        old_bonus = game_data.get("mutation_bonus", 0.0)
        old_chain = game_data.get("max_chain_mutations", 3)
        
        game_data["mutation_bonus"] = mutation_bonus
        game_data["max_chain_mutations"] = max_chain_mutations
        
        client.table("game_data").update({
            "data": game_data
        }).eq("username", username).execute()
        
        print(f"✅ '{username}'의 돌연변이 설정 변경: 보너스 {old_bonus} → {mutation_bonus}, 연쇄 {old_chain} → {max_chain_mutations}")
        return True, f"설정이 변경되었습니다. (보너스: {mutation_bonus*100:.0f}%, 최대 연쇄: {max_chain_mutations}회)"
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 돌연변이 설정 변경 실패 ({username}): {e}")
        return False, f"변경 중 오류 발생: {error_msg}"

# ============================================================================
# 랜덤박스 템플릿 관리
# ============================================================================

def load_box_templates(active_only: bool = True) -> List[Dict]:
    """랜덤박스 템플릿 목록 로드"""
    try:
        client = get_supabase_client()
        query = client.table("box_templates").select("*")
        if active_only:
            query = query.eq("is_active", True)
        response = query.order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"❌ 박스 템플릿 로드 실패: {e}")
        return []


def get_box_template(template_id: str) -> Optional[Dict]:
    """특정 랜덤박스 템플릿 로드"""
    try:
        client = get_supabase_client()
        response = client.table("box_templates").select("*").eq("id", template_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"❌ 박스 템플릿 로드 실패 ({template_id}): {e}")
        return None


def create_box_template(template_id: str, name: str, description: str, 
                       conditions: dict, created_by: str) -> bool:
    """새 랜덤박스 템플릿 생성"""
    try:
        client = get_supabase_client()
        client.table("box_templates").insert({
            "id": template_id,
            "name": name,
            "description": description,
            "conditions": conditions,
            "created_by": created_by,
            "is_active": True
        }).execute()
        print(f"✅ 박스 템플릿 생성: {name} ({template_id})")
        return True
    except Exception as e:
        print(f"❌ 박스 템플릿 생성 실패: {e}")
        return False


def update_box_template(template_id: str, name: str = None, description: str = None,
                       conditions: dict = None, is_active: bool = None) -> bool:
    """랜덤박스 템플릿 업데이트"""
    try:
        client = get_supabase_client()
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if conditions is not None:
            update_data["conditions"] = conditions
        if is_active is not None:
            update_data["is_active"] = is_active
        
        client.table("box_templates").update(update_data).eq("id", template_id).execute()
        print(f"✅ 박스 템플릿 업데이트: {template_id}")
        return True
    except Exception as e:
        print(f"❌ 박스 템플릿 업데이트 실패: {e}")
        return False


def delete_box_template(template_id: str) -> bool:
    """랜덤박스 템플릿 삭제"""
    try:
        client = get_supabase_client()
        client.table("box_templates").delete().eq("id", template_id).execute()
        print(f"✅ 박스 템플릿 삭제: {template_id}")
        return True
    except Exception as e:
        print(f"❌ 박스 템플릿 삭제 실패: {e}")
        return False


# ============================================================================
# 우편함 관리
# ============================================================================

def load_mailbox(username: str, unclaimed_only: bool = True) -> List[Dict]:
    """사용자 우편함 로드"""
    try:
        client = get_supabase_client()
        query = client.table("mailbox").select("*").eq("user_id", username)
        if unclaimed_only:
            query = query.eq("claimed", False)
        response = query.order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"❌ 우편함 로드 실패 ({username}): {e}")
        return []


def send_mail(user_id: str, mail_type: str, message: str,
             instance_data: dict = None, box_template_id: str = None) -> bool:
    """우편 발송"""
    try:
        client = get_supabase_client()
        import uuid
        
        mail_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": mail_type,
            "message": message,
            "claimed": False
        }
        
        if mail_type == "instance":
            mail_data["instance_data"] = instance_data
        elif mail_type == "box":
            mail_data["box_template_id"] = box_template_id
        
        client.table("mailbox").insert(mail_data).execute()
        print(f"✅ 우편 발송: {user_id} <- {mail_type}")
        return True
    except Exception as e:
        print(f"❌ 우편 발송 실패: {e}")
        return False


def claim_mail(mail_id: str) -> Optional[Dict]:
    """우편 수령 (데이터 반환 후 claimed=True)"""
    try:
        client = get_supabase_client()
        
        # 우편 조회
        response = client.table("mailbox").select("*").eq("id", mail_id).execute()
        if not response.data:
            return None
        
        mail = response.data[0]
        
        # 이미 수령했으면 None
        if mail["claimed"]:
            return None
        
        # 수령 처리
        client.table("mailbox").update({
            "claimed": True,
            "claimed_at": datetime.now().isoformat()
        }).eq("id", mail_id).execute()
        
        print(f"✅ 우편 수령: {mail_id}")
        return mail
    except Exception as e:
        print(f"❌ 우편 수령 실패: {e}")
        return None


def delete_mail(mail_id: str) -> bool:
    """우편 삭제"""
    try:
        client = get_supabase_client()
        client.table("mailbox").delete().eq("id", mail_id).execute()
        print(f"✅ 우편 삭제: {mail_id}")
        return True
    except Exception as e:
        print(f"❌ 우편 삭제 실패: {e}")
        return False


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
