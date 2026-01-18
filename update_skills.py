"""
스킬 데이터만 Supabase에 업데이트
"""
import json
from supabase_config import get_supabase_client

def update_all_skills():
    """모든 스킬 데이터를 Supabase에 업데이트"""
    print("🔄 모든 스킬 데이터 업데이트 중...")
    
    # skills.json 읽기
    with open("data/skills.json", "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    
    print(f"  총 {len(skills_data)}개의 스킬 발견")
    
    # Supabase 업데이트
    try:
        client = get_supabase_client()
        
        updated_count = 0
        failed_count = 0
        
        for skill_id, skill_info in skills_data.items():
            try:
                # 기존 데이터 확인
                existing = client.table("master_skills").select("id").eq("id", skill_id).execute()
                
                if existing.data:
                    # 업데이트
                    client.table("master_skills").update({
                        "grade": skill_info.get("grade", "Normal"),
                        "slot": skill_info.get("slot", 1),
                        "skill_data": skill_info
                    }).eq("id", skill_id).execute()
                    updated_count += 1
                else:
                    # 새로 삽입
                    client.table("master_skills").insert({
                        "id": skill_id,
                        "grade": skill_info.get("grade", "Normal"),
                        "slot": skill_info.get("slot", 1),
                        "skill_data": skill_info
                    }).execute()
                    updated_count += 1
                
                if updated_count % 50 == 0:
                    print(f"  ... {updated_count}개 처리됨")
                    
            except Exception as e:
                print(f"  ❌ {skill_id} 업데이트 실패: {e}")
                failed_count += 1
        
        print(f"\n  ✅ 업데이트 완료: {updated_count}개 성공, {failed_count}개 실패")
    
    except Exception as e:
        print(f"  ❌ 전체 업데이트 실패: {e}")

if __name__ == "__main__":
    update_all_skills()
