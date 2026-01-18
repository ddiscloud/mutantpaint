"""
개체 데이터에 누락된 필드를 자동으로 추가하는 스크립트
"""
from supabase_db import get_supabase_client
from datetime import datetime

def fix_missing_fields():
    """모든 유저의 개체에 누락된 필드 추가"""
    try:
        client = get_supabase_client()
        
        # 모든 유저 조회
        users_response = client.table("users").select("username").execute()
        
        if not users_response.data:
            print("유저가 없습니다.")
            return
        
        total_fixed = 0
        
        for user in users_response.data:
            username = user["username"]
            
            try:
                # 게임 데이터 조회
                game_response = client.table("game_data").select("id, data").eq("username", username).execute()
                
                if not game_response.data or len(game_response.data) == 0:
                    continue
                
                record_id = game_response.data[0]["id"]
                game_data = game_response.data[0]["data"]
                
                instances = game_data.get("instances", [])
                if not instances:
                    continue
                
                updated = False
                for inst in instances:
                    # 필수 필드 추가
                    if "is_locked" not in inst:
                        inst["is_locked"] = False
                        updated = True
                    if "is_favorite" not in inst:
                        inst["is_favorite"] = False
                        updated = True
                    if "birth_time" not in inst:
                        inst["birth_time"] = datetime.now().isoformat()
                        updated = True
                    if "mutation" not in inst:
                        inst["mutation"] = {"count": 0, "fields": []}
                        updated = True
                    if "power_score" not in inst:
                        # 간단한 계산
                        stats = inst.get("stats", {"hp": 10, "atk": 1, "ms": 1})
                        inst["power_score"] = stats.get("hp", 10)
                        updated = True
                
                if updated:
                    # DB 업데이트
                    client.table("game_data").update({
                        "data": game_data,
                        "updated_at": datetime.now().isoformat()
                    }).eq("id", record_id).execute()
                    
                    print(f"✅ '{username}': {len(instances)}개 개체 필드 수정")
                    total_fixed += 1
                
            except Exception as e:
                print(f"❌ '{username}' 처리 실패: {e}")
        
        print(f"\n총 {total_fixed}명의 데이터 수정 완료")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    print("=== 개체 필드 수정 시작 ===\n")
    fix_missing_fields()
