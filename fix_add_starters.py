"""
시즌 초기화 후 Starter A, B가 없는 유저들에게 지급하는 스크립트
"""
from supabase_db import get_supabase_client, create_initial_starter_instances
from datetime import datetime

def add_starters_to_all_users():
    """모든 유저에게 Starter A, B 지급"""
    try:
        client = get_supabase_client()
        
        # 모든 유저 조회
        users_response = client.table("users").select("username").execute()
        
        if not users_response.data:
            print("유저가 없습니다.")
            return
        
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        for user in users_response.data:
            username = user["username"]
            
            try:
                # 게임 데이터 조회
                game_response = client.table("game_data").select("id, data").eq("username", username).execute()
                
                if not game_response.data or len(game_response.data) == 0:
                    print(f"⚠️ '{username}': 게임 데이터 없음")
                    skip_count += 1
                    continue
                
                record_id = game_response.data[0]["id"]
                game_data = game_response.data[0]["data"]
                
                # 이미 개체가 있으면 스킵
                if game_data.get("instances") and len(game_data["instances"]) > 0:
                    print(f"⏭️ '{username}': 이미 개체 있음 ({len(game_data['instances'])}마리)")
                    skip_count += 1
                    continue
                
                # Starter A, B 생성
                starter_instances = create_initial_starter_instances()
                
                # 데이터 업데이트
                game_data["instances"] = starter_instances
                
                # 컬렉션에 normal01 추가
                if "collection" not in game_data:
                    game_data["collection"] = {
                        "colors": {"main": [], "sub": [], "pattern": []},
                        "patterns": [],
                        "accessories": [],
                        "skills": {"slot1": [], "slot2": [], "slot3": []}
                    }
                
                if "normal01" not in game_data["collection"]["colors"]["main"]:
                    game_data["collection"]["colors"]["main"].append("normal01")
                if "normal01" not in game_data["collection"]["colors"]["sub"]:
                    game_data["collection"]["colors"]["sub"].append("normal01")
                if "normal01" not in game_data["collection"]["colors"]["pattern"]:
                    game_data["collection"]["colors"]["pattern"].append("normal01")
                if "normal01" not in game_data["collection"]["patterns"]:
                    game_data["collection"]["patterns"].append("normal01")
                
                # DB 업데이트
                client.table("game_data").update({
                    "data": game_data,
                    "updated_at": datetime.now().isoformat()
                }).eq("id", record_id).execute()
                
                print(f"✅ '{username}': Starter A, B 지급 완료")
                success_count += 1
                
            except Exception as e:
                print(f"❌ '{username}' 처리 실패: {e}")
                fail_count += 1
        
        print("\n=== 지급 완료 ===")
        print(f"✅ 성공: {success_count}명")
        print(f"⏭️ 스킵: {skip_count}명")
        print(f"❌ 실패: {fail_count}명")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    print("=== Starter A, B 일괄 지급 시작 ===\n")
    add_starters_to_all_users()
