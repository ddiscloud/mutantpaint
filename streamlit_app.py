import streamlit as st
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import uuid
import json
import os
import math
import hashlib
import shutil
import tempfile
# msvcrt 제거 - Supabase 사용으로 파일 잠금 불필요
from dotenv import load_dotenv

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))

# Supabase 임포트
from supabase_db import (
    load_master_colors, load_master_patterns, load_master_skills,
    save_game_data as save_game_data_db, load_game_data as load_game_data_db,
    check_user_exists, create_user,
    get_user_password_hash, load_season_history as load_season_history_db,
    save_season_history as save_season_history_db,
    init_supabase_db,
    # 랜덤박스 & 우편함
    load_box_templates, get_box_template, create_box_template, 
    update_box_template, delete_box_template,
    load_mailbox, send_mail, claim_mail, delete_mail,
    # 시즌 초기화
    reset_all_user_game_data, clear_all_mailbox
)

# 환경 변수 로드
load_dotenv()

# ============================================================================
# Supabase 초기화 (한 번만 실행)
# ============================================================================
if "supabase_initialized" not in st.session_state:
    init_supabase_db()
    st.session_state.supabase_initialized = True

# ============================================================================
# 마스터 데이터 로드 (Supabase에서)
# ============================================================================

# 마스터 데이터 로드 (캐싱을 위해 session_state 사용)
@st.cache_data(ttl=3600)  # 1시간 캐싱 (마스터 데이터는 자주 변경되지 않음)
def load_master_data_cached():
    """Supabase에서 마스터 데이터 로드 (캐싱)"""
    return {
        "colors": load_master_colors(),
        "patterns": load_master_patterns(),
        "skills": load_master_skills()
    }

master_data = load_master_data_cached()
COLOR_MASTER = master_data["colors"]
PATTERN_MASTER = master_data["patterns"]
SKILL_MASTER = master_data["skills"]
ACCESSORY_MASTER = SKILL_MASTER  # 하위 호환성

# ============================================================================
# 보안 및 파일 관리
# ============================================================================

def check_content_safety(text: str) -> Tuple[bool, str]:
    """텍스트 안전성 검사 (기본 필터 사용, OpenAI Moderation은 비활성화)
    
    Returns:
        (is_safe, reason): (안전여부, 사유)
    """
    # Streamlit Cloud 배포를 위해 OpenAI Moderation API 비활성화
    # 기본 필터만 사용하여 레이트 리미팅 문제 방지
    return basic_name_filter(text)

def basic_name_filter(text: str) -> Tuple[bool, str]:
    """기본 이름 필터 (OpenAI API 없을 때 사용)"""
    # 기본적인 금지어 리스트
    forbidden_words = ["시발", "씨발", "개새", "좆", "병신", "ㅅㅂ", "ㅂㅅ"]
    
    text_lower = text.lower()
    for word in forbidden_words:
        if word in text_lower:
            return False, "부적절한 단어가 포함되어 있습니다"
    
    return True, ""

def hash_password(password: str) -> str:
    """비밀번호 SHA-256 해싱"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """비밀번호 검증"""
    return hash_password(password) == hashed

def acquire_file_lock(file_handle, timeout: float = 5.0):
    """파일 잠금 획득 (레거시 함수 - Supabase 사용으로 불필요)"""
    return True  # 항상 성공 반환

def release_file_lock(file_handle):
    """파일 잠금 해제 (레거시 함수 - Supabase 사용으로 불필요)"""
    pass  # 아무 작업 안 함

def create_backup(filepath: str):
    """파일 백업 생성 (레거시 함수 - Supabase 사용으로 불필요)"""
    pass  # 아무 작업 안 함

# ============================================================================
# 성능 최적화 함수
# ============================================================================

# SVG 렌더링 캐시 (메모리 관리)
@st.cache_data(ttl=86400, max_entries=2000)  # 24시간, 최대 2000개 (메모리 효율적인 SVG)
def render_instance_svg_cached(instance_id: str, main_color_id: str, sub_color_id: str, 
                                pattern_color_id: str, pattern_id: str, size: int = 200) -> str:
    """개체를 SVG로 렌더링 (캐싱 최적화)"""
    main_hex = COLOR_MASTER[main_color_id]['hex']
    sub_hex = COLOR_MASTER[sub_color_id]['hex']
    pattern_hex = COLOR_MASTER[pattern_color_id]['hex']
    pattern_type = PATTERN_MASTER[pattern_id]['layout']
    
    svg_content = render_pattern_svg(pattern_type, main_hex, sub_hex, pattern_hex, size)
    svg = f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">{svg_content}</svg>'
    return svg

# ============================================================================
# 마스터 데이터 정의
# ============================================================================

# 등급별 가중치 (외형 유전용)
GRADE_WEIGHTS = {
    "Normal": 100,
    "Rare": 80,
    "Epic": 55,
    "Unique": 35,
    "Legendary": 20,
    "Mystic": 10
}

# 외형 변이 등급 확률
APPEARANCE_MUTATION_GRADE_PROBS = {
    "Normal": 0.70,
    "Rare": 0.20,
    "Epic": 0.07,
    "Unique": 0.02,
    "Legendary": 0.008,
    "Mystic": 0.002
}

# 컬러 마스터 데이터 - JSON 파일에서 로드됨 (data/colors.json)
# 패턴 마스터 데이터 - JSON 파일에서 로드됨 (data/patterns.json)
# 스킬 마스터 데이터 - JSON 파일에서 로드됨 (data/skills.json)
# ※ 데이터 추가/수정은 data/ 폴더의 JSON 파일을 편집하세요 ※

# ============================================================================
# 유틸리티 함수
# ============================================================================

def generate_id() -> str:
    """고유 ID 생성"""
    return str(uuid.uuid4())

def weighted_choice(choices: Dict[str, float]) -> str:
    """가중치 기반 선택"""
    items = list(choices.keys())
    weights = list(choices.values())
    return random.choices(items, weights=weights, k=1)[0]

def get_color_ids_by_grade(grade: str) -> List[str]:
    """특정 등급의 색 ID 목록 반환"""
    return [cid for cid, data in COLOR_MASTER.items() if data["grade"] == grade]

def get_pattern_ids_by_grade(grade: str) -> List[str]:
    """특정 등급의 패턴 ID 목록 반환"""
    return [pid for pid, data in PATTERN_MASTER.items() if data["grade"] == grade]

def get_skill_ids_by_grade_and_slot(grade: str, slot: int) -> List[str]:
    """특정 등급과 슬롯의 스킬 ID 목록 반환"""
    return [sid for sid, data in SKILL_MASTER.items() 
            if data["grade"] == grade and data["slot"] == slot]

# 하위 호환성을 위한 별칭
get_accessory_ids_by_grade_and_slot = get_skill_ids_by_grade_and_slot

# ============================================================================
# 개체 생성 및 관리
# ============================================================================

def update_collection(instance: Dict):
    """개체의 외형 요소를 도감에 등록"""
    if "collection" not in st.session_state:
        st.session_state.collection = {
            "colors": {"main": set(), "sub": set(), "pattern": set()},
            "patterns": set(),
            "accessories": set()
        }
    
    # 색상 등록 (타입별로 구분)
    st.session_state.collection["colors"]["main"].add(instance["appearance"]["main_color"]["id"])
    st.session_state.collection["colors"]["sub"].add(instance["appearance"]["sub_color"]["id"])
    st.session_state.collection["colors"]["pattern"].add(instance["appearance"]["pattern_color"]["id"])
    
    # 패턴 등록
    st.session_state.collection["patterns"].add(instance["appearance"]["pattern"]["id"])
    
    # 스킬 등록 (슬롯별로 구분)
    # 하위 호환성 확인
    if "skills" not in st.session_state.collection:
        st.session_state.collection["skills"] = {"slot1": set(), "slot2": set(), "slot3": set()}
    
    for i in range(1, 4):
        acc_key = f"accessory_{i}"
        slot_key = f"slot{i}"
        if instance.get(acc_key):
            skill_id = instance[acc_key]["id"]
            # 기존 방식 (하위 호환성)
            st.session_state.collection["accessories"].add(skill_id)
            # 새로운 방식 (슬롯별)
            st.session_state.collection["skills"][slot_key].add(skill_id)

def create_instance(
    hp: int,
    atk: int,
    ms: int,
    main_color: Dict,
    sub_color: Dict,
    pattern_color: Dict,
    pattern: Dict,
    accessory_1: Optional[Dict] = None,
    accessory_2: Optional[Dict] = None,
    accessory_3: Optional[Dict] = None,
    name: str = "Unnamed",
    created_by: str = "Init",
    mutation_count: int = 0,
    mutation_fields: List[str] = None
) -> Dict:
    """개체 생성"""
    instance = {
        "id": generate_id(),
        "name": name,
        "is_locked": False,
        "is_favorite": False,
        "created_by": created_by,
        "birth_time": datetime.now().isoformat(),
        "stats": {
            "hp": hp,
            "atk": atk,
            "ms": ms
        },
        "power_score": calculate_power_score({"hp": hp, "atk": atk, "ms": ms}),
        "appearance": {
            "main_color": main_color,
            "sub_color": sub_color,
            "pattern_color": pattern_color,
            "pattern": pattern
        },
        "accessory_1": accessory_1,
        "accessory_2": accessory_2,
        "accessory_3": accessory_3,
        "mutation": {
            "count": mutation_count,
            "fields": mutation_fields or []
        }
    }
    
    # 도감 업데이트
    update_collection(instance)
    
    return instance

def create_initial_instance() -> Dict:
    """초기 개체 생성 (HP 10, ATK 1, MS 1, 모든 normal01)"""
    return create_instance(
        hp=10,
        atk=1,
        ms=1,
        main_color={"grade": "Normal", "id": "normal01"},
        sub_color={"grade": "Normal", "id": "normal01"},
        pattern_color={"grade": "Normal", "id": "normal01"},
        pattern={"grade": "Normal", "id": "normal01"},
        accessory_1=None,
        accessory_2=None,
        accessory_3=None,
        name="Starter",
        created_by="Init"
    )

# ============================================================================
# 믹스 시스템
# ============================================================================

def inherit_stat(parent1_val: int, parent2_val: int) -> int:
    """능력치 유전: 부모 중 하나 선택"""
    return random.choice([parent1_val, parent2_val])

def inherit_appearance_item(parent1_item: Dict, parent2_item: Dict) -> Dict:
    """외형 항목 유전: 등급 가중치 기반"""
    candidates = []
    
    # 부모1의 항목
    grade1 = parent1_item["grade"]
    weight1 = GRADE_WEIGHTS[grade1]
    candidates.append((parent1_item["grade"], parent1_item["id"], weight1))
    
    # 부모2의 항목 (같은 id면 가중치 합산)
    if parent1_item["id"] != parent2_item["id"]:
        grade2 = parent2_item["grade"]
        weight2 = GRADE_WEIGHTS[grade2]
        candidates.append((parent2_item["grade"], parent2_item["id"], weight2))
    else:
        # 같은 항목이면 가중치 합산
        candidates[0] = (parent1_item["grade"], parent1_item["id"], weight1 + GRADE_WEIGHTS[parent2_item["grade"]])
    
    # 가중치 기반 선택
    weights = [c[2] for c in candidates]
    selected = random.choices(candidates, weights=weights, k=1)[0]
    
    # 새 딕셔너리 생성하여 반환
    return {"grade": selected[0], "id": selected[1]}

def mutate_stat(current_val: int, stat_type: str) -> Tuple[int, int]:
    """능력치 돌연변이: 증가량 반환"""
    if stat_type == "hp":
        delta_probs = {10: 0.80, 20: 0.15, 30: 0.05}
    elif stat_type == "atk":
        delta_probs = {1: 0.57, 2: 0.30, 3: 0.08, 4: 0.04, 5: 0.01}
    elif stat_type == "ms":
        delta_probs = {1: 0.80, 2: 0.15, 3: 0.05}
    else:
        return current_val, 0
    
    delta = weighted_choice(delta_probs)
    return current_val + delta, delta

def mutate_appearance_item(item_type: str, parent1: Dict, parent2: Dict, slot: Optional[int] = None) -> Dict:
    """외형 돌연변이: 새로운 값 생성"""
    # 등급 선택
    grade = weighted_choice(APPEARANCE_MUTATION_GRADE_PROBS)
    
    # 부모가 가진 id 목록
    parent_ids = set()
    if item_type in ["main_color", "sub_color", "pattern_color"]:
        parent_ids.add(parent1["appearance"][item_type]["id"])
        parent_ids.add(parent2["appearance"][item_type]["id"])
        candidates = get_color_ids_by_grade(grade)
    elif item_type == "pattern":
        parent_ids.add(parent1["appearance"]["pattern"]["id"])
        parent_ids.add(parent2["appearance"]["pattern"]["id"])
        candidates = get_pattern_ids_by_grade(grade)
    else:  # accessory
        acc_key = f"accessory_{slot}"
        if parent1.get(acc_key):
            parent_ids.add(parent1[acc_key]["id"])
        if parent2.get(acc_key):
            parent_ids.add(parent2[acc_key]["id"])
        candidates = get_accessory_ids_by_grade_and_slot(grade, slot)
    
    # 부모와 다른 값 선택 (가능하면)
    different_candidates = [c for c in candidates if c not in parent_ids]
    if different_candidates:
        chosen_id = random.choice(different_candidates)
    elif candidates:
        chosen_id = random.choice(candidates)
    else:
        # 해당 등급에 후보가 없으면 Normal로
        if item_type in ["main_color", "sub_color", "pattern_color"]:
            chosen_id = "normal01"
        elif item_type == "pattern":
            chosen_id = "normal01"
        else:
            return None  # 악세서리는 null 가능
    
    return {"grade": grade, "id": chosen_id}

def breed(parent1: Dict, parent2: Dict) -> Dict:
    """믹스 수행"""
    # 시간 기반 랜덤 시드 설정
    random.seed(time.time())
    
    # 능력치 유전
    hp = inherit_stat(parent1["stats"]["hp"], parent2["stats"]["hp"])
    atk = inherit_stat(parent1["stats"]["atk"], parent2["stats"]["atk"])
    ms = inherit_stat(parent1["stats"]["ms"], parent2["stats"]["ms"])
    
    # 외형 유전
    main_color = inherit_appearance_item(
        parent1["appearance"]["main_color"],
        parent2["appearance"]["main_color"]
    )
    sub_color = inherit_appearance_item(
        parent1["appearance"]["sub_color"],
        parent2["appearance"]["sub_color"]
    )
    pattern_color = inherit_appearance_item(
        parent1["appearance"]["pattern_color"],
        parent2["appearance"]["pattern_color"]
    )
    pattern = inherit_appearance_item(
        parent1["appearance"]["pattern"],
        parent2["appearance"]["pattern"]
    )
    
    # 악세서리 유전
    accessory_1 = None
    if parent1.get("accessory_1") or parent2.get("accessory_1"):
        p1_acc1 = parent1.get("accessory_1") or {"grade": "Normal", "id": "acc1_normal01"}
        p2_acc1 = parent2.get("accessory_1") or {"grade": "Normal", "id": "acc1_normal01"}
        accessory_1 = inherit_appearance_item(p1_acc1, p2_acc1)
    
    accessory_2 = None
    if parent1.get("accessory_2") or parent2.get("accessory_2"):
        p1_acc2 = parent1.get("accessory_2") or {"grade": "Normal", "id": "acc2_normal01"}
        p2_acc2 = parent2.get("accessory_2") or {"grade": "Normal", "id": "acc2_normal01"}
        accessory_2 = inherit_appearance_item(p1_acc2, p2_acc2)
    
    accessory_3 = None
    if parent1.get("accessory_3") or parent2.get("accessory_3"):
        p1_acc3 = parent1.get("accessory_3") or {"grade": "Normal", "id": "acc3_normal01"}
        p2_acc3 = parent2.get("accessory_3") or {"grade": "Normal", "id": "acc3_normal01"}
        accessory_3 = inherit_appearance_item(p1_acc3, p2_acc3)
    
    # 돌연변이 시스템
    mutation_count = 0
    mutation_fields = []
    mutated_fields = set()
    
    # 유저별 돌연변이 보너스 적용
    mutation_bonus = st.session_state.get("mutation_bonus", 0.0)
    max_chain = st.session_state.get("max_chain_mutations", 3)
    
    # 1차 돌연변이 (기본 50% × (1 + 보너스))
    first_mutation_chance = 0.50 * (1 + mutation_bonus)
    if random.random() < first_mutation_chance:
        mutation_count = 1
        # 카테고리 선택: 능력치 80%, 외형 15%, 스킬 5%
        category_roll = random.random()
        
        if category_roll < 0.80:
            # 능력치 변이 (80%)
            stat_field = random.choice(["hp", "atk", "ms"])
            mutated_fields.add(stat_field)
            mutation_fields.append(stat_field)
            
            if stat_field == "hp":
                hp, delta = mutate_stat(max(parent1["stats"]["hp"], parent2["stats"]["hp"]), "hp")
            elif stat_field == "atk":
                atk, delta = mutate_stat(max(parent1["stats"]["atk"], parent2["stats"]["atk"]), "atk")
            elif stat_field == "ms":
                ms, delta = mutate_stat(max(parent1["stats"]["ms"], parent2["stats"]["ms"]), "ms")
        
        elif category_roll < 0.95:
            # 외형 변이 (15%): 색상/패턴만
            appearance_field = random.choice(["main_color", "sub_color", "pattern_color", "pattern"])
            mutated_fields.add(appearance_field)
            mutation_fields.append(appearance_field)
            
            new_appearance = mutate_appearance_item(appearance_field, parent1, parent2)
            if appearance_field == "main_color":
                main_color = new_appearance
            elif appearance_field == "sub_color":
                sub_color = new_appearance
            elif appearance_field == "pattern_color":
                pattern_color = new_appearance
            elif appearance_field == "pattern":
                pattern = new_appearance
        
        else:
            # 스킬 변이 (5%): 악세서리
            acc_slot = random.choice([1, 2, 3])
            field_name = f"accessory_{acc_slot}"
            mutated_fields.add(field_name)
            mutation_fields.append(field_name)
            
            new_acc = mutate_appearance_item(field_name, parent1, parent2, acc_slot)
            if acc_slot == 1:
                accessory_1 = new_acc
            elif acc_slot == 2:
                accessory_2 = new_acc
            elif acc_slot == 3:
                accessory_3 = new_acc
        
        # 2차 연쇄 돌연변이 (기본 40% × (1 + 보너스))
        second_mutation_chance = 0.40 * (1 + mutation_bonus)
        if random.random() < second_mutation_chance:
            mutation_count = 2
            # 중복 제외하고 선택
            available_stats = [s for s in ["hp", "atk", "ms"] if s not in mutated_fields]
            available_appearance = [a for a in ["main_color", "sub_color", "pattern_color", "pattern"] 
                                    if a not in mutated_fields]
            available_skills = [a for a in ["accessory_1", "accessory_2", "accessory_3"] 
                                if a not in mutated_fields]
            
            category_roll = random.random()
            
            if category_roll < 0.80 and available_stats:
                # 능력치 변이 (80%)
                stat_field = random.choice(available_stats)
                mutated_fields.add(stat_field)
                mutation_fields.append(stat_field)
                
                if stat_field == "hp":
                    hp, delta = mutate_stat(hp, "hp")
                elif stat_field == "atk":
                    atk, delta = mutate_stat(atk, "atk")
                elif stat_field == "ms":
                    ms, delta = mutate_stat(ms, "ms")
            
            elif category_roll < 0.95 and available_appearance:
                # 외형 변이 (15%)
                appearance_field = random.choice(available_appearance)
                mutated_fields.add(appearance_field)
                mutation_fields.append(appearance_field)
                
                new_appearance = mutate_appearance_item(appearance_field, parent1, parent2)
                if appearance_field == "main_color":
                    main_color = new_appearance
                elif appearance_field == "sub_color":
                    sub_color = new_appearance
                elif appearance_field == "pattern_color":
                    pattern_color = new_appearance
                elif appearance_field == "pattern":
                    pattern = new_appearance
            
            elif available_skills:
                # 스킬 변이 (5%)
                skill_field = random.choice(available_skills)
                mutated_fields.add(skill_field)
                mutation_fields.append(skill_field)
                
                slot = int(skill_field.split("_")[1])
                new_acc = mutate_appearance_item(skill_field, parent1, parent2, slot)
                if slot == 1:
                    accessory_1 = new_acc
                elif slot == 2:
                    accessory_2 = new_acc
                elif slot == 3:
                    accessory_3 = new_acc
            
            # 3차 연쇄 돌연변이 (기본 20% × (1 + 보너스))
            third_mutation_chance = 0.20 * (1 + mutation_bonus)
            if random.random() < third_mutation_chance:
                mutation_count = 3
                available_stats = [s for s in ["hp", "atk", "ms"] if s not in mutated_fields]
                available_appearance = [a for a in ["main_color", "sub_color", "pattern_color", "pattern"] 
                                        if a not in mutated_fields]
                available_skills = [a for a in ["accessory_1", "accessory_2", "accessory_3"] 
                                    if a not in mutated_fields]
                
                category_roll = random.random()
                
                if category_roll < 0.80 and available_stats:
                    stat_field = random.choice(available_stats)
                    mutated_fields.add(stat_field)
                    mutation_fields.append(stat_field)
                    
                    if stat_field == "hp":
                        hp, delta = mutate_stat(hp, "hp")
                    elif stat_field == "atk":
                        atk, delta = mutate_stat(atk, "atk")
                    elif stat_field == "ms":
                        ms, delta = mutate_stat(ms, "ms")
                
                elif category_roll < 0.95 and available_appearance:
                    appearance_field = random.choice(available_appearance)
                    mutated_fields.add(appearance_field)
                    mutation_fields.append(appearance_field)
                    
                    new_appearance = mutate_appearance_item(appearance_field, parent1, parent2)
                    if appearance_field == "main_color":
                        main_color = new_appearance
                    elif appearance_field == "sub_color":
                        sub_color = new_appearance
                    elif appearance_field == "pattern_color":
                        pattern_color = new_appearance
                    elif appearance_field == "pattern":
                        pattern = new_appearance
                
                elif available_skills:
                    skill_field = random.choice(available_skills)
                    mutated_fields.add(skill_field)
                    mutation_fields.append(skill_field)
                    
                    slot = int(skill_field.split("_")[1])
                    new_acc = mutate_appearance_item(skill_field, parent1, parent2, slot)
                    if slot == 1:
                        accessory_1 = new_acc
                    elif slot == 2:
                        accessory_2 = new_acc
                    elif slot == 3:
                        accessory_3 = new_acc
                
                # 4차 연쇄 돌연변이 (기본 10% × (1 + 보너스), max_chain >= 4일 때만)
                if max_chain >= 4:
                    fourth_mutation_chance = 0.10 * (1 + mutation_bonus)
                    if random.random() < fourth_mutation_chance:
                        mutation_count = 4
                        available_stats = [s for s in ["hp", "atk", "ms"] if s not in mutated_fields]
                        available_appearance = [a for a in ["main_color", "sub_color", "pattern_color", "pattern"] 
                                                if a not in mutated_fields]
                        available_skills = [a for a in ["accessory_1", "accessory_2", "accessory_3"] 
                                            if a not in mutated_fields]
                        
                        category_roll = random.random()
                        
                        if category_roll < 0.80 and available_stats:
                            stat_field = random.choice(available_stats)
                            mutated_fields.add(stat_field)
                            mutation_fields.append(stat_field)
                            
                            if stat_field == "hp":
                                hp, delta = mutate_stat(hp, "hp")
                            elif stat_field == "atk":
                                atk, delta = mutate_stat(atk, "atk")
                            elif stat_field == "ms":
                                ms, delta = mutate_stat(ms, "ms")
                        
                        elif category_roll < 0.95 and available_appearance:
                            appearance_field = random.choice(available_appearance)
                            mutated_fields.add(appearance_field)
                            mutation_fields.append(appearance_field)
                            
                            new_appearance = mutate_appearance_item(appearance_field, parent1, parent2)
                            if appearance_field == "main_color":
                                main_color = new_appearance
                            elif appearance_field == "sub_color":
                                sub_color = new_appearance
                            elif appearance_field == "pattern_color":
                                pattern_color = new_appearance
                            elif appearance_field == "pattern":
                                pattern = new_appearance
                        
                        elif available_skills:
                            skill_field = random.choice(available_skills)
                            mutated_fields.add(skill_field)
                            mutation_fields.append(skill_field)
                            
                            slot = int(skill_field.split("_")[1])
                            new_acc = mutate_appearance_item(skill_field, parent1, parent2, slot)
                            if slot == 1:
                                accessory_1 = new_acc
                            elif slot == 2:
                                accessory_2 = new_acc
                            elif slot == 3:
                                accessory_3 = new_acc
                        
                        # 5차 연쇄 돌연변이 (기본 5% × (1 + 보너스), max_chain >= 5일 때만)
                        if max_chain >= 5:
                            fifth_mutation_chance = 0.05 * (1 + mutation_bonus)
                            if random.random() < fifth_mutation_chance:
                                mutation_count = 5
                                available_stats = [s for s in ["hp", "atk", "ms"] if s not in mutated_fields]
                                available_appearance = [a for a in ["main_color", "sub_color", "pattern_color", "pattern"] 
                                                        if a not in mutated_fields]
                                available_skills = [a for a in ["accessory_1", "accessory_2", "accessory_3"] 
                                                    if a not in mutated_fields]
                                
                                category_roll = random.random()
                                
                                if category_roll < 0.80 and available_stats:
                                    stat_field = random.choice(available_stats)
                                    mutated_fields.add(stat_field)
                                    mutation_fields.append(stat_field)
                                    
                                    if stat_field == "hp":
                                        hp, delta = mutate_stat(hp, "hp")
                                    elif stat_field == "atk":
                                        atk, delta = mutate_stat(atk, "atk")
                                    elif stat_field == "ms":
                                        ms, delta = mutate_stat(ms, "ms")
                                
                                elif category_roll < 0.95 and available_appearance:
                                    appearance_field = random.choice(available_appearance)
                                    mutated_fields.add(appearance_field)
                                    mutation_fields.append(appearance_field)
                                    
                                    new_appearance = mutate_appearance_item(appearance_field, parent1, parent2)
                                    if appearance_field == "main_color":
                                        main_color = new_appearance
                                    elif appearance_field == "sub_color":
                                        sub_color = new_appearance
                                    elif appearance_field == "pattern_color":
                                        pattern_color = new_appearance
                                    elif appearance_field == "pattern":
                                        pattern = new_appearance
                                
                                elif available_skills:
                                    skill_field = random.choice(available_skills)
                                    mutated_fields.add(skill_field)
                                    mutation_fields.append(skill_field)
                                    
                                    slot = int(skill_field.split("_")[1])
                                    new_acc = mutate_appearance_item(skill_field, parent1, parent2, slot)
                                    if slot == 1:
                                        accessory_1 = new_acc
                                    elif slot == 2:
                                        accessory_2 = new_acc
                                    elif slot == 3:
                                        accessory_3 = new_acc
    
    # 새 개체 생성 (offspring 카운터 증가)
    st.session_state.offspring_counter = st.session_state.get("offspring_counter", 0) + 1
    offspring_name = f"Offspring {st.session_state.offspring_counter}"
    
    return create_instance(
        hp=hp,
        atk=atk,
        ms=ms,
        main_color=main_color,
        sub_color=sub_color,
        pattern_color=pattern_color,
        pattern=pattern,
        accessory_1=accessory_1,
        accessory_2=accessory_2,
        accessory_3=accessory_3,
        name=offspring_name,
        created_by="Breed",
        mutation_count=mutation_count,
        mutation_fields=mutation_fields
    )

# ============================================================================
# 랜덤박스 시스템
# ============================================================================

def open_random_box(template_id: str, created_by: str = "RandomBox") -> Optional[Dict]:
    """랜덤박스 개봉 - 조건에 맞는 개체 생성"""
    template = get_box_template(template_id)
    if not template:
        return None
    
    conditions = template["conditions"]
    
    # 능력치 랜덤 생성
    stat_ranges = conditions.get("stat_ranges", {})
    hp_min = stat_ranges.get("hp", {}).get("min", 10)
    hp_max = stat_ranges.get("hp", {}).get("max", 100)
    # HP는 10단위로 생성 (10, 20, 30, ...)
    hp = random.randint(hp_min // 10, hp_max // 10) * 10
    
    atk = random.randint(
        stat_ranges.get("atk", {}).get("min", 1),
        stat_ranges.get("atk", {}).get("max", 10)
    )
    ms = random.randint(
        stat_ranges.get("ms", {}).get("min", 1),
        stat_ranges.get("ms", {}).get("max", 10)
    )
    
    # 외형 요소 생성 (등급 가중치 기반)
    grades_config = conditions.get("grades", {})
    
    def select_appearance_item(item_type: str, allowed_grades: List[str]) -> Dict:
        """허용된 등급 내에서 가중치 기반 선택"""
        if not allowed_grades:
            # 등급 제한이 없으면 Normal 기본값
            allowed_grades = ["Normal"]
        
        # 허용된 등급의 아이템들 수집
        candidates = []
        if item_type in ["main_color", "sub_color", "pattern_color"]:
            for color_id, color_data in COLOR_MASTER.items():
                if color_data["grade"] in allowed_grades:
                    candidates.append((color_id, color_data["grade"]))
        elif item_type == "pattern":
            for pattern_id, pattern_data in PATTERN_MASTER.items():
                if pattern_data["grade"] in allowed_grades:
                    candidates.append((pattern_id, pattern_data["grade"]))
        
        if not candidates:
            # 후보가 없으면 Normal 첫번째 아이템
            if item_type == "pattern":
                return {"grade": "Normal", "id": "normal01"}
            else:
                return {"grade": "Normal", "id": "normal01"}
        
        # 등급별 가중치 계산
        weighted_candidates = []
        for item_id, grade in candidates:
            weight = GRADE_WEIGHTS.get(grade, 1)
            weighted_candidates.append((item_id, grade, weight))
        
        # 가중치 기반 랜덤 선택
        total_weight = sum(w for _, _, w in weighted_candidates)
        rand_val = random.uniform(0, total_weight)
        cumulative = 0
        
        for item_id, grade, weight in weighted_candidates:
            cumulative += weight
            if rand_val <= cumulative:
                return {"grade": grade, "id": item_id}
        
        # 폴백 (이론적으로 도달 불가)
        return {"grade": weighted_candidates[0][1], "id": weighted_candidates[0][0]}
    
    def select_skill_item(slot: int, allowed_grades: List[str]) -> Optional[Dict]:
        """허용된 등급 내에서 스킬 선택"""
        if not allowed_grades or allowed_grades == [None]:
            return None
        
        # 허용된 등급의 스킬들 수집
        candidates = []
        for skill_id, skill_data in SKILL_MASTER.items():
            if skill_data.get("slot") == slot and skill_data["grade"] in allowed_grades:
                candidates.append((skill_id, skill_data["grade"]))
        
        if not candidates:
            return None
        
        # 등급별 가중치 계산
        weighted_candidates = []
        for skill_id, grade in candidates:
            weight = GRADE_WEIGHTS.get(grade, 1)
            weighted_candidates.append((skill_id, grade, weight))
        
        # 가중치 기반 랜덤 선택
        total_weight = sum(w for _, _, w in weighted_candidates)
        rand_val = random.uniform(0, total_weight)
        cumulative = 0
        
        for skill_id, grade, weight in weighted_candidates:
            cumulative += weight
            if rand_val <= cumulative:
                return {"grade": grade, "id": skill_id}
        
        return {"grade": weighted_candidates[0][1], "id": weighted_candidates[0][0]}
    
    # 외형 생성
    main_color = select_appearance_item("main_color", grades_config.get("main_color", ["Normal"]))
    sub_color = select_appearance_item("sub_color", grades_config.get("sub_color", ["Normal"]))
    pattern_color = select_appearance_item("pattern_color", grades_config.get("pattern_color", ["Normal"]))
    pattern = select_appearance_item("pattern", grades_config.get("pattern", ["Normal"]))
    
    # 스킬 생성
    accessory_1 = select_skill_item(1, grades_config.get("accessory_1"))
    accessory_2 = select_skill_item(2, grades_config.get("accessory_2"))
    accessory_3 = select_skill_item(3, grades_config.get("accessory_3"))
    
    # 개체 생성
    box_counter = st.session_state.get("box_counter", 0) + 1
    st.session_state.box_counter = box_counter
    
    return create_instance(
        hp=hp,
        atk=atk,
        ms=ms,
        main_color=main_color,
        sub_color=sub_color,
        pattern_color=pattern_color,
        pattern=pattern,
        accessory_1=accessory_1,
        accessory_2=accessory_2,
        accessory_3=accessory_3,
        name=f"Box {box_counter}",
        created_by=created_by,
        mutation_count=0,
        mutation_fields=[]
    )

# ============================================================================
# 전투 시스템
# ============================================================================

class Buff:
    """버프/디버프 클래스"""
    def __init__(self, buff_type: str, value: float, duration: int, source: str = "", count: int = 0):
        self.type = buff_type
        self.value = value
        self.duration = duration
        self.source = source
        self.count = count  # 횟수 기반 효과용 (회피 횟수 등)

class BattleInstance:
    """전투용 개체 임시 데이터"""
    def __init__(self, instance: Dict, is_player: bool = True):
        self.original = instance
        self.is_player = is_player
        
        # 기본 스탯
        self.max_hp = instance["stats"]["hp"]
        self.base_atk = instance["stats"]["atk"]
        self.base_ms = instance["stats"]["ms"]
        
        # 현재 스탯
        self.current_hp = self.max_hp
        self.current_atk = self.base_atk
        self.current_ms = self.base_ms
        
        # 버프/디버프
        self.buffs = []
        self.debuffs = []
        
        # 속도 게이지 (ATB 시스템)
        self.speed_gauge = 0
        
        # 쉴드 (오버힐로 변환되는 임시 보호)
        self.shield = 0
        
        # 반격 데미지 추적 (로그 표시용)
        self.last_counter_damage = 0
        
        # 쿨다운 {slot: remaining_turns}
        self.cooldowns = {1: 0, 2: 0, 3: 0}
        
        # Mystic 스킬 사용 여부
        self.mystic_used = set()
        
        # 특수 상태
        self.invincible = 0  # 무적 턴
        self.stunned = 0  # 스턴 턴
        self.revive_once = False  # 1회 부활
        self.auto_revive_hp = 0  # 자동 부활 시 HP
        self.time_loop = 0  # 타임루프 턴
        self.saved_state = None  # 저장된 상태
        self.next_turn_first_strike = False  # 다음 턴 선공 플래그
        self.next_turn_dodge_active = False  # 다음 상대 공격 회피 플래그
        self.next_turn_dodge_chance = 0  # 다음 상대 공격 회피 확률
        
        # 스킬
        self.skills = {}
        for i in range(1, 4):
            acc_key = f"accessory_{i}"
            if instance.get(acc_key):
                skill_id = instance[acc_key]["id"]
                if skill_id in SKILL_MASTER:
                    self.skills[i] = SKILL_MASTER[skill_id]
    
    def get_hp_percent(self) -> float:
        return self.current_hp / self.max_hp if self.max_hp > 0 else 0
    
    def apply_buffs(self):
        """버프 효과 적용하여 현재 스탯 계산"""
        self.current_atk = self.base_atk
        self.current_ms = self.base_ms
        
        # ATK 버프/디버프
        atk_modifier = 1.0
        for buff in self.buffs:
            if buff.type == "atk_boost":
                atk_modifier += buff.value
        for debuff in self.debuffs:
            if debuff.type == "atk_reduce":
                atk_modifier -= debuff.value
        
        self.current_atk = int(self.base_atk * max(0.1, min(1.9, atk_modifier)))
        
        # MS 버프/디버프
        ms_modifier = 0
        for buff in self.buffs:
            if buff.type == "ms_boost":
                ms_modifier += int(buff.value)
        for debuff in self.debuffs:
            if debuff.type == "ms_reduce":
                ms_modifier -= int(debuff.value)
        
        self.current_ms = max(1, self.base_ms + ms_modifier)
    
    def add_buff(self, buff_type: str, value: float, duration: int, source: str = "", count: int = 0):
        """버프 추가"""
        self.buffs.append(Buff(buff_type, value, duration, source, count))
    
    def add_debuff(self, debuff_type: str, value: float, duration: int, source: str = "", count: int = 0):
        """디버프 추가"""
        self.debuffs.append(Buff(debuff_type, value, duration, source, count))
    
    def tick_buffs(self):
        """버프/디버프 지속시간 감소"""
        # duration 감소 먼저
        for b in self.buffs:
            b.duration -= 1
        for d in self.debuffs:
            d.duration -= 1
        
        # 버프 제거 조건:
        # - count 기반 버프(dodge_count): count가 0 이하일 때 제거
        # - 일반 버프: duration이 0 이하일 때 제거
        new_buffs = []
        for b in self.buffs:
            if b.type == "dodge_count":
                # count 기반 버프는 count로만 관리
                if b.count > 0:
                    new_buffs.append(b)
            else:
                # 일반 버프는 duration으로 관리
                if b.duration > 0:
                    new_buffs.append(b)
        
        self.buffs = new_buffs
        self.debuffs = [d for d in self.debuffs if d.duration > 0]
        
        # 쿨다운 감소
        for slot in self.cooldowns:
            if self.cooldowns[slot] > 0:
                self.cooldowns[slot] -= 1
        
        # 특수 상태 감소
        if self.invincible > 0:
            self.invincible -= 1
        if self.stunned > 0:
            self.stunned -= 1
        if self.time_loop > 0:
            self.time_loop -= 1
        
        self.apply_buffs()

class Battle:
    """전투 매니저"""
    def __init__(self, player_instance: Dict, enemy_instance: Dict):
        self.player = BattleInstance(player_instance, is_player=True)
        self.enemy = BattleInstance(enemy_instance, is_player=False)
        self.turn = 0
        self.log = []
        self.max_turns = 50
        self.winner = None
        # 행동 임계값을 전투 시작 시 고정 (base MS 기준)
        self.action_threshold = self.player.base_ms + self.enemy.base_ms
    
    def add_log(self, message: str):
        """전투 로그 추가"""
        self.log.append(f"턴 {self.turn}: {message}")
    
    def check_dodge_simple(self, defender: BattleInstance) -> bool:
        """간단한 회피 체크 (소모 없음)"""
        for buff in defender.buffs:
            if buff.type == "dodge_count" and buff.count > 0:
                return True
        
        dodge_chance = 0
        for buff in defender.buffs:
            if buff.type == "dodge_chance":
                dodge_chance = max(dodge_chance, buff.value)
        
        if dodge_chance > 0 and random.random() < dodge_chance:
            return True
        
        return False
    
    def check_and_consume_dodge(self, defender: BattleInstance, defender_name: str) -> Optional[str]:
        """회피 체크 및 회피 횟수 소모
        
        Returns:
            회피 성공 시 메시지, 실패 시 None
        """
        # 1. 다음 턴 회피 체크 (우선순위 높음)
        if defender.next_turn_dodge_active:
            dodge_chance = defender.next_turn_dodge_chance
            roll = random.random()
            if roll < dodge_chance:
                defender.next_turn_dodge_active = False
                defender.next_turn_dodge_chance = 0
                return f"{defender_name}이(가) 공격을 회피했다! ({int(dodge_chance*100)}% 확률)"
            else:
                # 회피 실패 시 플래그 초기화
                defender.next_turn_dodge_active = False
                defender.next_turn_dodge_chance = 0
        
        # 2. 횟수 기반 회피 체크
        for buff in defender.buffs:
            if buff.type == "dodge_count" and buff.count > 0:
                buff.count -= 1
                remaining = buff.count
                if buff.count <= 0:
                    # 횟수 소진 시 버프 제거
                    defender.buffs.remove(buff)
                    return f"{defender_name}이(가) 공격을 회피했다! (마지막 회피!)"
                return f"{defender_name}이(가) 공격을 회피했다! (남은 회피: {remaining}회)"
        
        # 3. 확률 기반 회피 체크
        dodge_chance = 0
        for buff in defender.buffs:
            if buff.type == "dodge_chance":
                dodge_chance = max(dodge_chance, buff.value)  # 최대 확률 적용
        
        if dodge_chance > 0 and random.random() < dodge_chance:
            return f"{defender_name}이(가) 공격을 회피했다! ({int(dodge_chance*100)}% 확률)"
        
        return None
    
    def apply_damage(self, attacker: BattleInstance, defender: BattleInstance, damage: int) -> int:
        """피해 적용 (immortal 버프 체크, shield 처리, lifesteal 처리, counter 처리)"""
        # 쉴드 먼저 처리
        if defender.shield > 0:
            if defender.shield >= damage:
                defender.shield -= damage
                return damage
            else:
                remaining_damage = damage - defender.shield
                defender.shield = 0
                damage = remaining_damage
        
        has_immortal = any(buff.type == "immortal" for buff in defender.buffs)
        if has_immortal:
            new_hp = defender.current_hp - damage
            defender.current_hp = max(1, new_hp)
        else:
            defender.current_hp = max(0, defender.current_hp - damage)
        
        # lifesteal 버프 처리
        lifesteal_buff = next((buff for buff in attacker.buffs if buff.type == "lifesteal"), None)
        if lifesteal_buff:
            heal = int(damage * lifesteal_buff.value)
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
        
        # counter(반격) 버프 처리 - 데미지를 받은 defender가 반격
        counter_buff = next((buff for buff in defender.buffs if buff.type == "counter"), None)
        if counter_buff and defender.current_hp > 0:
            counter_damage = int(damage * counter_buff.value)
            attacker.current_hp = max(0, attacker.current_hp - counter_damage)
            # 로그에 반격 데미지 기록 (나중에 표시용)
            defender.last_counter_damage = counter_damage
        else:
            defender.last_counter_damage = 0
        
        return damage
    
    def apply_heal(self, target: BattleInstance, heal_amount: int) -> tuple:
        """회복 적용 (오버힐은 쉴드로 전환)
        
        Returns:
            (실제 회복량, 변환된 쉴드량)
        """
        before_hp = target.current_hp
        target.current_hp = min(target.max_hp, target.current_hp + heal_amount)
        actual_heal = target.current_hp - before_hp
        
        # 오버힐 계산 (초과량의 50%만 쉴드로 변환)
        overheal = heal_amount - actual_heal
        if overheal > 0:
            target.shield += int(overheal * 0.5)
        
        return actual_heal, overheal
    
    def tick_and_get_next_actor(self) -> Optional[BattleInstance]:
        """게이지를 1틱만 진행하고 다음 행동자 반환 (ATB 시스템)
        
        행동 임계값 = 두 개체의 base MS 합계 (고정)
        
        Returns:
            행동할 캐릭터, 아무도 행동 못하면 None
        """
        # 행동 임계값: 전투 시작 시 고정된 값 사용
        action_threshold = self.action_threshold
        
        # 먼저 현재 게이지 확인 (증가 전)
        player_ready = self.player.speed_gauge >= action_threshold
        enemy_ready = self.enemy.speed_gauge >= action_threshold
        
        if player_ready and enemy_ready:
            # 둘 다 준비되면 게이지가 더 높은 쪽 (동시면 랜덤)
            if self.player.speed_gauge > self.enemy.speed_gauge:
                self.player.speed_gauge -= action_threshold
                return self.player
            elif self.enemy.speed_gauge > self.player.speed_gauge:
                self.enemy.speed_gauge -= action_threshold
                return self.enemy
            else:
                actor = random.choice([self.player, self.enemy])
                actor.speed_gauge -= action_threshold
                return actor
        elif player_ready:
            self.player.speed_gauge -= action_threshold
            return self.player
        elif enemy_ready:
            self.enemy.speed_gauge -= action_threshold
            return self.enemy
        
        # 아무도 준비 안 됐으면 게이지 증가 (1틱만 진행)
        self.player.speed_gauge += self.player.current_ms / 10
        self.enemy.speed_gauge += self.enemy.current_ms / 10
        
        return None
    
    def select_skill(self, attacker: BattleInstance) -> Optional[int]:
        """AI 스킬 선택"""
        available_skills = []
        priorities = []
        
        for slot, skill in attacker.skills.items():
            # 쿨다운 체크
            if attacker.cooldowns[slot] > 0:
                continue
            
            # Mystic 스킬 체크
            if skill["grade"] == "Mystic" and slot in attacker.mystic_used:
                continue
            
            priority = 0
            hp_percent = attacker.get_hp_percent()
            enemy = self.enemy if attacker.is_player else self.player
            enemy_hp_percent = enemy.get_hp_percent()
            
            # 슬롯별 우선순위
            if slot == 1:  # 회복 스킬
                if hp_percent < 0.3:
                    priority += 100
                elif hp_percent < 0.6:
                    priority += 50
                else:
                    priority += 10
            
            elif slot == 2:  # 공격 스킬
                if enemy_hp_percent < 0.4:
                    priority += 80
                elif enemy_hp_percent > 0.8:
                    priority += 60
                else:
                    priority += 40
            
            elif slot == 3:  # MS/유틸 스킬
                ms_ratio = enemy.current_ms / max(1, attacker.current_ms)
                if ms_ratio > 1.5:
                    priority += 90
                elif ms_ratio > 1.2:
                    priority += 70
                elif ms_ratio > 1.0:
                    priority += 50
                else:
                    priority += 30
            
            # 등급 보너스
            grade_bonus = {
                "Normal": 5, "Rare": 10, "Epic": 15,
                "Unique": 20, "Legendary": 25, "Mystic": 30
            }
            priority += grade_bonus.get(skill["grade"], 0)
            
            # 랜덤 요소
            priority += random.randint(-10, 10)
            
            available_skills.append(slot)
            priorities.append(priority)
        
        if not available_skills:
            return None
        
        # 가장 높은 우선순위 스킬 선택
        max_priority_idx = priorities.index(max(priorities))
        return available_skills[max_priority_idx]
    
    def use_skill(self, attacker: BattleInstance, skill_slot: int) -> str:
        """스킬 사용"""
        if skill_slot not in attacker.skills:
            return "스킬 없음"
        
        skill = attacker.skills[skill_slot]
        defender = self.enemy if attacker.is_player else self.player
        attacker_name = "아군" if attacker.is_player else "적군"
        defender_name = "적군" if attacker.is_player else "아군"
        
        # 쿨다운 설정
        attacker.cooldowns[skill_slot] = skill.get("cooldown", 3)
        
        # Mystic 스킬 마킹
        if skill["grade"] == "Mystic":
            attacker.mystic_used.add(skill_slot)
        
        effect = skill.get("effect", "")
        result = f"{attacker_name}이(가) '{skill['name']}' 사용!"
        
        # ==================== 회복 효과 ====================
        if effect == "heal":
            heal_amount = int(attacker.max_hp * skill.get("value", 0.1))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal_amount)
            result += f" HP {heal_amount} 회복!"
        
        elif effect == "regen":
            duration = skill.get("duration", 3)
            attacker.add_buff("regen", skill.get("value", 0.05), duration)
            result += f" {duration}턴간 매턴 HP {int(skill.get('value', 0.05)*100)}% 회복!"
        
        elif effect == "drain":
            # 회피 체크
            dodged = self.check_and_consume_dodge(defender, defender_name)
            if dodged:
                result += f" -> {dodged}"
                return result
            
            drain_amount = int(defender.current_hp * skill.get("value", 0.2))
            defender.current_hp = max(0, defender.current_hp - drain_amount)
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + drain_amount)
            result += f" 적 HP {drain_amount} 흡수!"
        
        elif effect == "heal_def":
            heal_amount = int(attacker.max_hp * skill.get("value", 0.08))
            actual_heal, overheal = self.apply_heal(attacker, heal_amount)
            duration = skill.get("duration", 1)
            attacker.add_buff("def_boost", skill.get("def_boost", 0.10), duration)
            msg = f" HP {actual_heal} 회복 + {duration}턴 방어 +{int(skill.get('def_boost',0.10)*100)}%!"
            if overheal > 0:
                msg += f" (쉴드 +{overheal})"
            result += msg
        
        elif effect in ["heal_block", "heal_conditional", "heal_sacrifice", "heal_nullify", "heal_ms", "heal_allbuff", "heal_regen", "heal_maxhp", "heal"]:
            # 기본 회복 (오버힐 → 쉴드 변환)
            heal_amount = int(attacker.max_hp * skill.get("value", 0.10))
            actual_heal, overheal = self.apply_heal(attacker, heal_amount)
            msg = f" HP {actual_heal} 회복!"
            if overheal > 0:
                msg += f" (쉴드 +{overheal})"
            result += msg
        
        # ==================== 공격 효과 ====================
        elif effect == "atk_buff":
            duration = skill.get("duration", 3)
            attacker.add_buff("atk_boost", skill.get("value", 0.15), duration)
            result += f" {duration}턴간 ATK +{int(skill.get('value', 0.15)*100)}%!"
        
        elif effect == "def_break":
            duration = skill.get("duration", 2)
            defender.add_debuff("def_reduce", skill.get("value", 0.2), duration)
            result += f" 적 방어 -{int(skill.get('value', 0.2)*100)}% ({duration}턴)!"
        
        elif effect == "fixed_dmg_percent":
            # 회피 체크
            dodged = self.check_and_consume_dodge(defender, defender_name)
            if dodged:
                result += f" -> {dodged}"
                return result
            
            dmg = int(defender.current_hp * skill.get("value", 0.5))
            defender.current_hp = max(0, defender.current_hp - dmg)
            result += f" 적에게 고정 {dmg} 데미지!"
        
        elif effect == "execute":
            # Finish Blow: HP 임계값 이하 시 데미지 부스트
            hp_threshold = skill.get("hp_threshold", 0.30)
            if defender.current_hp <= int(defender.max_hp * hp_threshold):
                attacker.add_buff("execute_dmg", skill.get("dmg_boost", 2.0), 1)
                result += f" 처형 발동! (다음 공격 {int(skill.get('dmg_boost',2.0)*100)}%)"
            else:
                result += f" (적 HP {int(hp_threshold*100)}% 이하 시 발동)"
        
        elif effect == "multi_hit":
            # 회피 체크 (첫 타격만)
            dodged = self.check_and_consume_dodge(defender, defender_name)
            if dodged:
                result += f" -> {dodged}"
                return result
            
            # 다단 히트
            hits = skill.get("hits", 2)
            dmg_per = skill.get("dmg_per", 0.80)
            total_dmg = 0
            for _ in range(hits):
                dmg = int(attacker.current_atk * dmg_per * random.uniform(0.8, 1.2))
                defender.current_hp = max(0, defender.current_hp - dmg)
                total_dmg += dmg
            result += f" {hits}회 연타! 총 {total_dmg} 데미지!"
        
        elif effect == "counter":
            duration = skill.get("duration", 1)
            attacker.add_buff("counter", skill.get("value", 0.50), duration)
            result += f" {duration}턴간 {int(skill.get('value',0.50)*100)}% 반격!"
        
        elif effect in ["crit_chance", "dmg_boost_once", "atk_def_trade", "atk_hp_trade", "dmg_hp_based"]:
            # 공격 버프 계열 (간소화)
            attacker.add_buff("atk_boost", 0.20, 1)
            result += f" 공격력 강화!"
        
        # ==================== MS/유틸 효과 ====================
        elif effect == "first_strike":
            attacker.next_turn_first_strike = True
            result += f" 다음 턴 선공!"
        
        elif effect == "ms_buff":
            duration = skill.get("duration", 3)
            ms_boost = int(attacker.base_ms * skill.get("value", 0.2))
            attacker.add_buff("ms_boost", ms_boost, duration)
            result += f" {duration}턴간 MS +{int(skill.get('value', 0.2)*100)}% ({ms_boost})!"
        
        elif effect == "dodge":
            # 확률 기반 회피
            duration = skill.get("duration", 1)
            attacker.add_buff("dodge_chance", skill.get("value", 0.5), duration)
            result += f" {duration}턴간 {int(skill.get('value', 0.5)*100)}% 회피!"
        
        elif effect == "next_turn_dodge":
            # 다음 상대 공격 1회 회피 (확률 기반)
            attacker.next_turn_dodge_active = True
            attacker.next_turn_dodge_chance = skill.get("value", 0.9)
            result += f" 다음 공격 {int(skill.get('value', 0.9)*100)}% 회피!"
        
        elif effect == "reflect":
            duration = skill.get("duration", 2)
            attacker.add_buff("reflect", skill.get("value", 0.5), duration)
            result += f" {duration}턴간 피해의 {int(skill.get('value', 0.5)*100)}% 반사!"
        
        elif effect == "stun":
            defender.stunned = skill.get("duration", 1)
            result += f" 적 {skill.get('duration', 1)}턴 행동 불가!"
        
        elif effect in ["invincible", "immortal"]:
            duration = skill.get("duration", 3)
            attacker.invincible = duration
            result += f" {duration}턴간 무적!"
        
        elif effect in ["ms_debuff_enemy", "atk_debuff_enemy"]:
            # 적 디버프
            duration = skill.get("duration", 2)
            result += f" 적 약화 ({duration}턴)!"
        
        elif effect in ["dodge_multi", "dodge_ms_buff", "dodge_ms_debuff"]:
            # 횟수 기반 회피 (확정 회피)
            dodge_count = skill.get("duration", 2)  # duration을 회피 횟수로 사용
            attacker.add_buff("dodge_count", 1.0, 999, count=dodge_count)  # count로 횟수 관리
            result += f" {dodge_count}회 확정 회피!"
            
            # 추가 효과
            if effect == "dodge_ms_buff":
                ms_duration = skill.get("duration", 2)
                ms_boost = int(attacker.base_ms * skill.get("ms_boost", 0.6))
                attacker.add_buff("ms_boost", ms_boost, ms_duration)
                result += f" + MS +{int(skill.get('ms_boost', 0.6)*100)}%!"
            elif effect == "dodge_ms_debuff":
                # 적 MS 감소
                duration = skill.get("duration", 2)
                defender.add_debuff("ms_reduce", skill.get("value", 0.3), duration)
        
        # ==================== 추가 회복 효과 (Legendary/Mystic) ====================
        elif effect == "heal_full_noheal":
            heal = attacker.max_hp - attacker.current_hp
            attacker.current_hp = attacker.max_hp
            duration = skill.get("duration", 3)
            attacker.add_debuff("no_regen", 1.0, duration)
            result += f" HP 완전 회복! (단, {duration}턴간 자연 회복 불가)"
        
        elif effect == "heal_full_grow":
            heal = attacker.max_hp - attacker.current_hp
            attacker.current_hp = attacker.max_hp
            duration = skill.get("duration", 5)
            max_hp_grow = skill.get("max_hp_grow", 0.05)
            attacker.add_buff("max_hp_grow", max_hp_grow, duration)
            result += f" HP 완전 회복! + {duration}턴간 매턴 최대HP {int(max_hp_grow*100)}% 증가"
        
        elif effect == "auto_revive":
            revive_hp = skill.get("revive_hp", 1.0)
            attacker.add_buff("auto_revive", revive_hp, 999)
            result += f" 부활 버프 획득! (패배 시 HP {int(revive_hp*100)}%로 부활)"
        
        elif effect == "heal_block":
            heal = int(attacker.max_hp * skill.get("value", 0.1))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            block_chance = skill.get("block_chance", 0.5)
            if random.random() < block_chance:
                attacker.add_buff("dodge_count", 0, 99, count=1)
                result += f" HP {heal} 회복 + 1회 회피 획득!"
            else:
                result += f" HP {heal} 회복!"
        
        elif effect == "heal_conditional":
            hp_threshold = skill.get("hp_threshold", 0.5)
            if attacker.get_hp_percent() <= hp_threshold:
                heal = int(attacker.max_hp * skill.get("value", 0.3))
                attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
                result += f" 조건 충족! HP {heal} 회복!"
            else:
                result += f" (HP {int(hp_threshold*100)}% 이하 시 발동)"
        
        elif effect == "heal_ms":
            heal = int(attacker.max_hp * skill.get("value", 0.2))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            duration = skill.get("duration", 2)
            ms_boost = int(attacker.base_ms * skill.get("ms_boost", 0.1))
            attacker.add_buff("ms_boost", ms_boost, duration)
            result += f" HP {heal} 회복 + MS +{int(skill.get('ms_boost',0.1)*100)}%!"
        
        elif effect == "heal_sacrifice":
            atk_cost = int(attacker.base_atk * skill.get("atk_cost", 0.1))
            attacker.current_atk = max(1, attacker.current_atk - atk_cost)
            heal = int(attacker.max_hp * skill.get("value", 0.35))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            result += f" ATK {atk_cost} 희생, HP {heal} 회복!"
        
        elif effect == "heal_maxhp":
            max_hp_boost = skill.get("max_hp_boost", 0.1)
            hp_increase = int(attacker.max_hp * max_hp_boost)
            attacker.max_hp += hp_increase
            heal = int(attacker.max_hp * skill.get("value", 0.1))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            result += f" 최대HP +{hp_increase}, HP {heal} 회복!"
        
        elif effect == "heal_cleanse":
            heal = int(attacker.max_hp * skill.get("value", 0.7))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            attacker.debuffs.clear()
            result += f" HP {heal} 회복 + 모든 디버프 제거!"
        
        elif effect == "heal_allbuff":
            heal_amount = int(attacker.max_hp * skill.get("value", 0.4))
            actual_heal, overheal = self.apply_heal(attacker, heal_amount)
            duration = skill.get("duration", 2)
            stat_boost = skill.get("stat_boost", 0.2)
            attacker.add_buff("atk_boost", stat_boost, duration)
            attacker.add_buff("ms_boost", int(attacker.base_ms * stat_boost), duration)
            msg = f" HP {actual_heal} 회복 + 전체 스탯 {int(stat_boost*100)}% 증가!"
            if overheal > 0:
                msg += f" (쉴드 +{overheal})"
            result += msg
        
        elif effect == "heal_regen":
            heal_amount = int(attacker.max_hp * skill.get("value", 0.35))
            actual_heal, overheal = self.apply_heal(attacker, heal_amount)
            duration = skill.get("duration", 3)
            attacker.add_buff("regen", skill.get("regen", 0.12), duration)
            msg = f" HP {actual_heal} 회복 + {duration}턴간 지속 회복!"
            if overheal > 0:
                msg += f" (쉴드 +{overheal})"
            result += msg
        
        elif effect == "heal_revive":
            heal_amount = int(attacker.max_hp * skill.get("value", 0.3))
            actual_heal, overheal = self.apply_heal(attacker, heal_amount)
            revive_hp = skill.get("revive_hp", 0.5)
            attacker.add_buff("revive_once", revive_hp, 999)
            msg = f" HP {actual_heal} 회복 + 1회 부활 버프!"
            if overheal > 0:
                msg += f" (쉴드 +{overheal})"
            result += msg
        
        # ==================== 추가 공격 효과 ====================
        elif effect == "damage":
            if not self.check_dodge_simple(defender):
                dmg = int(attacker.current_atk * skill.get("value", 1.5))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "true_damage":
            dmg = int(attacker.current_atk * skill.get("value", 2.0))
            self.apply_damage(attacker, defender, dmg)
            result += f" 관통 {dmg} 데미지! (회피 무시)"
        
        elif effect == "dot_dmg":
            if not self.check_dodge_simple(defender):
                initial = int(attacker.current_atk * skill.get("initial", 1.0))
                self.apply_damage(attacker, defender, initial)
                duration = skill.get("duration", 3)
                dot_value = skill.get("dot_dmg", 0.2)
                defender.add_debuff("dot_dmg", dot_value, duration)
                result += f" {initial} 데미지 + {duration}턴간 지속 피해!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "dmg_hp_based":
            if not self.check_dodge_simple(defender):
                missing_hp = 1.0 - defender.get_hp_percent()
                max_bonus = skill.get("max_bonus", 0.5)
                bonus = missing_hp * max_bonus
                dmg = int(attacker.current_atk * (1.0 + bonus))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지! (적 잃은 HP 비례)"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "atk_hp_trade":
            hp_cost = int(attacker.max_hp * skill.get("hp_cost", 0.1))
            attacker.current_hp = max(1, attacker.current_hp - hp_cost)
            duration = skill.get("duration", 4)
            attacker.add_buff("atk_boost", skill.get("atk_boost", 0.3), duration)
            result += f" HP {hp_cost} 소모, {duration}턴간 ATK +{int(skill.get('atk_boost',0.3)*100)}%!"
        
        elif effect == "dmg_boost_once":
            ms_cost = skill.get("ms_cost", 1)
            attacker.current_ms = max(1, attacker.current_ms - ms_cost)
            attacker.add_buff("dmg_boost_once", skill.get("value", 0.8), 1)
            result += f" MS {ms_cost} 소모, 1턴간 데미지 +{int(skill.get('value',0.8)*100)}%!"
        
        elif effect == "lifesteal":
            duration = skill.get("duration", 3)
            attacker.add_buff("lifesteal", skill.get("value", 0.25), duration)
            result += f" {duration}턴간 흡혈 {int(skill.get('value',0.25)*100)}%!"
        
        elif effect == "atk_grow":
            if not self.check_dodge_simple(defender):
                dmg = attacker.current_atk
                self.apply_damage(attacker, defender, dmg)
                attacker.base_atk += dmg
                attacker.current_atk += dmg
                result += f" {dmg} 데미지 + ATK 영구 +{dmg}!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "ms_multi_hit":
            if not self.check_dodge_simple(defender):
                hits = max(1, int(attacker.current_ms / 100))
                dmg_per = skill.get("dmg_per", 0.18)
                total_dmg = 0
                for _ in range(hits):
                    dmg = int(attacker.current_atk * dmg_per)
                    self.apply_damage(attacker, defender, dmg)
                    total_dmg += dmg
                result += f" MS 기반 {hits}회 연타! 총 {total_dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "ms_multi_hit_double":
            if not self.check_dodge_simple(defender):
                hits = max(1, int(attacker.current_ms / 50))
                dmg_per = skill.get("dmg_per", 0.15)
                total_dmg = 0
                for _ in range(hits):
                    dmg = int(attacker.current_atk * dmg_per)
                    self.apply_damage(attacker, defender, dmg)
                    total_dmg += dmg
                result += f" MS×2 기반 {hits}회 연타! 총 {total_dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "triple_crit":
            if not self.check_dodge_simple(defender):
                crit_chance = skill.get("crit_chance", 0.5)
                crit_dmg = skill.get("crit_dmg", 2.0)
                total_dmg = 0
                for i in range(3):
                    base_dmg = attacker.current_atk
                    if random.random() < crit_chance:
                        dmg = int(base_dmg * crit_dmg)
                    else:
                        dmg = base_dmg
                    self.apply_damage(attacker, defender, dmg)
                    total_dmg += dmg
                result += f" 3회 크리티컬 판정! 총 {total_dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "guaranteed_crit":
            duration = skill.get("duration", 2)
            dmg_boost = skill.get("dmg_boost", 0.5)
            attacker.add_buff("guaranteed_crit", dmg_boost, duration)
            result += f" {duration}턴간 확정 크리티컬 +{int(dmg_boost*100)}%!"
        
        elif effect == "maxhp_perma_atk":
            dmg_percent = skill.get("dmg_percent", 0.4)
            dmg = int(defender.max_hp * dmg_percent)
            self.apply_damage(attacker, defender, dmg)
            atk_grow = skill.get("atk_grow", 0.2)
            atk_increase = int(attacker.base_atk * atk_grow)
            attacker.base_atk += atk_increase
            attacker.current_atk += atk_increase
            result += f" 최대HP {int(dmg_percent*100)}% 피해 ({dmg}) + ATK 영구 +{int(atk_grow*100)}%!"
        
        elif effect == "fixed_dmg_maxhp":
            percent = skill.get("value", 0.3)
            dmg = int(defender.max_hp * percent)
            self.apply_damage(attacker, defender, dmg)
            result += f" 최대HP {int(percent*100)}% 고정 피해 ({dmg})!"
        
        elif effect == "ultra_fixed":
            dmg = int(max(defender.current_hp, defender.max_hp) * 0.8)
            self.apply_damage(attacker, defender, dmg)
            result += f" 궁극 고정 피해 {dmg}!"
        
        elif effect == "pierce_all":
            dmg = attacker.current_atk
            self.apply_damage(attacker, defender, dmg)
            result += f" 관통 {dmg} 데미지! (모든 방어 무시)"
        
        elif effect == "fixed_heal_block":
            dmg_percent = skill.get("dmg_percent", 0.7)
            dmg = int(defender.current_hp * dmg_percent)
            self.apply_damage(attacker, defender, dmg)
            heal_block_duration = skill.get("heal_block", 5)
            defender.add_debuff("heal_block", 1.0, heal_block_duration)
            result += f" {dmg} 피해 + {heal_block_duration}턴 힐 차단!"
        
        elif effect == "damage_buff":
            if not self.check_dodge_simple(defender):
                dmg = int(attacker.current_atk * skill.get("dmg_value", 0.5))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
            
            buff_type = skill.get("buff_type", "atk_boost")
            buff_value = skill.get("buff_value", 0.3)
            duration = skill.get("duration", 3)
            attacker.add_buff(buff_type, buff_value, duration)
            result += f" + {duration}턴 ATK +{int(buff_value*100)}%"
        
        elif effect == "damage_debuff":
            if not self.check_dodge_simple(defender):
                dmg = int(attacker.current_atk * skill.get("dmg_value", 1.3))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
            
            debuff_type = skill.get("debuff_type", "atk_reduce")
            debuff_value = skill.get("debuff_value", 0.2)
            duration = skill.get("duration", 2)
            defender.add_debuff(debuff_type, debuff_value, duration)
            result += f" + 적 ATK -{int(debuff_value*100)}% ({duration}턴)"
        
        elif effect == "damage_ms_reduce":
            if not self.check_dodge_simple(defender):
                dmg = int(attacker.current_atk * skill.get("dmg_value", 0.8))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
            
            duration = skill.get("duration", 3)
            ms_reduce = skill.get("ms_reduce", 0.3)
            defender.add_debuff("ms_reduce", ms_reduce, duration)
            result += f" + 적 MS -{int(ms_reduce*100)}% ({duration}턴)"
        
        elif effect == "dmg_heal_block":
            if not self.check_dodge_simple(defender):
                dmg_boost = skill.get("dmg_boost", 0.8)
                dmg = int(attacker.current_atk * (1.0 + dmg_boost))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
            
            heal_block_duration = skill.get("heal_block", 2)
            defender.add_debuff("heal_block", 1.0, heal_block_duration)
            result += f" + 적 {heal_block_duration}턴 힐 차단!"
        
        elif effect == "dmg_heal_reduce":
            if not self.check_dodge_simple(defender):
                dmg_boost = skill.get("dmg_boost", 1.0)
                dmg = int(attacker.current_atk * (1.0 + dmg_boost))
                self.apply_damage(attacker, defender, dmg)
                result += f" {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
            
            heal_reduce = skill.get("heal_reduce", 0.5)
            attacker.add_debuff("heal_reduce", heal_reduce, 999)
            result += f" (자신의 회복 -{int(heal_reduce*100)}%)"
        
        elif effect == "dmg_ignore_def":
            dmg_boost = skill.get("dmg_boost", 0.5)
            dmg = int(attacker.current_atk * (1.0 + dmg_boost))
            self.apply_damage(attacker, defender, dmg)
            result += f" 방어 무시 {dmg} 데미지!"
        
        elif effect == "instant_atk":
            if not self.check_dodge_simple(defender):
                dmg = int(attacker.current_atk * skill.get("dmg_percent", 0.8))
                self.apply_damage(attacker, defender, dmg)
                result += f" 즉발 {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        # ==================== 추가 유틸 효과 ====================
        elif effect == "extra_action":
            attacker.speed_gauge += attacker.current_ms + defender.current_ms
            result += f" 추가 행동 획득!"
        
        elif effect == "ms_atk_buff":
            duration = skill.get("duration", 4)
            ms_boost = int(attacker.base_ms * skill.get("ms_boost", 1.2))
            attacker.add_buff("ms_boost", ms_boost, duration)
            attacker.add_buff("atk_boost", skill.get("atk_boost", 0.2), duration)
            result += f" {duration}턴간 MS +{int(skill.get('ms_boost',1.2)*100)}%, ATK +{int(skill.get('atk_boost',0.2)*100)}%!"
        
        elif effect == "double_speed":
            duration = skill.get("duration", 3)
            attacker.add_buff("double_speed", 1.0, duration)
            result += f" {duration}턴간 2배속 행동!"
        
        elif effect == "invincible_atk":
            duration = skill.get("duration", 2)
            attacker.add_buff("invincible", 1.0, duration)
            result += f" {duration}턴간 무적 + 공격 가능!"
        
        elif effect == "hp_swap":
            temp_hp = attacker.current_hp
            attacker.current_hp = defender.current_hp
            defender.current_hp = temp_hp
            result += f" HP 교환! (아군 {attacker.current_hp}, 적군 {defender.current_hp})"
        
        elif effect == "stat_swap":
            temp_hp, temp_atk, temp_ms = attacker.current_hp, attacker.current_atk, attacker.current_ms
            attacker.current_hp, attacker.current_atk, attacker.current_ms = defender.current_hp, defender.current_atk, defender.current_ms
            defender.current_hp, defender.current_atk, defender.current_ms = temp_hp, temp_atk, temp_ms
            result += f" 모든 스탯 교환!"
        
        elif effect == "rewind":
            heal = int(attacker.max_hp * 0.5)
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            for slot in attacker.cooldowns:
                attacker.cooldowns[slot] = max(0, attacker.cooldowns[slot] - 1)
            result += f" 시간 역행! HP {heal} 회복 + 쿨다운 1턴 감소!"
        
        elif effect == "drain_maxhp":
            drain = int(defender.max_hp * skill.get("value", 0.15))
            defender.max_hp = max(1, defender.max_hp - drain)
            defender.current_hp = min(defender.current_hp, defender.max_hp)
            attacker.max_hp += drain
            attacker.current_hp += drain
            result += f" 최대HP {drain} 흡수!"
        
        elif effect == "atk_vuln":
            duration = skill.get("duration", 5)
            attacker.add_buff("atk_boost", skill.get("atk_boost", 0.8), duration)
            attacker.add_debuff("vulnerability", skill.get("vuln", 0.3), duration)
            result += f" {duration}턴간 ATK +{int(skill.get('atk_boost',0.8)*100)}%, 하지만 피해 +{int(skill.get('vuln',0.3)*100)}%!"
        
        elif effect == "atk_recoil":
            duration = skill.get("duration", 5)
            recoil_hp = skill.get("recoil_hp", 0.2)
            attacker.add_buff("atk_boost", skill.get("atk_boost", 0.6), duration)
            attacker.add_debuff("recoil_hp", recoil_hp, duration)
            result += f" {duration}턴간 ATK +{int(skill.get('atk_boost',0.6)*100)}%, 종료 시 HP {int(recoil_hp*100)}% 손실!"
        
        elif effect == "atk_stack":
            duration = skill.get("duration", 4)
            initial = skill.get("initial", 0.4)
            stack = skill.get("stack_per_turn", 0.05)
            attacker.add_buff("atk_boost", initial, duration)
            attacker.add_buff("atk_stack", stack, duration)
            result += f" {duration}턴간 ATK +{int(initial*100)}% + 매턴 +{int(stack*100)}% 누적!"
        
        elif effect == "dodge_heal":
            count = skill.get("dodge_count", 3)
            attacker.add_buff("dodge_count", 0, 99, count=count)
            heal = int(attacker.max_hp * skill.get("heal_value", 0.15))
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            result += f" {count}회 회피 + HP {heal} 회복!"
        
        elif effect == "random_effect":
            duration = skill.get("duration", 5)
            attacker.add_buff("random_effect", 1.0, duration)
            result += f" {duration}턴간 랜덤 효과 발동!"
        
        elif effect == "death_loop":
            duration = skill.get("duration", 5)
            attacker.add_buff("death_loop", 1.0, duration)
            result += f" {duration}턴간 사망 시 턴 되돌리기!"
        
        elif effect == "delayed_burst":
            duration = skill.get("duration", 5)
            attacker.add_buff("delayed_burst", 1.0, duration)
            result += f" {duration}턴간 데미지 누적 후 폭발!"
        
        elif effect == "crit_chance":
            if not self.check_dodge_simple(defender):
                crit_chance = skill.get("value", 0.35)
                crit_dmg = skill.get("crit_dmg", 1.35)
                if random.random() < crit_chance:
                    dmg = int(attacker.current_atk * crit_dmg)
                else:
                    dmg = attacker.current_atk
                self.apply_damage(attacker, defender, dmg)
                result += f" {int(crit_chance*100)}% 확률 크리티컬! {dmg} 데미지!"
            else:
                dodged = self.check_and_consume_dodge(defender, defender_name)
                result += f" -> {dodged}"
        
        elif effect == "dodge_multi":
            count = skill.get("value", 1)
            attacker.add_buff("dodge_count", 0, 99, count=count)
            result += f" {count}회 확정 회피!"
        
        elif effect == "atk_debuff_enemy":
            duration = skill.get("duration", 2)
            debuff_value = skill.get("value", 0.8)
            defender.add_debuff("atk_reduce", debuff_value, duration)
            result += f" 적 ATK {int(debuff_value*100)}% 감소 ({duration}턴)!"
        
        elif effect == "ms_debuff_enemy":
            duration = skill.get("duration", 3)
            ms_reduce = skill.get("value", 0.3)
            defender.add_debuff("ms_reduce", ms_reduce, duration)
            result += f" 적 MS {int(ms_reduce*100)}% 감소 ({duration}턴)!"
        
        elif effect == "immortal":
            duration = skill.get("duration", 7)
            attacker.add_buff("immortal", 1.0, duration)
            result += f" {duration}턴간 HP 0 이하로 떨어지지 않음 (최소 1 유지)!"
        
        elif effect == "ms_double_hit":
            duration = skill.get("duration", 5)
            attacker.add_buff("ms_boost", int(attacker.base_ms * skill.get("ms_boost", 5.0)), duration)
            attacker.add_buff("double_hit", 1.0, duration)
            result += f" {duration}턴간 MS +{int(skill.get('ms_boost',5.0)*100)}% + 2회 공격!"
        
        else:
            # 미구현 스킬
            result += f" 효과 발동!"
        
        # 버프/디버프로 인한 스탯 변경사항 즉시 반영
        attacker.apply_buffs()
        defender.apply_buffs()
        
        return result
    
    def basic_attack(self, attacker: BattleInstance) -> str:
        """기본 공격"""
        defender = self.enemy if attacker.is_player else self.player
        attacker_name = "아군" if attacker.is_player else "적군"
        defender_name = "적군" if attacker.is_player else "아군"
        
        # 회피 체크
        dodged = self.check_and_consume_dodge(defender, defender_name)
        if dodged:
            return dodged
        
        # 데미지 계산
        base_dmg = attacker.current_atk * random.uniform(0.8, 1.2)
        
        # 방어 감소 적용
        def_modifier = 1.0
        for debuff in defender.debuffs:
            if debuff.type == "def_reduce":
                def_modifier += debuff.value
        
        final_dmg = int(base_dmg * def_modifier)
        final_dmg = max(1, final_dmg)
        
        # 무적 체크
        if defender.invincible > 0:
            return f"{attacker_name}의 공격! 하지만 {defender_name}은(는) 무적 상태!"
        
        # 피해 적용 (쉴드 처리 포함)
        actual_dmg = self.apply_damage(attacker, defender, final_dmg)
        
        # 반사 데미지
        reflect_dmg = 0
        for buff in defender.buffs:
            if buff.type == "reflect":
                reflect_dmg += int(actual_dmg * buff.value)
        
        # 쉴드로 막았는지 체크
        shield_blocked = defender.shield > 0 or (final_dmg > actual_dmg)
        
        if shield_blocked:
            result = f"{attacker_name}의 공격! {defender_name}에게 {actual_dmg} 데미지! 🛡️"
        else:
            result = f"{attacker_name}의 공격! {defender_name}에게 {actual_dmg} 데미지!"
        
        # 반격 데미지 표시
        if defender.last_counter_damage > 0:
            result += f" ⚔️ 반격 {defender.last_counter_damage}!"
        
        if reflect_dmg > 0:
            attacker.current_hp = max(0, attacker.current_hp - reflect_dmg)
            result += f" 반사 {reflect_dmg} 데미지!"
        
        return result
    
    def execute_turn(self):
        """턴 실행 (1명의 행동) - 행동자가 있을 때만 호출"""
        # first_strike 플래그 처리 (게이지 우선 설정) - 상대보다 높게
        if self.player.next_turn_first_strike:
            # 상대 게이지보다 높게 설정 (최소 100)
            self.player.speed_gauge = max(100, self.enemy.speed_gauge + 1)
            self.player.next_turn_first_strike = False
        if self.enemy.next_turn_first_strike:
            # 상대 게이지보다 높게 설정 (최소 100)
            self.enemy.speed_gauge = max(100, self.player.speed_gauge + 1)
            self.enemy.next_turn_first_strike = False
        
        # 버프/디버프 적용
        self.player.apply_buffs()
        self.enemy.apply_buffs()
        
        # 다음 행동자 결정 (게이지 시스템)
        actor = self.tick_and_get_next_actor()
        
        if not actor:
            # 아무도 행동하지 않음 (게이지만 증가)
            return False
        
        # 실제 행동 발생 - 턴 증가
        self.turn += 1
        
        name = "아군" if actor.is_player else "적군"
        self.add_log(f"=== {name}의 턴 ===")
        
        # 턴 시작 시 버프/디버프 지속시간 감소 (이전 턴에 받은 효과 소진)
        actor.tick_buffs()
        
        # 턴 시작 효과 (지속 회복 등) - 행동자만
        for buff in actor.buffs:
            if buff.type == "regen":
                heal = int(actor.max_hp * buff.value)
                actor.current_hp = min(actor.max_hp, actor.current_hp + heal)
                self.add_log(f"{name} HP {heal} 회복 (지속 회복)")
        
        # 스턴 체크
        if actor.stunned > 0:
            self.add_log(f"{name}은(는) 행동 불가!")
            return
        
        # 스킬 선택 및 사용
        skill_slot = self.select_skill(actor)
        if skill_slot:
            result = self.use_skill(actor, skill_slot)
            self.add_log(result)
        
        # 기본 공격
        result = self.basic_attack(actor)
        self.add_log(result)
        
        return True  # 행동 발생함
    
    def check_victory(self) -> bool:
        """승패 판정"""
        if self.player.current_hp <= 0 and self.enemy.current_hp <= 0:
            self.winner = "draw"
            self.add_log("무승부!")
            return True
        elif self.player.current_hp <= 0:
            self.winner = "enemy"
            self.add_log("적군 승리!")
            return True
        elif self.enemy.current_hp <= 0:
            self.winner = "player"
            self.add_log("아군 승리!")
            return True
        elif self.turn >= self.max_turns:
            # 타임아웃 시 무조건 패배
            self.winner = "enemy"
            self.add_log("시간 초과! 전투 실패!")
            return True
        return False
    
    def run_battle(self):
        """전투 실행"""
        self.add_log("=== 전투 시작! ===")
        self.add_log(f"아군: {self.player.original['name']} (HP: {self.player.max_hp}, ATK: {self.player.base_atk}, MS: {self.player.base_ms})")
        self.add_log(f"적군: {self.enemy.original['name']} (HP: {self.enemy.max_hp}, ATK: {self.enemy.base_atk}, MS: {self.enemy.base_ms})")
        
        while not self.check_victory():
            self.execute_turn()
        
        return self.winner, self.log

# ============================================================================
# 랜덤 박스 시스템
# ============================================================================

def can_use_random_box() -> Tuple[bool, str]:
    """랜덤 박스 사용 가능 여부 확인
    Returns:
        (사용 가능 여부, 메시지)
    """
    last_use = st.session_state.get("last_random_box_time")
    if not last_use:
        return True, "랜덤 박스를 사용할 수 있습니다."
    
    last_use_dt = datetime.fromisoformat(last_use)
    now = datetime.now()
    
    # 하루(24시간) 경과 확인
    time_diff = now - last_use_dt
    if time_diff.total_seconds() >= 86400:  # 24시간 = 86400초
        return True, "랜덤 박스를 사용할 수 있습니다."
    
    # 남은 시간 계산
    remaining_seconds = 86400 - time_diff.total_seconds()
    remaining_hours = int(remaining_seconds // 3600)
    remaining_minutes = int((remaining_seconds % 3600) // 60)
    
    return False, f"다음 랜덤 박스까지 {remaining_hours}시간 {remaining_minutes}분 남았습니다."

def create_random_box_instance() -> Dict:
    """랜덤 박스에서 개체 생성
    - 메인 컬러, 서브 컬러, 패턴 컬러, 패턴 중 1가지만 변경
    - 25% 확률로 각 타입 선택
    - 선택된 타입에서 등급별 가중치로 값 선택
    - 하루 1회 제한이므로 일반 돌연변이보다 높은 희귀 확률
    """
    # 시간 기반 랜덤 시드
    random.seed(time.time())
    
    # 기본 베이스 (초기 개체와 동일)
    base_color = {"grade": "Normal", "id": "normal01"}
    base_pattern = {"grade": "Normal", "id": "normal01"}
    
    # 변경할 타입 선택 (25% 균등 확률)
    change_type = random.choice(["main_color", "sub_color", "pattern_color", "pattern"])
    
    # 랜덤 박스 전용 확률 (하루 1회 제한이므로 더 좋은 확률)
    random_box_grade_probs = {
        "Normal": 0.40,      # 70% → 40%
        "Rare": 0.35,        # 20% → 35%
        "Epic": 0.15,        # 7% → 15%
        "Unique": 0.06,      # 2% → 6%
        "Legendary": 0.03,   # 0.8% → 3%
        "Mystic": 0.01       # 0.2% → 1%
    }
    
    # 등급 선택 (랜덤 박스 전용 가중치)
    grade = weighted_choice(random_box_grade_probs)
    
    # 선택된 타입에서 아이템 선택
    if change_type in ["main_color", "sub_color", "pattern_color"]:
        candidates = get_color_ids_by_grade(grade)
        chosen_id = random.choice(candidates) if candidates else "normal01"
        chosen_item = {"grade": grade, "id": chosen_id}
    else:  # pattern
        candidates = get_pattern_ids_by_grade(grade)
        chosen_id = random.choice(candidates) if candidates else "normal01"
        chosen_item = {"grade": grade, "id": chosen_id}
    
    # 각 타입에 따라 설정
    if change_type == "main_color":
        main_color = chosen_item
        sub_color = base_color
        pattern_color = base_color
        pattern = base_pattern
    elif change_type == "sub_color":
        main_color = base_color
        sub_color = chosen_item
        pattern_color = base_color
        pattern = base_pattern
    elif change_type == "pattern_color":
        main_color = base_color
        sub_color = base_color
        pattern_color = chosen_item
        pattern = base_pattern
    else:  # pattern
        main_color = base_color
        sub_color = base_color
        pattern_color = base_color
        pattern = chosen_item
    
    # 개체 생성
    instance = create_instance(
        hp=10,
        atk=1,
        ms=1,
        main_color=main_color,
        sub_color=sub_color,
        pattern_color=pattern_color,
        pattern=pattern,
        accessory_1=None,
        accessory_2=None,
        accessory_3=None,
        name="Random Box",
        created_by="RandomBox",
        mutation_count=0,
        mutation_fields=[]
    )
    
    return instance

# ============================================================================
# SVG 렌더링
# ============================================================================

def render_pattern_svg(pattern_layout: str, main_color: str, sub_color: str, pattern_color: str, size: int = 200) -> str:
    """패턴별 SVG 생성 (모든 패턴에 3가지 색 사용)"""
    
    if pattern_layout == "full_main":
        # 단색처럼 보이지만 경계에 3색 포인트
        border = size * 0.1
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="0" y="0" width="{border}" height="{border}" fill="{sub_color}" stroke="#000" stroke-width="1"/><rect x="{size-border}" y="{size-border}" width="{border}" height="{border}" fill="{pattern_color}" stroke="#000" stroke-width="1"/>'
    
    elif pattern_layout == "split_v":
        # 세로 3분할
        third = size / 3
        return f'<rect x="0" y="0" width="{third}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{third}" y="0" width="{third}" height="{size}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="{third*2}" y="0" width="{third}" height="{size}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "split_h":
        # 가로 3분할
        third = size / 3
        return f'<rect x="0" y="0" width="{size}" height="{third}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="0" y="{third}" width="{size}" height="{third}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="0" y="{third*2}" width="{size}" height="{third}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "quad":
        # 4분할 + 중앙
        half = size / 2
        center_size = size * 0.2
        center_offset = (size - center_size) / 2
        return f'<rect x="0" y="0" width="{half}" height="{half}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{half}" y="0" width="{half}" height="{half}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="0" y="{half}" width="{half}" height="{half}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="{half}" y="{half}" width="{half}" height="{half}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{center_offset}" y="{center_offset}" width="{center_size}" height="{center_size}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "frame":
        # 3단 프레임
        border1 = size * 0.15
        border2 = size * 0.30
        inner = size - border2 * 2
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{border1}" y="{border1}" width="{size-border1*2}" height="{size-border1*2}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="{border2}" y="{border2}" width="{inner}" height="{inner}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "diagonal":
        # 대각선 3분할
        mid = size / 2
        return f'<polygon points="0,0 {size},0 {mid},{mid}" fill="{main_color}" stroke="#000" stroke-width="2"/><polygon points="0,0 0,{size} {mid},{mid}" fill="{sub_color}" stroke="#000" stroke-width="2"/><polygon points="{size},0 {size},{size} 0,{size} {mid},{mid}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "core_center":
        # 중앙 원형 코어 (바깥 네모)
        center = size / 2
        middle_radius = size * 0.35
        core_radius = size * 0.2
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><circle cx="{center}" cy="{center}" r="{middle_radius}" fill="{sub_color}" stroke="#000" stroke-width="2"/><circle cx="{center}" cy="{center}" r="{core_radius}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "stripe_v":
        # 세로 줄무늬 (3색 순환)
        stripe_width = size / 6
        stripes = ""
        colors = [main_color, sub_color, pattern_color]
        for i in range(6):
            color = colors[i % 3]
            stripes += f'<rect x="{i * stripe_width}" y="0" width="{stripe_width}" height="{size}" fill="{color}" stroke="#000" stroke-width="1"/>'
        return stripes
    
    elif pattern_layout == "stripe_h":
        # 가로 줄무늬 (3색 순환)
        stripe_height = size / 6
        stripes = ""
        colors = [main_color, sub_color, pattern_color]
        for i in range(6):
            color = colors[i % 3]
            stripes += f'<rect x="0" y="{i * stripe_height}" width="{size}" height="{stripe_height}" fill="{color}" stroke="#000" stroke-width="1"/>'
        return stripes
    
    elif pattern_layout == "cross":
        # 십자가
        arm_width = size * 0.3
        arm_offset = (size - arm_width) / 2
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{arm_offset}" y="0" width="{arm_width}" height="{size}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="0" y="{arm_offset}" width="{size}" height="{arm_width}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "diamond":
        # 다이아몬드 3층
        mid = size / 2
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><polygon points="{mid},10 {size-10},{mid} {mid},{size-10} 10,{mid}" fill="{sub_color}" stroke="#000" stroke-width="2"/><polygon points="{mid},{size*0.25} {size*0.75},{mid} {mid},{size*0.75} {size*0.25},{mid}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "border_thick":
        # X자 크로스 (대각선 교차)
        mid = size / 2
        thickness = size * 0.15
        # 배경
        svg = f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/>'
        # 왼쪽 위에서 오른쪽 아래 대각선
        svg += f'<polygon points="0,0 {thickness},{thickness} {size},{size} {size-thickness},{size} 0,{thickness}" fill="{sub_color}" stroke="#000" stroke-width="2"/>'
        # 오른쪽 위에서 왼쪽 아래 대각선
        svg += f'<polygon points="{size},0 {size},{thickness} {thickness},{size} 0,{size} 0,{size-thickness} {size-thickness},0" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
        return svg
    
    elif pattern_layout == "fractured_core":
        # 깨진 중심
        q = size / 4
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><rect x="{q}" y="{q}" width="{q}" height="{q}" fill="{sub_color}" stroke="#000" stroke-width="2"/><rect x="{q*2}" y="{q}" width="{q}" height="{q}" fill="{pattern_color}" stroke="#000" stroke-width="2"/><rect x="{q}" y="{q*2}" width="{q}" height="{q}" fill="{pattern_color}" stroke="#000" stroke-width="2"/><rect x="{q*2}" y="{q*2}" width="{q}" height="{q}" fill="{sub_color}" stroke="#000" stroke-width="2"/>'
    
    elif pattern_layout == "spiral":
        # 나선형 (회전하는 3색 팔)
        mid = size / 2
        svg = f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/>'
        # 3개의 나선 팔
        for i in range(3):
            angle = i * 120
            rad = angle * 3.14159 / 180
            # 곡선 팔 생성
            x1 = mid + size * 0.15 * math.cos(rad)
            y1 = mid + size * 0.15 * math.sin(rad)
            x2 = mid + size * 0.45 * math.cos(rad + 0.5)
            y2 = mid + size * 0.45 * math.sin(rad + 0.5)
            x3 = mid + size * 0.5 * math.cos(rad + 0.8)
            y3 = mid + size * 0.5 * math.sin(rad + 0.8)
            
            svg += f'<path d="M {mid},{mid} L {x1},{y1} Q {x2},{y2} {x3},{y3}" fill="{sub_color}" stroke="#000" stroke-width="2"/>'
        
        # 중앙 원
        svg += f'<circle cx="{mid}" cy="{mid}" r="{size*0.1}" fill="{pattern_color}" stroke="#000" stroke-width="2"/>'
        return svg
    
    elif pattern_layout == "checkerboard":
        # 체크보드 (3색)
        cell = size / 4
        squares = ""
        colors = [main_color, sub_color, pattern_color]
        for i in range(4):
            for j in range(4):
                color = colors[(i + j) % 3]
                squares += f'<rect x="{i*cell}" y="{j*cell}" width="{cell}" height="{cell}" fill="{color}" stroke="#000" stroke-width="1"/>'
        return squares
    
    elif pattern_layout == "mandala":
        # 만다라 패턴 (대칭)
        mid = size / 2
        r1 = size * 0.4
        r2 = size * 0.25
        r3 = size * 0.1
        circles = f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/><circle cx="{mid}" cy="{mid}" r="{r1}" fill="{sub_color}" stroke="#000" stroke-width="2"/><circle cx="{mid}" cy="{mid}" r="{r2}" fill="{pattern_color}" stroke="#000" stroke-width="2"/><circle cx="{mid}" cy="{mid}" r="{r3}" fill="{main_color}" stroke="#000" stroke-width="2"/>'
        # 8개의 대칭 원들
        for i in range(8):
            angle = i * 45
            rad = angle * 3.14159 / 180
            x = mid + r2 * 1.5 * math.cos(rad)
            y = mid + r2 * 1.5 * math.sin(rad)
            circles += f'<circle cx="{x}" cy="{y}" r="{r3*0.8}" fill="{sub_color}" stroke="#000" stroke-width="1"/>'
        return circles
    
    elif pattern_layout == "explosion":
        # 방사형 폭발
        mid = size / 2
        triangles = f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/>'
        colors = [sub_color, pattern_color, sub_color]
        for i in range(8):
            angle1 = i * 45
            angle2 = (i + 1) * 45
            rad1 = angle1 * 3.14159 / 180
            rad2 = angle2 * 3.14159 / 180
            x1 = mid + (size * 0.5) * math.cos(rad1)
            y1 = mid + (size * 0.5) * math.sin(rad1)
            x2 = mid + (size * 0.5) * math.cos(rad2)
            y2 = mid + (size * 0.5) * math.sin(rad2)
            color = colors[i % 3]
            triangles += f'<polygon points="{mid},{mid} {x1},{y1} {x2},{y2}" fill="{color}" stroke="#000" stroke-width="2"/>'
        return triangles
    
    elif pattern_layout == "cosmic":
        # 우주 (그라디언트 + 별)
        svg = f'<defs><radialGradient id="cosmic-grad-{hash(main_color)}"><stop offset="0%" style="stop-color:{sub_color};stop-opacity:1" /><stop offset="100%" style="stop-color:{main_color};stop-opacity:1" /></radialGradient></defs><rect x="0" y="0" width="{size}" height="{size}" fill="url(#cosmic-grad-{hash(main_color)})" stroke="#000" stroke-width="2"/>'
        # 별 추가
        star_seed = hash(main_color + sub_color) % 10000
        random.seed(star_seed)
        for _ in range(15):
            x = random.uniform(10, size - 10)
            y = random.uniform(10, size - 10)
            r = random.uniform(2, 5)
            svg += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{pattern_color}" stroke="none"/>'
        return svg
    
    else:
        # 기본값
        return f'<rect x="0" y="0" width="{size}" height="{size}" fill="{main_color}" stroke="#000" stroke-width="2"/>'

def get_instance_svg(instance: Dict, size: int = 200) -> str:
    """개체 정보에서 SVG 렌더링 (캐싱 래퍼)"""
    return render_instance_svg_cached(
        instance['id'],
        instance['appearance']['main_color']['id'],
        instance['appearance']['sub_color']['id'],
        instance['appearance']['pattern_color']['id'],
        instance['appearance']['pattern']['id'],
        size
    )

# ============================================================================
# Streamlit UI
# ============================================================================

def get_user_save_file(username: str) -> str:
    """사용자별 저장 파일 경로 반환 (레거시, 현재는 Supabase 사용)"""
    # Supabase 사용으로 이 함수는 더 이상 필요 없지만, 호환성을 위해 유지
    safe_username = username.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return f"saves/{safe_username}_data.json"

def get_season_history_file() -> str:
    """시즌 히스토리 파일 경로 (레거시, 현재는 Supabase 사용)"""
    # Supabase 사용으로 이 함수는 더 이상 필요 없지만, 호환성을 위해 유지
    return "saves/season_history.json"

def load_season_history() -> Dict:
    """시즌 히스토리 로드 (Supabase에서)"""
    season_data = load_season_history_db()
    
    if not season_data:
        return {
            "current_season": 0,
            "season_end_time": None,
            "history": []
        }
    
    return season_data

def save_season_history(season_data: Dict):
    """시즌 히스토리 저장 (Supabase에 저장)"""
    try:
        save_season_history_db(season_data)
    except Exception as e:
        print(f"❌ 시즌 히스토리 저장 실패: {e}")

def end_current_season(to_preseason=False):
    """현재 시즌 종료 및 새 시즌 시작
    
    Args:
        to_preseason: True면 프리시즌으로 전환 (데이터 초기화 안함), False면 정식 시즌으로 전환
    """
    season_data = load_season_history()
    current_season = season_data["current_season"]
    
    # 현재 시즌 상위 3명 수집
    top3_users = get_all_users_representatives()[:3]
    
    # 히스토리에 추가 (Preseason은 기록하지 않음)
    if current_season != "Preseason":
        season_data["history"].append({
            "season": current_season,
            "top3": top3_users,
            "end_time": datetime.now().isoformat()
        })
    
    # 시즌 0 챔피언 기록 (프리시즌 전환 시)
    if to_preseason and current_season == 0 and top3_users:
        season_data["season0_champion"] = top3_users[0]["username"]
    
    # 새 시즌 시작
    if to_preseason:
        season_data["current_season"] = "Preseason"
    else:
        # 정식 시즌 시작 (Preseason -> 1)
        if current_season == "Preseason":
            season_data["current_season"] = 1
        else:
            season_data["current_season"] = current_season + 1
    season_data["season_end_time"] = None
    
    save_season_history(season_data)
    
    # 프리시즌으로 전환 시에는 데이터 초기화하지 않음
    if to_preseason:
        return season_data["current_season"]
    
    # 1등 유저 확인 (보너스 부여용)
    # 정식 시즌 시작 시 시즌 0 챔피언에게 보너스
    first_place_username = None
    if "season0_champion" in season_data and season_data["season0_champion"]:
        first_place_username = season_data["season0_champion"]
    elif top3_users:
        first_place_username = top3_users[0]["username"]
    
    # ========================================
    # Supabase 데이터 초기화
    # ========================================
    
    # 1. 모든 유저 게임 데이터 초기화 (비밀번호는 유지)
    success_count, fail_count, failed_users = reset_all_user_game_data(
        keep_password=True,
        champion_username=first_place_username
    )
    print(f"✅ Supabase 유저 데이터 초기화: {success_count}명 성공, {fail_count}명 실패")
    if failed_users:
        print(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
    
    # 2. 우편함 전체 삭제
    mail_success, mail_count = clear_all_mailbox()
    if mail_success:
        print(f"✅ 우편함 데이터 {mail_count}개 삭제 완료")
    else:
        print(f"⚠️ 우편함 삭제 실패")
    
    # ========================================
    # 로컬 파일 초기화 (레거시 지원)
    # ========================================
    
    # 모든 유저 데이터 초기화 (비밀번호만 유지)
    if os.path.exists("saves"):
        for filename in os.listdir("saves"):
            if filename.endswith("_data.json"):
                filepath = os.path.join("saves", filename)
                try:
                    # 기존 데이터 로드
                    with open(filepath, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    
                    # 파일명에서 유저명 추출
                    username = filename.replace("_data.json", "").replace("_", " ")
                    
                    # 1등 유저에게 돌연변이 보너스 및 연쇄 증가 부여
                    mutation_bonus = 0.1 if username == first_place_username else 0.0
                    max_chain = 4 if username == first_place_username else 3
                    
                    # 초기 개체 2마리 생성
                    starter_a = create_initial_instance()
                    starter_a["name"] = "Starter A"
                    starter_b = create_initial_instance()
                    starter_b["name"] = "Starter B"
                    
                    # 비밀번호(해시) 유지하고 나머지는 초기화
                    new_data = {
                        "password_hash": old_data.get("password_hash", old_data.get("password", "")),  # 구 버전 호환
                        "cheat_level": "user",
                        "instances": [starter_a, starter_b],
                        "last_breed_time": None,
                        "representative_id": None,
                        "offspring_counter": 0,
                        "last_random_box_time": None,
                        "max_instances": 200,
                        "collection": {
                            "colors": {"main": ["normal01"], "sub": ["normal01"], "pattern": ["normal01"]},
                            "patterns": ["normal01"],
                            "accessories": [],
                            "skills": {"slot1": [], "slot2": [], "slot3": []}
                        },
                        "max_power": 0,
                        "mutation_bonus": mutation_bonus,
                        "max_chain_mutations": max_chain,
                        "current_stage": 1
                    }
                    
                    # 초기화된 데이터 저장
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(new_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error resetting {filename}: {e}")
    
    # 새 시즌 번호 반환
    return season_data["current_season"]

def save_game_data():
    """게임 데이터 저장 (Supabase에 저장)"""
    if "username" not in st.session_state or not st.session_state.username:
        return
    
    # 컬렉션을 JSON 직렬화 가능한 형태로 변환
    collection_data = st.session_state.get("collection", {
        "colors": {"main": set(), "sub": set(), "pattern": set()},
        "patterns": set(),
        "accessories": set(),
        "skills": {"slot1": set(), "slot2": set(), "slot3": set()}
    })
    
    # skills가 없으면 추가 (하위 호환성)
    if "skills" not in collection_data:
        collection_data["skills"] = {"slot1": set(), "slot2": set(), "slot3": set()}
    
    collection_json = {
        "colors": {
            "main": list(collection_data["colors"]["main"]),
            "sub": list(collection_data["colors"]["sub"]),
            "pattern": list(collection_data["colors"]["pattern"])
        },
        "patterns": list(collection_data["patterns"]),
        "accessories": list(collection_data["accessories"]),
        "skills": {
            "slot1": list(collection_data["skills"]["slot1"]),
            "slot2": list(collection_data["skills"]["slot2"]),
            "slot3": list(collection_data["skills"]["slot3"])
        }
    }
    
    data = {
        "password_hash": st.session_state.get("password_hash", ""),
        "cheat_level": st.session_state.get("cheat_level", "user"),
        "instances": st.session_state.instances,
        "last_breed_time": st.session_state.last_breed_time,
        "representative_id": st.session_state.get("representative_id", None),
        "offspring_counter": st.session_state.get("offspring_counter", 0),
        "last_random_box_time": st.session_state.get("last_random_box_time", None),
        "max_instances": st.session_state.get("max_instances", 200),
        "collection": collection_json,
        "max_power": st.session_state.get("max_power", 0),
        "mutation_bonus": st.session_state.get("mutation_bonus", 0.0),
        "max_chain_mutations": st.session_state.get("max_chain_mutations", 3),
        "current_stage": st.session_state.get("current_stage", 1),
        "tutorial_seen": st.session_state.get("tutorial_seen", False)
    }
    
    # Supabase에 저장
    try:
        save_game_data_db(st.session_state.username, data)
    except Exception as e:
        # 에러는 조용히 처리
        print(f"게임 데이터 저장 중 오류: {e}")
        pass

def load_game_data(username: str) -> Optional[Dict]:
    """게임 데이터 로드 (Supabase에서)"""
    try:
        data = load_game_data_db(username)
        
        if data:
            # 데이터 마이그레이션: accessories를 skills 슬롯별로 분류 (호환성 유지)
            if "collection" in data:
                if "skills" not in data["collection"]:
                    data["collection"]["skills"] = {"slot1": [], "slot2": [], "slot3": []}
                
                # 기존 accessories 배열을 슬롯별로 분류
                if "accessories" in data["collection"] and isinstance(data["collection"]["accessories"], list):
                    for skill_id in data["collection"]["accessories"]:
                        if skill_id.startswith("acc1_"):
                            if skill_id not in data["collection"]["skills"]["slot1"]:
                                data["collection"]["skills"]["slot1"].append(skill_id)
                        elif skill_id.startswith("acc2_"):
                            if skill_id not in data["collection"]["skills"]["slot2"]:
                                data["collection"]["skills"]["slot2"].append(skill_id)
                        elif skill_id.startswith("acc3_"):
                            if skill_id not in data["collection"]["skills"]["slot3"]:
                                data["collection"]["skills"]["slot3"].append(skill_id)
            
            return data
        return None
    except Exception as e:
        print(f"❌ 데이터 로드 실패: {e}")
        return None

def user_exists(username: str) -> bool:
    """사용자 존재 여부 확인 (Supabase)"""
    from supabase_db import check_user_exists as check_from_db
    try:
        return check_from_db(username)
    except:
        return False

def verify_password(username: str, password: str) -> bool:
    """비밀번호 확인 (해시 기반, Supabase)"""
    from supabase_db import get_user_password_hash
    try:
        password_hash = get_user_password_hash(username)
        if password_hash:
            return hash_password(password) == password_hash
        return False
    except:
        return False

def calculate_power_score(stats: Dict) -> int:
    """전투력 계산: HP + ATK×10 + MS×5
    - HP는 생존력
    - ATK는 공격력 (가중치 10)
    - MS는 속도 (가중치 5)
    """
    return stats["hp"] + stats["atk"] * 10 + stats["ms"] * 5


def format_korean_number(n: int) -> str:
    """한국식 계층적 단위 표기: 경(10^16), 조(10^12), 억(10^8), 만(10^4)
    - 예: 123456789 -> '1억 2345만 6789'
    - 음수도 지원
    """
    if n == 0:
        return "0"
    
    try:
        is_negative = n < 0
        abs_n = abs(n)
        
        # 단위별 (base, label)
        units = [
            (10**16, "경"),
            (10**12, "조"),
            (10**8, "억"),
            (10**4, "만"),
        ]
        
        result = ""
        remaining = abs_n
        
        for base, label in units:
            if remaining >= base:
                digit_count = remaining // base
                result += str(digit_count) + label + " "
                remaining = remaining % base
        
        # 일 단위 (1000 미만, 0이면 표시 안 함)
        if remaining > 0:
            result += str(remaining)
        
        return ("-" if is_negative else "") + result.strip()
    except Exception:
        return str(n)


def get_all_users_representatives() -> List[Dict]:
    """모든 사용자의 대표 유닛 정보 수집"""
    representatives = []
    
    # 방법 1: Supabase에서 시도
    try:
        from supabase_db import get_all_users, load_game_data as db_load_game_data
        
        users = get_all_users()
        
        for user in users:
            username = user.get("username")
            if not username:
                continue
            
            # 게임 데이터 로드 (Supabase)
            game_data = db_load_game_data(username)
            if not game_data:
                continue
            
            # 대표 유닛 확인
            rep_id = game_data.get("representative_id")
            if not rep_id:
                continue
            
            instances = game_data.get("instances", [])
            rep_inst = next((inst for inst in instances if inst.get("id") == rep_id), None)
            
            if rep_inst and rep_inst.get("stats"):
                representatives.append({
                    "username": username,
                    "instance": rep_inst,
                    "power_score": calculate_power_score(rep_inst["stats"])
                })
    except Exception as e:
        print(f"⚠️ Supabase 랭킹 조회 실패: {e}")
    
    # 방법 2: 로컬 파일에서 보완 (Supabase 미사용 혹은 실패 시)
    if not representatives and os.path.exists("saves"):
        try:
            for filename in os.listdir("saves"):
                if filename.endswith("_data.json"):
                    try:
                        filepath = os.path.join("saves", filename)
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        rep_id = data.get("representative_id")
                        if rep_id:
                            instances = data.get("instances", [])
                            rep_inst = next((inst for inst in instances if inst.get("id") == rep_id), None)
                            
                            if rep_inst and rep_inst.get("stats"):
                                username = filename.replace("_data.json", "")
                                representatives.append({
                                    "username": username,
                                    "instance": rep_inst,
                                    "power_score": calculate_power_score(rep_inst["stats"])
                                })
                    except Exception:
                        continue
        except Exception as e:
            print(f"⚠️ 로컬 파일 랭킹 조회 실패: {e}")
    
    # 전투력 순으로 정렬
    representatives.sort(
        key=lambda x: (
            x["power_score"],
            x["instance"].get("stats", {}).get("hp", 0),
            x["instance"].get("stats", {}).get("atk", 0),
            x["instance"].get("stats", {}).get("ms", 0),
            x["username"]
        ),
        reverse=True
    )
    
    return representatives

def cleanup_session_state():
    """불필요한 세션 상태 정리 (메모리 최적화)"""
    # 임시 페이지 상태 정리
    temp_keys = [key for key in st.session_state.keys() 
                 if key.startswith('temp_') or key.startswith('_')]
    for key in temp_keys:
        del st.session_state[key]
    
    # 브리딩 결과 정리 (저장 후)
    if 'breed_result' in st.session_state and st.session_state.breed_result:
        # 결과가 이미 저장되었으면 제거
        result_id = st.session_state.breed_result.get('id')
        if result_id and any(inst['id'] == result_id for inst in st.session_state.instances):
            st.session_state.breed_result = None

def cleanup_session_state():
    """불필요한 세션 상태 정리 (메모리 최적화)"""
    # 임시 페이지 상태 정리
    temp_keys = [key for key in st.session_state.keys() 
                 if key.startswith('temp_') or key.startswith('_')]
    for key in temp_keys:
        del st.session_state[key]
    
    # 브리딩 결과 정리 (저장 후)
    if 'breed_result' in st.session_state and st.session_state.breed_result:
        # 결과가 이미 저장되었으면 제거
        result_id = st.session_state.breed_result.get('id')
        if result_id and any(inst['id'] == result_id for inst in st.session_state.instances):
            st.session_state.breed_result = None

def init_session_state():
    """세션 상태 초기화"""
    # 로그인 상태 초기화
    if "username" not in st.session_state:
        st.session_state.username = None
    
    if "password_hash" not in st.session_state:
        st.session_state.password_hash = None
    
    # 로그인하지 않은 경우 여기서 멈춤
    if not st.session_state.username:
        return
    
    # 메모리 정리 (5분마다)
    current_time = time.time()
    if "last_cleanup" not in st.session_state:
        st.session_state.last_cleanup = current_time
    elif current_time - st.session_state.last_cleanup > 300:  # 5분
        cleanup_session_state()
        st.session_state.last_cleanup = current_time
    
    # 기본 세션 상태 먼저 초기화
    if "last_breed_time" not in st.session_state:
        st.session_state.last_breed_time = None
    
    if "breed_result" not in st.session_state:
        st.session_state.breed_result = None
    
    if "page" not in st.session_state:
        st.session_state.page = "home"
    
    if "selected_parent_a" not in st.session_state:
        st.session_state.selected_parent_a = None
    
    if "selected_parent_b" not in st.session_state:
        st.session_state.selected_parent_b = None
    
    # instances 초기화
    if "instances" not in st.session_state:
        # 저장된 데이터 로드 시도
        saved_data = load_game_data(st.session_state.username)
        if saved_data:
            st.session_state.instances = saved_data.get("instances", [])
            st.session_state.last_breed_time = saved_data.get("last_breed_time")
            st.session_state.representative_id = saved_data.get("representative_id", None)
            st.session_state.cheat_level = saved_data.get("cheat_level", "user")
            st.session_state.offspring_counter = saved_data.get("offspring_counter", 0)
            st.session_state.last_random_box_time = saved_data.get("last_random_box_time", None)
            st.session_state.max_instances = saved_data.get("max_instances", 200)  # 기본값 200
            st.session_state.max_power = saved_data.get("max_power", 0)
            st.session_state.mutation_bonus = saved_data.get("mutation_bonus", 0.0)  # 돌연변이 확률 보너스
            st.session_state.max_chain_mutations = saved_data.get("max_chain_mutations", 3)  # 최대 연쇄 횟수
            st.session_state.current_stage = saved_data.get("current_stage", 1)  # 보스 스테이지
            st.session_state.tutorial_seen = saved_data.get("tutorial_seen", False)  # 튜토리얼 확인 여부
            
            # 비밀번호 해시 로드 (신규) - 구버전 호환
            if "password_hash" in saved_data:
                st.session_state.password_hash = saved_data["password_hash"]
            elif "password" in saved_data and saved_data["password"]:
                # 구 버전 평문을 해시로 변환
                st.session_state.password_hash = hash_password(saved_data["password"])
            
            # 컬렉션 데이터 로드 및 변환
            collection_data = saved_data.get("collection", None)
            if collection_data is None:
                # 컬렉션이 없으면 새 구조로 초기화
                st.session_state.collection = {
                    "colors": {"main": set(), "sub": set(), "pattern": set()},
                    "patterns": set(),
                    "accessories": set(),
                    "skills": {"slot1": set(), "slot2": set(), "slot3": set()}
                }
                # 초기 개체들의 collection 일괄 추가 (최적화)
                for inst in st.session_state.instances:
                    # update_collection 대신 직접 추가
                    st.session_state.collection["colors"]["main"].add(inst['appearance']['main_color']['id'])
                    st.session_state.collection["colors"]["sub"].add(inst['appearance']['sub_color']['id'])
                    st.session_state.collection["colors"]["pattern"].add(inst['appearance']['pattern_color']['id'])
                    st.session_state.collection["patterns"].add(inst['appearance']['pattern']['id'])
                    for i in range(1, 4):
                        acc_key = f"accessory_{i}"
                        if inst.get(acc_key):
                            skill_id = inst[acc_key]['id']
                            st.session_state.collection["accessories"].add(skill_id)
                            if skill_id.startswith("acc1_"):
                                st.session_state.collection["skills"]["slot1"].add(skill_id)
                            elif skill_id.startswith("acc2_"):
                                st.session_state.collection["skills"]["slot2"].add(skill_id)
                            elif skill_id.startswith("acc3_"):
                                st.session_state.collection["skills"]["slot3"].add(skill_id)
                save_game_data()
            elif isinstance(collection_data, list):
                # 구 형식 (단순 리스트)을 새 형식으로 변환
                st.session_state.collection = {
                    "colors": {"main": set(), "sub": set(), "pattern": set()},
                    "patterns": set(),
                    "accessories": set(),
                    "skills": {"slot1": set(), "slot2": set(), "slot3": set()}
                }
                # 기존 개체들로 재구성 (최적화)
                for inst in st.session_state.instances:
                    st.session_state.collection["colors"]["main"].add(inst['appearance']['main_color']['id'])
                    st.session_state.collection["colors"]["sub"].add(inst['appearance']['sub_color']['id'])
                    st.session_state.collection["colors"]["pattern"].add(inst['appearance']['pattern_color']['id'])
                    st.session_state.collection["patterns"].add(inst['appearance']['pattern']['id'])
                    for i in range(1, 4):
                        acc_key = f"accessory_{i}"
                        if inst.get(acc_key):
                            skill_id = inst[acc_key]['id']
                            st.session_state.collection["accessories"].add(skill_id)
                            if skill_id.startswith("acc1_"):
                                st.session_state.collection["skills"]["slot1"].add(skill_id)
                            elif skill_id.startswith("acc2_"):
                                st.session_state.collection["skills"]["slot2"].add(skill_id)
                            elif skill_id.startswith("acc3_"):
                                st.session_state.collection["skills"]["slot3"].add(skill_id)
                save_game_data()
            else:
                # 새 형식 로드
                st.session_state.collection = {
                    "colors": {
                        "main": set(collection_data.get("colors", {}).get("main", [])),
                        "sub": set(collection_data.get("colors", {}).get("sub", [])),
                        "pattern": set(collection_data.get("colors", {}).get("pattern", []))
                    },
                    "patterns": set(collection_data.get("patterns", [])),
                    "accessories": set(collection_data.get("accessories", [])),
                    "skills": {
                        "slot1": set(collection_data.get("skills", {}).get("slot1", [])),
                        "slot2": set(collection_data.get("skills", {}).get("slot2", [])),
                        "slot3": set(collection_data.get("skills", {}).get("slot3", []))
                    }
                }
        else:
            # 초기 개체 2마리 생성
            st.session_state.instances = [
                create_initial_instance(),
                create_initial_instance()
            ]
            st.session_state.instances[0]["name"] = "Starter A"
            st.session_state.instances[1]["name"] = "Starter B"
            st.session_state.representative_id = None
            st.session_state.cheat_level = "user"
            st.session_state.offspring_counter = 0
            st.session_state.last_random_box_time = None
            st.session_state.max_instances = 200
            st.session_state.mutation_bonus = 0.0  # 초기 돌연변이 보너스
            st.session_state.max_chain_mutations = 3  # 초기 최대 연쇄 횟수
            st.session_state.collection = {
                "colors": {"main": set(), "sub": set(), "pattern": set()},
                "patterns": set(),
                "accessories": set(),
                "skills": {"slot1": set(), "slot2": set(), "slot3": set()}
            }
            # 초기 개체들로 collection 초기화 (최적화)
            for inst in st.session_state.instances:
                st.session_state.collection["colors"]["main"].add(inst['appearance']['main_color']['id'])
                st.session_state.collection["colors"]["sub"].add(inst['appearance']['sub_color']['id'])
                st.session_state.collection["colors"]["pattern"].add(inst['appearance']['pattern_color']['id'])
                st.session_state.collection["patterns"].add(inst['appearance']['pattern']['id'])
                for i in range(1, 4):
                    acc_key = f"accessory_{i}"
                    if inst.get(acc_key):
                        skill_id = inst[acc_key]['id']
                        st.session_state.collection["accessories"].add(skill_id)
                        if skill_id.startswith("acc1_"):
                            st.session_state.collection["skills"]["slot1"].add(skill_id)
                        elif skill_id.startswith("acc2_"):
                            st.session_state.collection["skills"]["slot2"].add(skill_id)
                        elif skill_id.startswith("acc3_"):
                            st.session_state.collection["skills"]["slot3"].add(skill_id)
            save_game_data()

def display_instance_card(instance: Dict, show_details: bool = False, show_compact: bool = False):
    """개체 카드 표시 (간결 버전)
    Args:
        instance: 개체 데이터
        show_details: 상세 정보 표시 (구 버전 호환성)
        show_compact: 간결 모드 (리스트용, expander로 상세정보 숨김)
    """
    # 2열 레이아웃: 왼쪽 이미지, 오른쪽 정보
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # 개체 이미지
        svg = get_instance_svg(instance, size=120)
        st.markdown(svg, unsafe_allow_html=True)
    
    with col2:
        # 이름과 전투력
        st.markdown(f"### {instance['name']}")
        power_score = instance.get("power_score", calculate_power_score(instance["stats"]))
        st.markdown(f"💪 **전투력: {format_korean_number(power_score)}**")
        
        # 스탯 (한 줄로)
        st.markdown(f"**HP** {instance['stats']['hp']:,} | **ATK** {instance['stats']['atk']:,} | **MS** {instance['stats']['ms']:,}")
        
        # 스킬 (항상 표시)
        st.markdown("**⚔️ 스킬:**")
        has_skill = False
        for i in range(1, 4):
            acc_key = f"accessory_{i}"
            if instance.get(acc_key) and instance[acc_key]["id"] in SKILL_MASTER:
                skill = SKILL_MASTER[instance[acc_key]["id"]]
                cooldown = skill.get('cooldown', 0)
                st.markdown(f"• **{skill['name']}** ({skill['grade']})")
                st.caption(f"{skill['desc']} (쿨타임: {cooldown}턴)")
                has_skill = True
            else:
                st.caption(f"슬롯 {i}: 없음")
        if not has_skill:
            st.caption("장착된 스킬 없음")
    
    # 상세 정보 (간결 모드인 경우 expander로 숨김)
    if show_compact or show_details:
        with st.expander("🔍 외형 상세 정보"):
            _display_detailed_info(instance)

def _display_detailed_info(instance: Dict):
    """개체 상세 정보 표시 (내부 함수)"""
    st.markdown("**외형**")
    
    # 색상 정보 (실제 색상 표시)
    main_color = COLOR_MASTER[instance['appearance']['main_color']['id']]
    sub_color = COLOR_MASTER[instance['appearance']['sub_color']['id']]
    pattern_color = COLOR_MASTER[instance['appearance']['pattern_color']['id']]
    
    st.markdown(f"""
    <div style="display: flex; align-items: center; margin-bottom: 5px;">
        <div style="width: 30px; height: 30px; background-color: {main_color['hex']}; border: 2px solid #000; margin-right: 10px;"></div>
        <span>Main Color: {main_color['name']} ({instance['appearance']['main_color']['grade']})</span>
    </div>
    <div style="display: flex; align-items: center; margin-bottom: 5px;">
        <div style="width: 30px; height: 30px; background-color: {sub_color['hex']}; border: 2px solid #000; margin-right: 10px;"></div>
        <span>Sub Color: {sub_color['name']} ({instance['appearance']['sub_color']['grade']})</span>
    </div>
    <div style="display: flex; align-items: center; margin-bottom: 5px;">
        <div style="width: 30px; height: 30px; background-color: {pattern_color['hex']}; border: 2px solid #000; margin-right: 10px;"></div>
        <span>Pattern Color: {pattern_color['name']} ({instance['appearance']['pattern_color']['grade']})</span>
    </div>
    <div style="margin-top: 10px;">Pattern: {PATTERN_MASTER[instance['appearance']['pattern']['id']]['layout']} ({instance['appearance']['pattern']['grade']})</div>
    """, unsafe_allow_html=True)
    
    acc_lines = []
    for i in range(1, 4):
        acc = instance.get(f"accessory_{i}")
        if acc:
            acc_lines.append(f"- Slot {i}: {ACCESSORY_MASTER[acc['id']]['name']} ({acc['grade']})")
        else:
            acc_lines.append(f"- Slot {i}: None")
    
    st.markdown("**악세서리**  \n" + "  \n".join(acc_lines))
    
    # 메타 정보
    st.markdown("""**메타**  
- ID: {0}  
- Created: {1}  
- Birth: {2}  
- Locked: {3}  
- Favorite: {4}""".format(
        instance['id'],
        instance['created_by'],
        instance['birth_time'][:19],
        instance['is_locked'],
        instance['is_favorite']
    ))
    
    if instance['mutation']['count'] > 0:
        st.markdown(f"**돌연변이 ({instance['mutation']['count']}회)**  \n- Fields: {', '.join(instance['mutation']['fields'])}")

@st.dialog("🎓 시작 가이드", width="large")
def show_tutorial():
    """튜토리얼 팝업 표시"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ## 📌 **1단계: 시작 개체**
        
        📋 **개체 목록**에 **Starter A**와 **B**가 있어요!
        
        ## 📌 **2단계: 믹스 (핵심!)**
        
        🧬 **믹스** 버튼으로 두 개체를 섞으세요!
        - 능력치와 외형이 유전돼요
        - 돌연변이로 더 강해져요!
        
        💡 전투력 높은 개체끼리 믹스!
        """)
    
    with col2:
        st.markdown("""
        ## 📌 **3단계: 전투**
        
        ⚔️ **전투** 버튼으로 보스를 클리어하세요!
        
        ## 📌 **4단계: 대표 설정**
        
        📋 가장 강한 개체를 **👑 대표 설정**하세요!
        - 랭킹 자동 등록
        - 전투 기본 선택
        """)
    
    st.markdown("---")
    
    st.markdown("""
    <div style='background-color: #2d5016; padding: 12px; border-radius: 6px; border-left: 4px solid #4CAF50; color: #ffffff;'>
    <strong>🎯 목표:</strong> 믹스 → 전투 → 랭킹 1등! | 💡 팁: ⭐즐겨찾기 🔒잠금 🎁랜덤박스(24시간 쿨타임)
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("")
    
@st.dialog("🎓 시작 가이드", width="large")
def show_tutorial():
    """튜토리얼 팝업 표시"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ## 📌 **1단계: 시작 개체**
        
        📋 **개체 목록**에 **Starter A**와 **B**가 있어요!
        
        ## 📌 **2단계: 믹스 (핵심!)**
        
        🧬 **믹스** 버튼으로 두 개체를 섞으세요!
        - 능력치와 외형이 유전돼요
        - 돌연변이로 더 강해져요!
        
        💡 전투력 높은 개체끼리 믹스!
        """)
    
    with col2:
        st.markdown("""
        ## 📌 **3단계: 전투**
        
        ⚔️ **전투** 버튼으로 보스를 클리어하세요!
        
        ## 📌 **4단계: 대표 설정**
        
        📋 가장 강한 개체를 **👑 대표 설정**하세요!
        - 랭킹 자동 등록
        - 전투 기본 선택
        """)
    
    st.markdown("---")
    
    st.markdown("""
    <div style='background-color: #2d5016; padding: 12px; border-radius: 6px; border-left: 4px solid #4CAF50; color: #ffffff;'>
    <strong>🎯 목표:</strong> 믹스 → 전투 → 랭킹 1등! | 💡 팁: ⭐즐겨찾기 🔒잠금 🎁랜덤박스(하루1회) 💬디스코드
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("")
    
    # 튜토리얼 확인 표시
    if st.button("✅ 시작하기!", use_container_width=True, type="primary"):
        st.session_state.tutorial_seen = True
        save_game_data()
        # st.rerun() 제거 - 버튼 클릭으로 자연스럽게 리렌더링

def page_home():
    """홈 화면"""
    st.title("🧬 Mutant Paint")
    
    # 최초 로그인 시 튜토리얼 자동 표시
    if not st.session_state.get("tutorial_seen", False):
        show_tutorial()
    
    max_instances = st.session_state.get("max_instances", 200)
    current_count = len(st.session_state.instances)
    st.metric("보유 개체 수", f"{current_count}/{max_instances}")
    
    # 튜토리얼 버튼
    if st.button("🎓 튜토리얼 보기", use_container_width=True):
        show_tutorial()
    
    # 시즌 정보 버튼
    if st.button("🏆 시즌 정보", use_container_width=True):
        st.session_state.page = "season_info"
        st.rerun()
    
    # 우편함 버튼 (알림 표시)
    username = st.session_state.username
    unclaimed_count = 0
    mails = load_mailbox(username, unclaimed_only=True)
    unclaimed_count = len(mails)
    
    mailbox_label = f"📬 우편함 ({unclaimed_count})" if unclaimed_count > 0 else "📬 우편함"
    if st.button(mailbox_label, use_container_width=True, type="primary" if unclaimed_count > 0 else "secondary"):
        st.session_state.page = "mailbox"
        st.rerun()
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        if st.button("📋 개체 목록", use_container_width=True):
            st.session_state.page = "list"
            st.rerun()
    
    with col2:
        if st.button("🧬 믹스", use_container_width=True):
            st.session_state.page = "breed"
            st.rerun()
    
    with col3:
        if st.button("⚔️ 전투", use_container_width=True):
            st.session_state.page = "battle"
            st.rerun()
    
    with col4:
        if st.button("🎁 랜덤 박스", use_container_width=True):
            st.session_state.page = "random_box"
            st.rerun()
    
    with col5:
        if st.button("📖 도감", use_container_width=True):
            st.session_state.page = "collection"
            st.rerun()
    
    with col6:
        if st.button("🏆 랭킹", use_container_width=True):
            st.session_state.page = "ranking"
            st.rerun()
    
    # 개발자 권한이 있는 경우에만 개발자 메뉴 표시
    if st.session_state.get("cheat_level", "user") == "dev":
        col_dev1, col_dev2 = st.columns(2)
        with col_dev1:
            if st.button("🛠️ 개발자 메뉴", use_container_width=True):
                st.session_state.page = "dev"
                st.rerun()
        with col_dev2:
            if st.button("👨‍💼 사용자 관리", use_container_width=True):
                st.session_state.page = "admin"
                st.rerun()
    
    # 즐겨찾기 개체
    favorites = [inst for inst in st.session_state.instances if inst["is_favorite"]]
    if favorites:
        st.markdown("### ⭐ 즐겨찾기")
        for fav in favorites[:3]:
            with st.expander(fav["name"]):
                display_instance_card(fav)

def page_list():
    """개체 목록 화면"""
    st.title("📋 개체 목록")
    
    # 개체 수 표시
    max_instances = st.session_state.get("max_instances", 200)
    current_count = len(st.session_state.instances)
    st.info(f"📊 현재 개체 수: {current_count}/{max_instances}")
    
    # 일괄 삭제 버튼
    deletable_count = sum(1 for inst in st.session_state.instances if not inst.get("is_locked", False))
    if deletable_count > 1:
        if st.button("🗑️ 일괄 삭제 모드", use_container_width=True):
            st.session_state.page = "bulk_delete"
            st.rerun()
        st.markdown("---")
    
    # 필터
    st.sidebar.title("필터")
    show_favorites_only = st.sidebar.checkbox("즐겨찾기만")
    show_locked = st.sidebar.checkbox("잠금 포함", value=True)
    
    # 외형 필터
    st.sidebar.markdown("---")
    st.sidebar.markdown("**외형 필터**")
    
    # 보유한 외형 속성 수집
    owned_main_colors = set()
    owned_sub_colors = set()
    owned_pattern_colors = set()
    owned_patterns = set()
    
    for inst in st.session_state.instances:
        owned_main_colors.add(inst["appearance"]["main_color"]["id"])
        owned_sub_colors.add(inst["appearance"]["sub_color"]["id"])
        owned_pattern_colors.add(inst["appearance"]["pattern_color"]["id"])
        owned_patterns.add(inst["appearance"]["pattern"]["id"])
    
    # 등급 순서 정의
    grade_order = {"Normal": 0, "Rare": 1, "Epic": 2, "Unique": 3, "Legendary": 4, "Mystic": 5}
    
    # 색상 옵션 생성 (등급 순서로 정렬)
    main_color_sorted = sorted(owned_main_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    main_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in main_color_sorted]
    main_color_ids = [None] + main_color_sorted
    
    sub_color_sorted = sorted(owned_sub_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    sub_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in sub_color_sorted]
    sub_color_ids = [None] + sub_color_sorted
    
    pattern_color_sorted = sorted(owned_pattern_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    pattern_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in pattern_color_sorted]
    pattern_color_ids = [None] + pattern_color_sorted
    
    # 패턴 옵션 생성 (등급 순서로 정렬)
    pattern_sorted = sorted(owned_patterns, key=lambda x: (grade_order.get(PATTERN_MASTER[x]['grade'], 99), x))
    pattern_options = ["전체"] + [f"{PATTERN_MASTER[pid]['layout']} ({PATTERN_MASTER[pid]['grade']})" for pid in pattern_sorted]
    pattern_ids = [None] + pattern_sorted
    
    main_color_filter_idx = st.sidebar.selectbox("메인 색상", range(len(main_color_options)), format_func=lambda x: main_color_options[x], key="list_main_color")
    main_color_filter = main_color_ids[main_color_filter_idx]
    
    sub_color_filter_idx = st.sidebar.selectbox("서브 색상", range(len(sub_color_options)), format_func=lambda x: sub_color_options[x], key="list_sub_color")
    sub_color_filter = sub_color_ids[sub_color_filter_idx]
    
    pattern_color_filter_idx = st.sidebar.selectbox("패턴 색상", range(len(pattern_color_options)), format_func=lambda x: pattern_color_options[x], key="list_pattern_color")
    pattern_color_filter = pattern_color_ids[pattern_color_filter_idx]
    
    pattern_filter_idx = st.sidebar.selectbox("패턴", range(len(pattern_options)), format_func=lambda x: pattern_options[x], key="list_pattern")
    pattern_filter = pattern_ids[pattern_filter_idx]
    
    # 스킬 필터
    st.sidebar.markdown("---")
    st.sidebar.markdown("**스킬 필터**")
    
    # 보유한 스킬 수집 (슬롯별)
    owned_skills_slot1 = set()
    owned_skills_slot2 = set()
    owned_skills_slot3 = set()
    
    for inst in st.session_state.instances:
        # 여러 데이터 형식 지원
        # 1. skills 딕셔너리 형태
        skills_data = inst.get("skills")
        if skills_data:
            if skills_data.get("slot1"):
                owned_skills_slot1.add(skills_data["slot1"])
            if skills_data.get("slot2"):
                owned_skills_slot2.add(skills_data["slot2"])
            if skills_data.get("slot3"):
                owned_skills_slot3.add(skills_data["slot3"])
        # 2. accessories 딕셔너리 형태
        elif inst.get("accessories"):
            accessories_data = inst["accessories"]
            if accessories_data.get("slot1"):
                owned_skills_slot1.add(accessories_data["slot1"])
            if accessories_data.get("slot2"):
                owned_skills_slot2.add(accessories_data["slot2"])
            if accessories_data.get("slot3"):
                owned_skills_slot3.add(accessories_data["slot3"])
        # 3. accessory_1, accessory_2, accessory_3 개별 키 형태
        else:
            acc1 = inst.get("accessory_1")
            if acc1:
                skill_id = acc1["id"] if isinstance(acc1, dict) else acc1
                owned_skills_slot1.add(skill_id)
            acc2 = inst.get("accessory_2")
            if acc2:
                skill_id = acc2["id"] if isinstance(acc2, dict) else acc2
                owned_skills_slot2.add(skill_id)
            acc3 = inst.get("accessory_3")
            if acc3:
                skill_id = acc3["id"] if isinstance(acc3, dict) else acc3
                owned_skills_slot3.add(skill_id)
    
    # 스킬 옵션 생성 (등급 순서로 정렬)
    skill1_sorted = sorted(owned_skills_slot1, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill1_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill1_sorted]
    skill1_ids = [None] + skill1_sorted
    
    skill2_sorted = sorted(owned_skills_slot2, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill2_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill2_sorted]
    skill2_ids = [None] + skill2_sorted
    
    skill3_sorted = sorted(owned_skills_slot3, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill3_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill3_sorted]
    skill3_ids = [None] + skill3_sorted
    
    skill1_filter_idx = st.sidebar.selectbox("스킬 1 (회복)", range(len(skill1_options)), format_func=lambda x: skill1_options[x], key="list_skill1")
    skill1_filter = skill1_ids[skill1_filter_idx]
    
    skill2_filter_idx = st.sidebar.selectbox("스킬 2 (공격)", range(len(skill2_options)), format_func=lambda x: skill2_options[x], key="list_skill2")
    skill2_filter = skill2_ids[skill2_filter_idx]
    
    skill3_filter_idx = st.sidebar.selectbox("스킬 3 (보조)", range(len(skill3_options)), format_func=lambda x: skill3_options[x], key="list_skill3")
    skill3_filter = skill3_ids[skill3_filter_idx]
    
    # 정렬
    st.sidebar.markdown("---")
    sort_by = st.sidebar.selectbox("정렬", ["최신", "전투력", "HP", "ATK", "MS"])
    
    # 필터 변경 감지를 위한 해시 생성 (캐싱 최적화)
    current_filter_hash = hash((
        show_favorites_only, show_locked,
        main_color_filter, sub_color_filter, pattern_color_filter, pattern_filter,
        skill1_filter, skill2_filter, skill3_filter,
        sort_by, len(st.session_state.instances)
    ))
    
    # 필터 변경 시에만 재계산, 아니면 캐시 사용
    if ("list_filter_hash" not in st.session_state or 
        st.session_state.list_filter_hash != current_filter_hash or
        "list_filtered_cache" not in st.session_state):
        
        st.session_state.list_filter_hash = current_filter_hash
        
        # 필터링 (캐시 미스 시에만 실행)
        filtered = st.session_state.instances.copy()
        if show_favorites_only:
            filtered = [inst for inst in filtered if inst["is_favorite"]]
        if not show_locked:
            filtered = [inst for inst in filtered if not inst["is_locked"]]
        
        # 외형 필터 적용
        if main_color_filter:
            filtered = [inst for inst in filtered if inst["appearance"]["main_color"]["id"] == main_color_filter]
        if sub_color_filter:
            filtered = [inst for inst in filtered if inst["appearance"]["sub_color"]["id"] == sub_color_filter]
        if pattern_color_filter:
            filtered = [inst for inst in filtered if inst["appearance"]["pattern_color"]["id"] == pattern_color_filter]
        if pattern_filter:
            filtered = [inst for inst in filtered if inst["appearance"]["pattern"]["id"] == pattern_filter]
        
        # 스킬 필터 적용
        def get_skill_id(inst, slot_key, acc_key):
            # skills 또는 accessories 딕셔너리에서 확인
            skill_id = inst.get("skills", {}).get(slot_key) or inst.get("accessories", {}).get(slot_key)
            if skill_id:
                return skill_id
            # accessory_N 개별 키에서 확인
            acc = inst.get(acc_key)
            if acc:
                return acc["id"] if isinstance(acc, dict) else acc
            return None
        
        if skill1_filter:
            filtered = [inst for inst in filtered if get_skill_id(inst, "slot1", "accessory_1") == skill1_filter]
        if skill2_filter:
            filtered = [inst for inst in filtered if get_skill_id(inst, "slot2", "accessory_2") == skill2_filter]
        if skill3_filter:
            filtered = [inst for inst in filtered if get_skill_id(inst, "slot3", "accessory_3") == skill3_filter]
        
        # 정렬
        if sort_by == "최신":
            filtered.sort(key=lambda x: x["birth_time"], reverse=True)
        elif sort_by == "전투력":
            # power_score 필드 사용 (재계산 방지)
            filtered.sort(key=lambda x: x.get("power_score", calculate_power_score(x["stats"])), reverse=True)
        elif sort_by == "HP":
            filtered.sort(key=lambda x: x["stats"]["hp"], reverse=True)
        elif sort_by == "ATK":
            filtered.sort(key=lambda x: x["stats"]["atk"], reverse=True)
        elif sort_by == "MS":
            filtered.sort(key=lambda x: x["stats"]["ms"], reverse=True)
        
        # 캐시에 저장
        st.session_state.list_filtered_cache = filtered
    else:
        # 캐시 사용 (필터 미변경)
        filtered = st.session_state.list_filtered_cache
    
    # 페이지네이션 (성능 최적화)
    items_per_page = 20
    total_items = len(filtered)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    if "list_page" not in st.session_state:
        st.session_state.list_page = 1
    
    if total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 이전", disabled=st.session_state.list_page <= 1, use_container_width=True):
                st.session_state.list_page -= 1
                st.rerun()
        with col_info:
            st.markdown(f"<div style='text-align: center; padding: 0.375rem;'>페이지 {st.session_state.list_page}/{total_pages} ({total_items}개)</div>", unsafe_allow_html=True)
        with col_next:
            if st.button("다음 ▶", disabled=st.session_state.list_page >= total_pages, use_container_width=True):
                st.session_state.list_page += 1
                st.rerun()
    
    # 현재 페이지의 아이템만 표시
    start_idx = (st.session_state.list_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    page_items = filtered[start_idx:end_idx]
    
    # power_score 미리 계산 (반복 사용 방지)
    power_scores = {inst["id"]: inst.get("power_score", calculate_power_score(inst["stats"])) for inst in page_items}
    
    # 표시
    for inst in page_items:
        is_representative = st.session_state.get("representative_id") == inst["id"]
        is_favorite = inst.get("is_favorite", False)
        is_locked = inst.get("is_locked", False)
        power_score = power_scores[inst["id"]]
        
        title = f"{'👑 ' if is_representative else ''}{inst['name']}{'⭐' if is_favorite else ''}{'🔒' if is_locked else ''} - HP:{inst['stats']['hp']:,} ATK:{inst['stats']['atk']:,} MS:{inst['stats']['ms']:,} 💪{format_korean_number(power_score)}"
        
        with st.expander(title):
            # 버튼 먼저 표시 (상단)
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                if st.button("⭐ 즐겨찾기", key=f"fav_{inst['id']}"):
                    inst["is_favorite"] = not inst["is_favorite"]
                    save_game_data()
                    st.rerun()
            with col2:
                if st.button("🔒 잠금", key=f"lock_{inst['id']}"):
                    inst["is_locked"] = not inst["is_locked"]
                    save_game_data()
                    st.rerun()
            with col3:
                rep_label = "대표 해제" if is_representative else "👑 대표 설정"
                if st.button(rep_label, key=f"rep_{inst['id']}"):
                    if is_representative:
                        st.session_state.representative_id = None
                    else:
                        st.session_state.representative_id = inst["id"]
                    save_game_data()
                    st.rerun()
            with col4:
                new_name = st.text_input("이름 변경", value=inst["name"], key=f"name_{inst['id']}")
                if new_name != inst["name"]:
                    # 이름 안전성 검사
                    is_safe, reason = check_content_safety(new_name)
                    if not is_safe:
                        st.error(f"❌ {reason}")
                    else:
                        inst["name"] = new_name
                        save_game_data()
                        st.success("✅ 이름이 변경되었습니다!")
                        time.sleep(0.5)
                        st.rerun()
            with col5:
                if not inst["is_locked"]:
                    if st.button("🗑️ 삭제", key=f"delete_{inst['id']}"):
                        # 대표 유닛이면 대표 해제
                        if is_representative:
                            st.session_state.representative_id = None
                        st.session_state.instances.remove(inst)
                        save_game_data()
                        st.success("개체가 삭제되었습니다!")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    st.button("🗑️ 삭제", key=f"delete_{inst['id']}", disabled=True, help="잠금된 개체는 삭제할 수 없습니다")
            
            st.markdown("---")
            
            # 개체 카드 표시 (간결 모드)
            display_instance_card(inst, show_compact=True)

def page_bulk_delete():
    """일괄 삭제 화면"""
    st.title("🗑️ 일괄 삭제")
    
    # 선택 상태 초기화
    if "selected_for_delete" not in st.session_state:
        st.session_state.selected_for_delete = set()
    
    # 삭제 가능한 개체 필터링 (잠금되지 않은 개체만)
    deletable_instances = [inst for inst in st.session_state.instances if not inst.get("is_locked", False)]
    
    if not deletable_instances:
        st.info("삭제 가능한 개체가 없습니다. (잠금된 개체는 삭제할 수 없습니다)")
        if st.button("◀ 개체 목록으로", use_container_width=True):
            st.session_state.page = "list"
            st.rerun()
        return
    
    # 필터 & 정렬
    st.sidebar.title("필터 & 정렬")
    show_favorites_only = st.sidebar.checkbox("즐겨찾기만", key="bulk_delete_favorites")
    
    # 외형 필터
    st.sidebar.markdown("---")
    st.sidebar.markdown("**외형 필터**")
    
    # 삭제 가능한 개체들의 외형 속성 수집
    owned_main_colors = set()
    owned_sub_colors = set()
    owned_pattern_colors = set()
    owned_patterns = set()
    
    for inst in deletable_instances:
        owned_main_colors.add(inst["appearance"]["main_color"]["id"])
        owned_sub_colors.add(inst["appearance"]["sub_color"]["id"])
        owned_pattern_colors.add(inst["appearance"]["pattern_color"]["id"])
        owned_patterns.add(inst["appearance"]["pattern"]["id"])
    
    # 등급 순서 정의
    grade_order = {"Normal": 0, "Rare": 1, "Epic": 2, "Unique": 3, "Legendary": 4, "Mystic": 5}
    
    # 색상 옵션 생성 (등급 순서로 정렬)
    main_color_sorted = sorted(owned_main_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    main_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in main_color_sorted]
    main_color_ids = [None] + main_color_sorted
    
    sub_color_sorted = sorted(owned_sub_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    sub_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in sub_color_sorted]
    sub_color_ids = [None] + sub_color_sorted
    
    pattern_color_sorted = sorted(owned_pattern_colors, key=lambda x: (grade_order.get(COLOR_MASTER[x]['grade'], 99), x))
    pattern_color_options = ["전체"] + [f"{COLOR_MASTER[cid]['name']} ({COLOR_MASTER[cid]['grade']})" for cid in pattern_color_sorted]
    pattern_color_ids = [None] + pattern_color_sorted
    
    # 패턴 옵션 생성 (등급 순서로 정렬)
    pattern_sorted = sorted(owned_patterns, key=lambda x: (grade_order.get(PATTERN_MASTER[x]['grade'], 99), x))
    pattern_options = ["전체"] + [f"{PATTERN_MASTER[pid]['layout']} ({PATTERN_MASTER[pid]['grade']})" for pid in pattern_sorted]
    pattern_ids = [None] + pattern_sorted
    
    main_color_filter_idx = st.sidebar.selectbox("메인 색상", range(len(main_color_options)), format_func=lambda x: main_color_options[x], key="bulk_main_color")
    main_color_filter = main_color_ids[main_color_filter_idx]
    
    sub_color_filter_idx = st.sidebar.selectbox("서브 색상", range(len(sub_color_options)), format_func=lambda x: sub_color_options[x], key="bulk_sub_color")
    sub_color_filter = sub_color_ids[sub_color_filter_idx]
    
    pattern_color_filter_idx = st.sidebar.selectbox("패턴 색상", range(len(pattern_color_options)), format_func=lambda x: pattern_color_options[x], key="bulk_pattern_color")
    pattern_color_filter = pattern_color_ids[pattern_color_filter_idx]
    
    pattern_filter_idx = st.sidebar.selectbox("패턴", range(len(pattern_options)), format_func=lambda x: pattern_options[x], key="bulk_pattern")
    pattern_filter = pattern_ids[pattern_filter_idx]
    
    # 스킬 필터
    st.sidebar.markdown("---")
    st.sidebar.markdown("**스킬 필터**")
    
    # 보유한 스킬 수집 (슬롯별)
    owned_skills_slot1 = set()
    owned_skills_slot2 = set()
    owned_skills_slot3 = set()
    
    for inst in deletable_instances:
        # 여러 데이터 형식 지원
        # 1. skills 딕셔너리 형태
        skills_data = inst.get("skills")
        if skills_data:
            if skills_data.get("slot1"):
                owned_skills_slot1.add(skills_data["slot1"])
            if skills_data.get("slot2"):
                owned_skills_slot2.add(skills_data["slot2"])
            if skills_data.get("slot3"):
                owned_skills_slot3.add(skills_data["slot3"])
        # 2. accessories 딕셔너리 형태
        elif inst.get("accessories"):
            accessories_data = inst["accessories"]
            if accessories_data.get("slot1"):
                owned_skills_slot1.add(accessories_data["slot1"])
            if accessories_data.get("slot2"):
                owned_skills_slot2.add(accessories_data["slot2"])
            if accessories_data.get("slot3"):
                owned_skills_slot3.add(accessories_data["slot3"])
        # 3. accessory_1, accessory_2, accessory_3 개별 키 형태
        else:
            acc1 = inst.get("accessory_1")
            if acc1:
                skill_id = acc1["id"] if isinstance(acc1, dict) else acc1
                owned_skills_slot1.add(skill_id)
            acc2 = inst.get("accessory_2")
            if acc2:
                skill_id = acc2["id"] if isinstance(acc2, dict) else acc2
                owned_skills_slot2.add(skill_id)
            acc3 = inst.get("accessory_3")
            if acc3:
                skill_id = acc3["id"] if isinstance(acc3, dict) else acc3
                owned_skills_slot3.add(skill_id)
    
    # 스킬 옵션 생성 (등급 순서로 정렬)
    skill1_sorted = sorted(owned_skills_slot1, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill1_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill1_sorted]
    skill1_ids = [None] + skill1_sorted
    
    skill2_sorted = sorted(owned_skills_slot2, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill2_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill2_sorted]
    skill2_ids = [None] + skill2_sorted
    
    skill3_sorted = sorted(owned_skills_slot3, key=lambda x: (grade_order.get(SKILL_MASTER[x]['grade'], 99), x))
    skill3_options = ["전체"] + [f"{SKILL_MASTER[sid]['name']} ({SKILL_MASTER[sid]['grade']})" for sid in skill3_sorted]
    skill3_ids = [None] + skill3_sorted
    
    skill1_filter_idx = st.sidebar.selectbox("스킬 1 (회복)", range(len(skill1_options)), format_func=lambda x: skill1_options[x], key="bulk_skill1")
    skill1_filter = skill1_ids[skill1_filter_idx]
    
    skill2_filter_idx = st.sidebar.selectbox("스킬 2 (공격)", range(len(skill2_options)), format_func=lambda x: skill2_options[x], key="bulk_skill2")
    skill2_filter = skill2_ids[skill2_filter_idx]
    
    skill3_filter_idx = st.sidebar.selectbox("스킬 3 (보조)", range(len(skill3_options)), format_func=lambda x: skill3_options[x], key="bulk_skill3")
    skill3_filter = skill3_ids[skill3_filter_idx]
    
    st.sidebar.markdown("---")
    sort_by = st.sidebar.selectbox("정렬", ["최신", "전투력", "HP", "ATK", "MS"], key="bulk_delete_sort")
    
    # 필터링
    filtered = deletable_instances.copy()
    if show_favorites_only:
        filtered = [inst for inst in filtered if inst.get("is_favorite", False)]
    
    # 외형 필터 적용
    if main_color_filter:
        filtered = [inst for inst in filtered if inst["appearance"]["main_color"]["id"] == main_color_filter]
    if sub_color_filter:
        filtered = [inst for inst in filtered if inst["appearance"]["sub_color"]["id"] == sub_color_filter]
    if pattern_color_filter:
        filtered = [inst for inst in filtered if inst["appearance"]["pattern_color"]["id"] == pattern_color_filter]
    if pattern_filter:
        filtered = [inst for inst in filtered if inst["appearance"]["pattern"]["id"] == pattern_filter]
    
    # 스킬 필터 적용
    def get_skill_id_bulk(inst, slot_key, acc_key):
        # skills 또는 accessories 딕셔너리에서 확인
        skill_id = inst.get("skills", {}).get(slot_key) or inst.get("accessories", {}).get(slot_key)
        if skill_id:
            return skill_id
        # accessory_N 개별 키에서 확인
        acc = inst.get(acc_key)
        if acc:
            return acc["id"] if isinstance(acc, dict) else acc
        return None
    
    if skill1_filter:
        filtered = [inst for inst in filtered if get_skill_id_bulk(inst, "slot1", "accessory_1") == skill1_filter]
    if skill2_filter:
        filtered = [inst for inst in filtered if get_skill_id_bulk(inst, "slot2", "accessory_2") == skill2_filter]
    if skill3_filter:
        filtered = [inst for inst in filtered if get_skill_id_bulk(inst, "slot3", "accessory_3") == skill3_filter]
    
    # 정렬
    if sort_by == "최신":
        filtered.sort(key=lambda x: x["birth_time"], reverse=True)
    elif sort_by == "전투력":
        filtered.sort(key=lambda x: x.get("power_score", calculate_power_score(x["stats"])), reverse=True)
    elif sort_by == "HP":
        filtered.sort(key=lambda x: x["stats"]["hp"], reverse=True)
    elif sort_by == "ATK":
        filtered.sort(key=lambda x: x["stats"]["atk"], reverse=True)
    elif sort_by == "MS":
        filtered.sort(key=lambda x: x["stats"]["ms"], reverse=True)
    
    st.markdown(f"**삭제 가능한 개체: {len(filtered)}개** (전체: {len(deletable_instances)}개)")
    st.warning("⚠️ 잠금된 개체는 표시되지 않습니다. 삭제를 원하면 먼저 잠금을 해제하세요.")
    st.markdown("---")
    
    # 상단 제어 버튼
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("✅ 전체 선택", use_container_width=True):
            st.session_state.selected_for_delete = {inst["id"] for inst in filtered}
            st.rerun()
    
    with col2:
        if st.button("❌ 전체 해제", use_container_width=True):
            st.session_state.selected_for_delete.clear()
            st.rerun()
    
    with col3:
        selected_count = len(st.session_state.selected_for_delete)
        if selected_count > 0:
            if st.button(f"🗑️ 삭제 ({selected_count}개)", type="primary", use_container_width=True):
                # 삭제 실행
                to_delete = [inst for inst in filtered if inst["id"] in st.session_state.selected_for_delete]
                
                for inst in to_delete:
                    # 대표 유닛이면 대표 해제
                    if st.session_state.get("representative_id") == inst["id"]:
                        st.session_state.representative_id = None
                    st.session_state.instances.remove(inst)
                
                st.session_state.selected_for_delete.clear()
                save_game_data()
                st.success(f"✅ {len(to_delete)}개 개체가 삭제되었습니다!")
                time.sleep(1)
                st.rerun()
        else:
            st.button("🗑️ 삭제 (0개)", disabled=True, use_container_width=True)
    
    with col4:
        if st.button("◀ 개체 목록으로", use_container_width=True):
            st.session_state.selected_for_delete.clear()
            st.session_state.page = "list"
            st.rerun()
    
    st.markdown("---")
    
    # 개체 목록 (필터링 및 정렬 적용)
    for inst in filtered:
        is_selected = inst["id"] in st.session_state.selected_for_delete
        is_favorite = inst.get("is_favorite", False)
        is_representative = st.session_state.get("representative_id") == inst["id"]
        
        col_check, col_info = st.columns([1, 9])
        
        with col_check:
            # key에 선택 상태를 포함시켜 강제로 재렌더링
            checkbox_key = f"delete_{inst['id']}_{is_selected}"
            if st.checkbox("선택", value=is_selected, key=checkbox_key, label_visibility="collapsed"):
                st.session_state.selected_for_delete.add(inst["id"])
            else:
                st.session_state.selected_for_delete.discard(inst["id"])
        
        with col_info:
            power_score = calculate_power_score(inst["stats"])
            title = f"{'👑 ' if is_representative else ''}{inst['name']}{'⭐' if is_favorite else ''}"
            stats = f"HP:{inst['stats']['hp']:,} ATK:{inst['stats']['atk']:,} MS:{inst['stats']['ms']:,} 💪{format_korean_number(power_score)}"
            
            with st.expander(f"{title} - {stats}:"):
                display_instance_card(inst, show_details=True)

def page_random_box():
    """랜덤 박스 화면"""
    st.title("🎁 랜덤 박스")
    
    st.markdown("---")
    
    # 개체 수 제한 체크
    max_instances = st.session_state.get("max_instances", 200)
    instance_count = len(st.session_state.instances)
    if instance_count >= max_instances:
        st.error(f"⚠️ 개체 목록이 최대 {max_instances}개를 초과했습니다. 일부 개체를 삭제해주세요.")
        st.info("🗑️ 개체 목록 페이지에서 일괄 삭제 기능을 사용하세요.")
        can_use = False
    else:
        st.info(f"📊 현재 개체 수: {instance_count}/{max_instances}")
    
    # 사용 가능 여부 확인
    can_use_box, message = can_use_random_box()
    if instance_count < 200:
        can_use = can_use_box
    
    st.markdown("### 📦 랜덤 박스 사용")
    st.markdown("""
    **랜덤 박스 규칙:**
    - 하루에 1번만 사용 가능합니다.
    - 기본 능력치(HP 10, ATK 1, MS 1)를 가진 개체를 획득합니다.
    - 메인 컬러, 서브 컬러, 패턴 컬러, 패턴 중 **1가지만** 특별한 값을 가집니다.
    - 각 타입이 선택될 확률은 25%로 동일합니다.
    - 선택된 타입의 등급은 가중치에 따라 결정됩니다.
    """)
    
    st.markdown("---")
    
    # 상태 표시
    max_instances = st.session_state.get("max_instances", 200)
    if instance_count >= max_instances:
        pass  # 이미 위에서 에러 표시
    elif can_use:
        st.success(f"✅ {message}")
    else:
        st.warning(f"⏰ {message}")
    
    # 랜덤 박스 사용 버튼
    if st.button("🎁 랜덤 박스 열기", use_container_width=True, disabled=not can_use):
        # 개체 생성
        new_instance = create_random_box_instance()
        st.session_state.instances.append(new_instance)
        
        # 사용 시간 저장
        st.session_state.last_random_box_time = datetime.now().isoformat()
        save_game_data()
        
        # 결과 표시
        st.success("🎉 새로운 개체를 획득했습니다!")
        st.balloons()
        
        with st.container():
            st.markdown("### 획득한 개체")
            display_instance_card(new_instance, show_details=True)
        
        time.sleep(2)
        st.rerun()
    
    # 최근 획득 이력
    st.markdown("---")
    st.markdown("### 📜 최근 랜덤 박스 획득 개체")
    
    random_box_instances = [inst for inst in st.session_state.instances if inst["created_by"] == "RandomBox"]
    if random_box_instances:
        # 최신순 정렬
        random_box_instances.sort(key=lambda x: x["birth_time"], reverse=True)
        
        # 최근 5개만 표시
        for inst in random_box_instances[:5]:
            with st.expander(f"{inst['name']} - {inst['birth_time'][:19]}"):
                display_instance_card(inst, show_details=True)
    else:
        st.info("아직 랜덤 박스로 획득한 개체가 없습니다.")

def page_collection():
    """도감 화면"""
    st.title("📖 도감")
    
    if "collection" not in st.session_state:
        st.session_state.collection = {
            "colors": {"main": set(), "sub": set(), "pattern": set()},
            "patterns": set(),
            "accessories": set(),
            "skills": {"slot1": set(), "slot2": set(), "slot3": set()}
        }
    
    # 하위 호환성: 기존 데이터에 skills 키가 없으면 추가
    if "skills" not in st.session_state.collection:
        st.session_state.collection["skills"] = {"slot1": set(), "slot2": set(), "slot3": set()}
    
    # 도감 탭
    tab1, tab2, tab3 = st.tabs(["🎨 색상", "🖼️ 패턴", "⚔️ 스킬"])
    
    # 색상 도감
    with tab1:
        st.markdown("### 🎨 색상 도감")
        
        # 색상 타입별 서브 탭
        color_tab1, color_tab2, color_tab3 = st.tabs(["메인 색상", "서브 색상", "패턴 색상"])
        
        grades = ["Normal", "Rare", "Epic", "Unique", "Legendary", "Mystic"]
        
        # 메인 색상
        with color_tab1:
            for grade in grades:
                colors_in_grade = [(color_id, color_data) for color_id, color_data in COLOR_MASTER.items() if color_data["grade"] == grade]
                discovered = [c for c in colors_in_grade if c[0] in st.session_state.collection["colors"]["main"]]
                
                with st.expander(f"{grade} ({len(discovered)}/{len(colors_in_grade)})", expanded=(grade == "Normal")):
                    cols = st.columns(5)
                    for idx, (color_id, color) in enumerate(colors_in_grade):
                        col = cols[idx % 5]
                        with col:
                            if color_id in st.session_state.collection["colors"]["main"]:
                                # 획득한 색상
                                st.markdown(f"""
                                <div style="background-color: {color['hex']}; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #888;">
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown(f"**{color['name']}**", help=color['hex'])
                            else:
                                # 미획득 색상
                                st.markdown(f"""
                                <div style="background-color: #333; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #555;
                                            display: flex;
                                            align-items: center;
                                            justify-content: center;
                                            font-size: 30px;
                                            color: #666;">
                                    ?
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown("**???**")
        
        # 서브 색상
        with color_tab2:
            for grade in grades:
                colors_in_grade = [(color_id, color_data) for color_id, color_data in COLOR_MASTER.items() if color_data["grade"] == grade]
                discovered = [c for c in colors_in_grade if c[0] in st.session_state.collection["colors"]["sub"]]
                
                with st.expander(f"{grade} ({len(discovered)}/{len(colors_in_grade)})", expanded=(grade == "Normal")):
                    cols = st.columns(5)
                    for idx, (color_id, color) in enumerate(colors_in_grade):
                        col = cols[idx % 5]
                        with col:
                            if color_id in st.session_state.collection["colors"]["sub"]:
                                # 획득한 색상
                                st.markdown(f"""
                                <div style="background-color: {color['hex']}; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #888;">
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown(f"**{color['name']}**", help=color['hex'])
                            else:
                                # 미획득 색상
                                st.markdown(f"""
                                <div style="background-color: #333; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #555;
                                            display: flex;
                                            align-items: center;
                                            justify-content: center;
                                            font-size: 30px;
                                            color: #666;">
                                    ?
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown("**???**")
        
        # 패턴 색상
        with color_tab3:
            for grade in grades:
                colors_in_grade = [(color_id, color_data) for color_id, color_data in COLOR_MASTER.items() if color_data["grade"] == grade]
                discovered = [c for c in colors_in_grade if c[0] in st.session_state.collection["colors"]["pattern"]]
                
                with st.expander(f"{grade} ({len(discovered)}/{len(colors_in_grade)})", expanded=(grade == "Normal")):
                    cols = st.columns(5)
                    for idx, (color_id, color) in enumerate(colors_in_grade):
                        col = cols[idx % 5]
                        with col:
                            if color_id in st.session_state.collection["colors"]["pattern"]:
                                # 획득한 색상
                                st.markdown(f"""
                                <div style="background-color: {color['hex']}; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #888;">
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown(f"**{color['name']}**", help=color['hex'])
                            else:
                                # 미획득 색상
                                st.markdown(f"""
                                <div style="background-color: #333; 
                                            width: 100%; 
                                            height: 60px; 
                                            border-radius: 8px; 
                                            margin-bottom: 5px; 
                                            border: 2px solid #555;
                                            display: flex;
                                            align-items: center;
                                            justify-content: center;
                                            font-size: 30px;
                                            color: #666;">
                                    ?
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown("**???**")
    
    # 패턴 도감
    with tab2:
        st.markdown("### 🖼️ 패턴 도감")
        
        for grade in grades:
            patterns_in_grade = [(pattern_id, pattern_data) for pattern_id, pattern_data in PATTERN_MASTER.items() if pattern_data["grade"] == grade]
            discovered = [p for p in patterns_in_grade if p[0] in st.session_state.collection["patterns"]]
            
            with st.expander(f"{grade} ({len(discovered)}/{len(patterns_in_grade)})", expanded=(grade == "Normal")):
                cols = st.columns(4)
                for idx, (pattern_id, pattern) in enumerate(patterns_in_grade):
                    col = cols[idx % 4]
                    with col:
                        if pattern_id in st.session_state.collection["patterns"]:
                            # 획득한 패턴 (미리보기 SVG)
                            pattern_with_id = {"id": pattern_id, **pattern}
                            dummy_instance = {
                                "id": "preview",
                                "appearance": {
                                    "main_color": {"id": "normal01"},
                                    "sub_color": {"id": "normal02"},
                                    "pattern_color": {"id": "normal03"},
                                    "pattern": pattern_with_id
                                },
                                "accessory_1": None,
                                "accessory_2": None,
                                "accessory_3": None
                            }
                            svg = get_instance_svg(dummy_instance, size=80)
                            st.markdown(f'<div style="margin-bottom: 8px; text-align: center;">{svg}</div>', unsafe_allow_html=True)
                            st.markdown(f"<div style='text-align: center;'><strong>{pattern.get('name', pattern['layout'])}</strong></div>", unsafe_allow_html=True)
                        else:
                            # 미획득 패턴
                            st.markdown(f"""
                            <div style="background-color: #333; 
                                        width: 80px; 
                                        height: 80px; 
                                        border-radius: 8px; 
                                        margin: 0 auto 8px;
                                        border: 2px solid #555;
                                        display: flex;
                                        align-items: center;
                                        justify-content: center;
                                        font-size: 30px;
                                        color: #666;">
                                ?
                            </div>
                            <div style="text-align: center; margin-top: 5px;"><strong>???</strong></div>
                            """, unsafe_allow_html=True)
    
    # 스킬 도감
    with tab3:
        st.markdown("### ⚔️ 스킬 도감")
        
        # 스킬 슬롯별 서브 탭
        skill_tab1, skill_tab2, skill_tab3 = st.tabs(["스킬 1 (회복)", "스킬 2 (공격)", "스킬 3 (보조)"])
        
        # 스킬 1 (회복) - Slot 1
        with skill_tab1:
            for grade in grades:
                skills_in_grade = [(skill_id, skill_data) for skill_id, skill_data in SKILL_MASTER.items() 
                                   if skill_data["grade"] == grade and skill_data["slot"] == 1]
                discovered = [s for s in skills_in_grade if s[0] in st.session_state.collection["skills"]["slot1"]]
                
                if len(skills_in_grade) > 0:
                    with st.expander(f"{grade} ({len(discovered)}/{len(skills_in_grade)})", expanded=(grade == "Normal")):
                        cols = st.columns(4)
                        for idx, (skill_id, skill) in enumerate(skills_in_grade):
                            col = cols[idx % 4]
                            with col:
                                if skill_id in st.session_state.collection["skills"]["slot1"]:
                                    # 획득한 스킬
                                    st.markdown(f"**{skill['name']}**")
                                    cooldown = skill.get('cooldown', 0)
                                    st.caption(f"{skill.get('desc', '')} (쿨타임: {cooldown}턴)")
                                else:
                                    # 미획득 스킬
                                    st.markdown("**???**")
                                    st.caption("???")
        
        # 스킬 2 (공격) - Slot 2
        with skill_tab2:
            for grade in grades:
                skills_in_grade = [(skill_id, skill_data) for skill_id, skill_data in SKILL_MASTER.items() 
                                   if skill_data["grade"] == grade and skill_data["slot"] == 2]
                discovered = [s for s in skills_in_grade if s[0] in st.session_state.collection["skills"]["slot2"]]
                
                if len(skills_in_grade) > 0:
                    with st.expander(f"{grade} ({len(discovered)}/{len(skills_in_grade)})", expanded=(grade == "Normal")):
                        cols = st.columns(4)
                        for idx, (skill_id, skill) in enumerate(skills_in_grade):
                            col = cols[idx % 4]
                            with col:
                                if skill_id in st.session_state.collection["skills"]["slot2"]:
                                    # 획득한 스킬
                                    st.markdown(f"**{skill['name']}**")
                                    cooldown = skill.get('cooldown', 0)
                                    st.caption(f"{skill.get('desc', '')} (쿨타임: {cooldown}턴)")
                                else:
                                    # 미획득 스킬
                                    st.markdown("**???**")
                                    st.caption("???")
        
        # 스킬 3 (보조) - Slot 3
        with skill_tab3:
            for grade in grades:
                skills_in_grade = [(skill_id, skill_data) for skill_id, skill_data in SKILL_MASTER.items() 
                                   if skill_data["grade"] == grade and skill_data["slot"] == 3]
                discovered = [s for s in skills_in_grade if s[0] in st.session_state.collection["skills"]["slot3"]]
                
                if len(skills_in_grade) > 0:
                    with st.expander(f"{grade} ({len(discovered)}/{len(skills_in_grade)})", expanded=(grade == "Normal")):
                        cols = st.columns(4)
                        for idx, (skill_id, skill) in enumerate(skills_in_grade):
                            col = cols[idx % 4]
                            with col:
                                if skill_id in st.session_state.collection["skills"]["slot3"]:
                                    # 획득한 스킬
                                    st.markdown(f"**{skill['name']}**")
                                    cooldown = skill.get('cooldown', 0)
                                    st.caption(f"{skill.get('desc', '')} (쿨타임: {cooldown}턴)")
                                else:
                                    # 미획득 스킬
                                    st.markdown("**???**")
                                    st.caption("???")
    
    st.markdown("---")
    
    # 전체 진행도
    total_colors = len(COLOR_MASTER) * 3  # 메인/서브/패턴 색상 각각
    total_patterns = len(PATTERN_MASTER)
    
    # 슬롯별 스킬 개수 계산
    total_skills_slot1 = len([s for s in SKILL_MASTER.values() if s["slot"] == 1])
    total_skills_slot2 = len([s for s in SKILL_MASTER.values() if s["slot"] == 2])
    total_skills_slot3 = len([s for s in SKILL_MASTER.values() if s["slot"] == 3])
    total_skills = total_skills_slot1 + total_skills_slot2 + total_skills_slot3
    
    total_items = total_colors + total_patterns + total_skills
    
    # 중복 제거하여 실제 발견한 색상 수 계산
    all_discovered_colors = st.session_state.collection["colors"]["main"] | st.session_state.collection["colors"]["sub"] | st.session_state.collection["colors"]["pattern"]
    discovered_colors_main = len(st.session_state.collection["colors"]["main"])
    discovered_colors_sub = len(st.session_state.collection["colors"]["sub"])
    discovered_colors_pattern = len(st.session_state.collection["colors"]["pattern"])
    discovered_colors = discovered_colors_main + discovered_colors_sub + discovered_colors_pattern
    
    discovered_patterns = len(st.session_state.collection["patterns"])
    
    # 슬롯별 발견한 스킬 수 계산
    discovered_skills_slot1 = len(st.session_state.collection["skills"]["slot1"])
    discovered_skills_slot2 = len(st.session_state.collection["skills"]["slot2"])
    discovered_skills_slot3 = len(st.session_state.collection["skills"]["slot3"])
    discovered_skills = discovered_skills_slot1 + discovered_skills_slot2 + discovered_skills_slot3
    
    discovered_total = discovered_colors + discovered_patterns + discovered_skills
    
    st.markdown("### 📊 전체 진행도")
    st.progress(discovered_total / total_items if total_items > 0 else 0)
    st.markdown(f"**{discovered_total}/{total_items}** ({discovered_total * 100 // total_items if total_items > 0 else 0}%)")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("색상 (메인)", f"{discovered_colors_main}/{len(COLOR_MASTER)}")
    with col2:
        st.metric("색상 (서브)", f"{discovered_colors_sub}/{len(COLOR_MASTER)}")
    with col3:
        st.metric("색상 (패턴)", f"{discovered_colors_pattern}/{len(COLOR_MASTER)}")
    with col4:
        st.metric("패턴", f"{discovered_patterns}/{total_patterns}")
    
    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("스킬 1 (회복)", f"{discovered_skills_slot1}/{total_skills_slot1}")
    with col6:
        st.metric("스킬 2 (공격)", f"{discovered_skills_slot2}/{total_skills_slot2}")
    with col7:
        st.metric("스킬 3 (보조)", f"{discovered_skills_slot3}/{total_skills_slot3}")

def page_ranking():
    """랭킹 화면"""
    st.title("🏆 랭킹")
    
    # 랭킹 데이터 수집
    representatives = get_all_users_representatives()
    
    if not representatives:
        st.info("📊 아직 랭킹에 등록된 대표 유닛이 없습니다.")
        st.markdown("대표 유닛을 설정하면 랭킹에 참여할 수 있습니다!")
        return
    
    # 헤더 정보
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🎯 총 플레이어", f"{len(representatives)}명")
    with col2:
        avg_power = sum(r['power_score'] for r in representatives) / len(representatives)
        st.metric("📊 평균 전투력", f"{format_korean_number(int(avg_power))}")
    with col3:
        max_power = representatives[0]['power_score'] if representatives else 0
        st.metric("👑 1위 전투력", f"{format_korean_number(max_power)}")
    
    st.caption("💡 전투력 = HP + ATK×10 + MS×5")
    st.markdown("---")
    
    # 내 랭킹 표시
    my_username = st.session_state.username
    my_rank_info = next(((i+1, rep) for i, rep in enumerate(representatives) if rep["username"] == my_username), None)
    
    if my_rank_info:
        my_rank, my_rep = my_rank_info
        medal = "🥇" if my_rank == 1 else "🥈" if my_rank == 2 else "🥉" if my_rank == 3 else "🏅"
        
        st.markdown(f"### {medal} 내 랭킹: **{my_rank}위**")
        
        # 내 정보 간결하게
        col1, col2, col3 = st.columns([1, 3, 2])
        with col1:
            svg = get_instance_svg(my_rep["instance"], size=80)
            st.markdown(svg, unsafe_allow_html=True)
        with col2:
            st.markdown(f"**{my_rep['instance']['name']}**")
            st.markdown(f"💪 **{format_korean_number(my_rep['power_score'])}** | HP {my_rep['instance']['stats']['hp']:,} | ATK {my_rep['instance']['stats']['atk']:,} | MS {my_rep['instance']['stats']['ms']:,}")
        with col3:
            with st.expander("⚔️ 스킬 보기"):
                for i in range(1, 4):
                    acc_key = f"accessory_{i}"
                    if my_rep['instance'].get(acc_key):
                        skill_id = my_rep['instance'][acc_key]["id"]
                        if skill_id in SKILL_MASTER:
                            skill = SKILL_MASTER[skill_id]
                            st.markdown(f"**슬롯 {i}**: {skill['name']}")
                            st.caption(skill['desc'])
                        else:
                            st.markdown(f"슬롯 {i}: 없음")
                    else:
                        st.markdown(f"슬롯 {i}: 없음")
        st.markdown("---")
    else:
        st.warning("⚠️ 대표 유닛을 설정하여 랭킹에 참여하세요!")
        if st.button("📋 개체 목록으로 이동", use_container_width=True):
            st.session_state.page = "list"
            st.rerun()
        st.markdown("---")
    
    # 상위 3명 별도 표시
    st.markdown("### 🏅 TOP 3")
    top3 = representatives[:3]
    
    if len(top3) > 0:
        # 실제 있는 만큼만 컬럼 생성
        cols = st.columns(len(top3))
        medals = ["🥇", "🥈", "🥉"]
        border_colors = ['#ffd700', '#c0c0c0', '#cd7f32']
        
        for idx, (col, rep) in enumerate(zip(cols, top3)):
            with col:
                medal = medals[idx]
                is_me = rep["username"] == my_username
                
                st.markdown(f"""
                <div style="padding: 15px; border-radius: 10px; border: 2px solid {border_colors[idx]}; text-align: center; background: {'rgba(255, 215, 0, 0.1)' if idx==0 else 'transparent'};">
                    <div style="font-size: 2em;">{medal}</div>
                    <div style="font-weight: bold; margin: 5px 0;">{rep['username']}</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">💪 {format_korean_number(rep['power_score'])}</div>
                </div>
                """, unsafe_allow_html=True)
                
                svg = get_instance_svg(rep["instance"], size=120)
                st.markdown(f'<div style="text-align: center;">{svg}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="text-align: center; font-weight: bold; margin-top: 10px;">{rep["instance"]["name"]}</div>', unsafe_allow_html=True)
                
                with st.expander("상세 정보"):
                    st.markdown(f"HP: {rep['instance']['stats']['hp']:,}")
                    st.markdown(f"ATK: {rep['instance']['stats']['atk']:,}")
                    st.markdown(f"MS: {rep['instance']['stats']['ms']:,}")
                    
                    st.markdown("**⚔️ 스킬:**")
                    for i in range(1, 4):
                        acc_key = f"accessory_{i}"
                        if rep['instance'].get(acc_key) and rep['instance'][acc_key]["id"] in SKILL_MASTER:
                            skill = SKILL_MASTER[rep['instance'][acc_key]["id"]]
                            st.markdown(f"• **{skill['name']}** ({skill['grade']})")
                            st.caption(skill['desc'])
                        else:
                            st.markdown(f"• 슬롯 {i}: 없음")
    else:
        st.info("아직 TOP 3가 없습니다. 대표 유닛을 설정해주세요!")
    
    st.markdown("---")
    
    # 전체 랭킹 (간결하게, 20위까지만)
    st.markdown("### 📊 전체 랭킹 (TOP 20)")
    
    # TOP 3 제외한 나머지 표시
    remaining = [rep for idx, rep in enumerate(representatives[:20]) if idx >= 3]
    
    if remaining:
        for idx, rep in enumerate(remaining):
            rank = idx + 4  # 4위부터 시작
            is_me = rep["username"] == my_username
            
            col1, col2, col3, col4 = st.columns([0.5, 1, 2, 1.5])
            
            with col1:
                st.markdown(f"**{rank}**")
            
            with col2:
                svg = get_instance_svg(rep["instance"], size=50)
                st.markdown(svg, unsafe_allow_html=True)
            
            with col3:
                name_style = "color: #ff6b6b; font-weight: bold;" if is_me else ""
                st.markdown(f"<div style='{name_style}'>{rep['username']}</div>", unsafe_allow_html=True)
                st.caption(f"{rep['instance']['name']}")
            
            with col4:
                st.markdown(f"💪 **{format_korean_number(rep['power_score'])}**")
                with st.expander("상세"):
                    st.markdown(f"HP: {rep['instance']['stats']['hp']:,}")
                    st.markdown(f"ATK: {rep['instance']['stats']['atk']:,}")
                    st.markdown(f"MS: {rep['instance']['stats']['ms']:,}")
                    
                    st.markdown("**⚔️ 스킬:**")
                    for i in range(1, 4):
                        acc_key = f"accessory_{i}"
                        if rep['instance'].get(acc_key) and rep['instance'][acc_key]["id"] in SKILL_MASTER:
                            skill = SKILL_MASTER[rep['instance'][acc_key]["id"]]
                            st.markdown(f"• **{skill['name']}** ({skill['grade']})")
                            st.caption(skill['desc'])
                        else:
                            st.markdown(f"• 슬롯 {i}: 없음")
            
            if idx < len(remaining) - 1:  # 마지막이 아니면 구분선
                st.markdown("<hr style='margin: 5px 0; opacity: 0.3;'>", unsafe_allow_html=True)
    elif len(representatives) <= 3:
        st.info("4위 이하 랭킹이 없습니다.")

def generate_stage_enemy(stage: int) -> Dict:
    """스테이지별 적 생성 (스킬 고정)"""
    # 스테이지별 시드 고정 (스킬이 항상 같게)
    random.seed(stage * 12345)
    
    # 기본 스탯 (스테이지에 비례)
    base_hp = 100 + (stage - 1) * 50
    base_atk = 10 + (stage - 1) * 5
    base_ms = 10 + (stage - 1) * 3  # MS 기본값 증가 (5→10), 증가량 증가 (2→3)
    
    # 스테이지별 스탯 증가 (모두 1.2배씩)
    hp = int(base_hp * (1.2 ** (stage - 1)))
    atk = int(base_atk * (1.2 ** (stage - 1)))
    ms = int(base_ms * (1.2 ** (stage - 1)))  # MS도 1.2배로 통일
    
    # 로그 스케일 기반 스킬 장착 (무한 스테이지 대응)
    import math
    
    # 스테이지 로그 값 계산 (log10 사용)
    log_stage = math.log10(max(stage, 1))
    
    # 스킬 개수 결정 (단계별 구간)
    if stage <= 20:
        skill_count = 0
    elif stage <= 40:
        skill_count = 1
    elif stage <= 80:
        skill_count = 2
    else:
        skill_count = 3
    
    # 등급별 가중치 계산 (로그 스케일로 점진 상승)
    # log_stage 0 → Normal 100%
    # log_stage 1 → Normal 70%, Rare 25%, Epic 5%
    # log_stage 2 → Rare 40%, Epic 35%, Unique 20%, Legendary 5%
    # log_stage 3+ → Epic 20%, Unique 30%, Legendary 35%, Mystic 15%
    
    log_factor = min(log_stage / 3.0, 1.0)  # 0.0 ~ 1.0
    
    normal_weight = max(100 - log_stage * 50, 0)
    rare_weight = max(30 * log_stage - 10, 0)
    epic_weight = max(25 * log_stage, 5)
    unique_weight = max(30 * log_stage - 30, 0)
    legendary_weight = max(25 * log_stage - 40, 0)
    mystic_weight = max(15 * log_stage - 40, 0)
    
    # 가중치 기반 등급 선택 함수
    def get_grade_by_weight():
        weights = {
            "Normal": normal_weight,
            "Rare": rare_weight,
            "Epic": epic_weight,
            "Unique": unique_weight,
            "Legendary": legendary_weight,
            "Mystic": mystic_weight
        }
        weights = {k: v for k, v in weights.items() if v > 0}
        if not weights:
            return "Normal"
        grades_list = list(weights.keys())
        weight_list = list(weights.values())
        return random.choices(grades_list, weights=weight_list, k=1)[0]
    
    # 스킬 장착
    acc1 = None
    acc2 = None
    acc3 = None
    
    if skill_count >= 1:
        acc1_grade = get_grade_by_weight()
        acc1_candidates = get_skill_ids_by_grade_and_slot(acc1_grade, 1)
        acc1 = {"grade": acc1_grade, "id": random.choice(acc1_candidates)} if acc1_candidates else None
    
    if skill_count >= 2:
        acc2_grade = get_grade_by_weight()
        acc2_candidates = get_skill_ids_by_grade_and_slot(acc2_grade, 2)
        acc2 = {"grade": acc2_grade, "id": random.choice(acc2_candidates)} if acc2_candidates else None
    
    if skill_count >= 3:
        acc3_grade = get_grade_by_weight()
        acc3_candidates = get_skill_ids_by_grade_and_slot(acc3_grade, 3)
        acc3 = {"grade": acc3_grade, "id": random.choice(acc3_candidates)} if acc3_candidates else None
    
    # 시드 리셋 (다른 랜덤 작업에 영향 없도록)
    random.seed()
    
    # 적 생성
    enemy = create_instance(
        hp=hp,
        atk=atk,
        ms=ms,
        main_color={"grade": "Normal", "id": "normal04"},
        sub_color={"grade": "Normal", "id": "normal05"},
        pattern_color={"grade": "Normal", "id": "normal06"},
        pattern={"grade": "Normal", "id": "normal01"},
        accessory_1=acc1,
        accessory_2=acc2,
        accessory_3=acc3,
        name=f"Stage {stage} Boss",
        created_by="Battle"
    )
    
    return enemy

def generate_battle_reward(boss_power: int, stage: int) -> Dict:
    """전투 승리 보상 개체 생성 (보스 전투력의 1.1배)"""
    target_power = int(boss_power * 1.1)
    
    # 전투력 = HP + ATK×10 + MS×5
    # HP는 10단위, ATK:MS ≈ 2:1 비율
    # target_power = HP + ATK×10 + MS×5
    # HP + ATK×10 + (ATK/2)×5 = target_power
    # HP + ATK×12.5 = target_power
    # ATK = (target_power - HP) / 12.5
    
    # HP를 전투력의 30~40%로 설정 (10단위)
    hp = int((target_power * 0.35) / 10) * 10
    
    # 나머지를 ATK와 MS로 분배
    remaining = target_power - hp
    atk = int(remaining / 12.5)
    ms = int(atk / 2)
    
    # 미세 조정 (정확한 전투력 맞추기)
    actual_power = hp + atk * 10 + ms * 5
    if actual_power < target_power:
        diff = target_power - actual_power
        if diff >= 10:
            atk += 1
        elif diff >= 5:
            ms += 1
    
    # 스테이지별 등급 확률 (점진적 증가, 200+ 스테이지 대응)
    # 기본 확률 설정
    stage_factor = min(stage / 200.0, 1.0)  # 0.0 ~ 1.0 (200 스테이지에서 1.0)
    
    # 등급별 기본 가중치 계산
    normal_weight = max(100 - stage * 0.4, 10)  # 100 → 10 (느리게 감소)
    rare_weight = 30 + stage * 0.3  # 30 → 90 (스테이지 200에서)
    epic_weight = 10 + stage * 0.25  # 10 → 60
    unique_weight = max(stage * 0.2 - 10, 0)  # 50 스테이지부터 서서히
    legendary_weight = max(stage * 0.1 - 20, 0)  # 200 스테이지부터 서서히
    mystic_weight = max(stage * 0.05 - 30, 0)  # 600+ 스테이지부터 (극후반)
    
    # 스킬용 등급 풀 생성 (가중치 기반)
    def get_grade_by_weight():
        weights = {
            "Normal": normal_weight,
            "Rare": rare_weight,
            "Epic": epic_weight,
            "Unique": unique_weight,
            "Legendary": legendary_weight,
            "Mystic": mystic_weight
        }
        # 0 이하 제거
        weights = {k: v for k, v in weights.items() if v > 0}
        grades = list(weights.keys())
        weight_list = list(weights.values())
        return random.choices(grades, weights=weight_list, k=1)[0]
    
    # 외형용 등급 (Normal 확률 3배 증가)
    def get_appearance_grade():
        weights = {
            "Normal": normal_weight * 3,  # Normal 확률 3배
            "Rare": rare_weight,
            "Epic": epic_weight,
            "Unique": unique_weight,
            "Legendary": legendary_weight,
            "Mystic": mystic_weight
        }
        # 0 이하 제거
        weights = {k: v for k, v in weights.items() if v > 0}
        grades = list(weights.keys())
        weight_list = list(weights.values())
        return random.choices(grades, weights=weight_list, k=1)[0]
    
    # 랜덤 외형 생성 (50% 확률로 normal01 고정)
    def get_appearance():
        if random.random() < 0.5:  # 50% 확률로 normal01
            return {"grade": "Normal", "id": "normal01"}
        else:  # 나머지 50%는 가중치 기반
            grade = get_appearance_grade()
            items = [i for i, data in COLOR_MASTER.items() if data["grade"] == grade]
            return {"grade": grade, "id": random.choice(items)}
    
    def get_pattern():
        if random.random() < 0.5:  # 50% 확률로 normal01
            return {"grade": "Normal", "id": "normal01"}
        else:  # 나머지 50%는 가중치 기반
            grade = get_appearance_grade()
            items = [i for i, data in PATTERN_MASTER.items() if data["grade"] == grade]
            return {"grade": grade, "id": random.choice(items)}
    
    main_color = get_appearance()
    sub_color = get_appearance()
    pattern_color = get_appearance()
    pattern = get_pattern()
    
    # 랜덤 스킬 (50% 확률로 스킬 없음)
    def maybe_skill(slot):
        if random.random() < 0.5:  # 50% 확률로 없음
            return None
        grade = get_grade_by_weight()
        candidates = get_skill_ids_by_grade_and_slot(grade, slot)
        if candidates:
            return {"grade": grade, "id": random.choice(candidates)}
        return None
    
    acc1 = maybe_skill(1)
    acc2 = maybe_skill(2)
    acc3 = maybe_skill(3)
    
    # 개체 생성
    reward = create_instance(
        hp=hp,
        atk=atk,
        ms=ms,
        main_color=main_color,
        sub_color=sub_color,
        pattern_color=pattern_color,
        pattern=pattern,
        accessory_1=acc1,
        accessory_2=acc2,
        accessory_3=acc3,
        name=f"Stage {stage} Reward",
        created_by="Battle Reward"
    )
    
    return reward

def page_battle():
    """전투 화면"""
    st.title("⚔️ 전투 - 스테이지 도전")
    
    # 현재 스테이지 정보 (세션 스테이트에서 가져오기)
    if "current_stage" not in st.session_state:
        st.session_state.current_stage = 1
    
    current_stage = st.session_state.current_stage
    
    st.markdown(f"""
    ### 🎮 전투 시스템
    - **1:1 턴제 자동 전투**
    - MS가 높을수록 선공 및 추가 행동
    - 각 악세서리는 **전투 스킬**로 작동
    - 최대 50턴, 타임아웃 시 HP% 비교
    
    **현재 스테이지**: Stage {current_stage}
    """)
    
    # 소유한 개체 목록
    instances = st.session_state.instances
    if not instances:
        st.warning("소유한 개체가 없습니다.")
        return
    
    # 전투력 계산 (전역 calculate_power_score 함수 사용)
    def calc_power(inst):
        return calculate_power_score(inst["stats"])
    
    # 전투력 순으로 정렬
    sorted_instances = sorted(
        instances,
        key=lambda x: calc_power(x),
        reverse=True
    )
    
    # 대표 캐릭터 찾기
    representative_id = st.session_state.get("representative_id")
    instance_options = [f"{inst['name']} (전투력: {format_korean_number(calc_power(inst))})" for inst in sorted_instances]
    
    default_idx = 0
    if representative_id:
        for idx, inst in enumerate(sorted_instances):
            if inst["id"] == representative_id:
                default_idx = idx
                break
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**우리팀 선택**")
        
        selected_display = st.selectbox(
            "참전 개체",
            instance_options,
            index=default_idx
        )
        
        # 실제 개체 찾기
        selected_idx = instance_options.index(selected_display)
        player_instance = sorted_instances[selected_idx]
        
        # 플레이어 정보
        display_instance_card(player_instance)
    
    with col2:
        st.markdown("**적군 정보**")
        
        # 현재 스테이지 적 생성
        enemy = generate_stage_enemy(current_stage)
        
        # 적 정보
        display_instance_card(enemy)
        
        # 적 스탯
        st.info(f"**Stage {current_stage} 보스**\n\nHP: {enemy['stats']['hp']}\nATK: {enemy['stats']['atk']}\nMS: {enemy['stats']['ms']}")
        
        # 전투력 비교
        player_power = calc_power(player_instance)
        enemy_power = calc_power(enemy)
        
        st.metric("전투력 비교", f"{format_korean_number(player_power)} vs {format_korean_number(enemy_power)}", 
                  delta=player_power - enemy_power,
                  delta_color="normal")
    
    # 전투 시작 버튼
    st.markdown("---")
    
    # 전투 진행 중 여부 확인
    battle_in_progress = st.session_state.get("battle_in_progress", False)
    
    if st.button("⚔️ 전투 시작!", type="primary", use_container_width=True, disabled=battle_in_progress):
        # 전투 진행 플래그 설정
        st.session_state.battle_in_progress = True
        
        # 전투 진행 상태 표시
        st.markdown("### ⚔️ 전투 진행 중...")
        
        # 화면 영역 분리
        gauge_area = st.empty()
        status_area = st.empty()
        log_area = st.empty()
        
        # 전투 실행 (실시간 업데이트)
        battle = Battle(player_instance, enemy)
        
        # 턴별 실행
        turn_count = 0
        max_turns = 50
        action_threshold = battle.action_threshold  # Battle 클래스의 고정 임계값 사용
        
        # 이전 HP 추적 (데미지 시각화용)
        prev_player_hp = battle.player.current_hp
        prev_enemy_hp = battle.enemy.current_hp
        
        while battle.turn < max_turns:
            # 승패 체크
            if battle.player.current_hp <= 0 or battle.enemy.current_hp <= 0:
                break
            
            # 한 틱 실행 (행동 발생 시 True 반환)
            action_occurred = battle.execute_turn()
            
            # 행동 발생 시 승패 체크
            if action_occurred and battle.check_victory():
                break
            
            # === ATB 게이지 시각화 ===
            # 게이지를 0-100% 범위로 정규화 (임계값을 100%로)
            player_gauge_percent = min(100, (battle.player.speed_gauge / action_threshold) * 100)
            enemy_gauge_percent = min(100, (battle.enemy.speed_gauge / action_threshold) * 100)
            
            # 행동 중인지 체크 (게이지가 100% 도달)
            player_ready = player_gauge_percent >= 100
            enemy_ready = enemy_gauge_percent >= 100
            
            # 게이지 색상 (고정)
            player_gauge_color = "#0066ff"
            enemy_gauge_color = "#ff0000"
            
            player_text = "⚡ 행동!" if player_ready else "게이지"
            enemy_text = "⚡ 행동!" if enemy_ready else "게이지"
            
            gauge_area.markdown(f"""
            <div style="display: flex; align-items: center; gap: 10px; margin: 20px 0;">
                <div style="flex: 1; text-align: right;">
                    <div style="margin-bottom: 5px; font-weight: bold;">🔵 플레이어 {player_text}</div>
                    <div style="background: rgba(0,0,0,0.1); height: 30px; border-radius: 5px; overflow: hidden;">
                        <div style="background: {player_gauge_color}; height: 100%; width: {player_gauge_percent}%; transition: width 0.1s; float: left;"></div>
                    </div>
                </div>
                <div style="font-size: 24px; font-weight: bold; padding: 0 10px;">⚔️</div>
                <div style="flex: 1; text-align: left;">
                    <div style="margin-bottom: 5px; font-weight: bold;">🔴 적군 {enemy_text}</div>
                    <div style="background: rgba(0,0,0,0.1); height: 30px; border-radius: 5px; overflow: hidden;">
                        <div style="background: {enemy_gauge_color}; height: 100%; width: {enemy_gauge_percent}%; transition: width 0.1s; float: right;"></div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # === HP 상태 업데이트 (데미지/회복 시각화) ===
            player_hp_percent = (battle.player.current_hp / battle.player.max_hp) * 100
            enemy_hp_percent = (battle.enemy.current_hp / battle.enemy.max_hp) * 100
            
            # 이전 HP 비율
            prev_player_hp_percent = (prev_player_hp / battle.player.max_hp) * 100
            prev_enemy_hp_percent = (prev_enemy_hp / battle.enemy.max_hp) * 100
            
            # HTML 직접 생성
            html_parts = ['<div style="display: flex; gap: 20px; margin: 10px 0;">']
            
            # 플레이어 HP + 쉴드
            html_parts.append('<div style="flex: 1;">')
            shield_text_player = f' + 🛡️{battle.player.shield}' if battle.player.shield > 0 else ''
            html_parts.append(f'<div style="font-weight: bold; margin-bottom: 5px;">🔵 플레이어 HP: {battle.player.current_hp}/{battle.player.max_hp}{shield_text_player}</div>')
            html_parts.append('<div style="background: rgba(0,0,0,0.1); height: 25px; border-radius: 5px; overflow: hidden; position: relative;">')
            
            if prev_player_hp > battle.player.current_hp:  # 데미지
                # 빨강이 이전 HP 위치에서 천천히 줄어듬
                html_parts.append(f'<div style="background: #ff3333; height: 100%; width: {prev_player_hp_percent}%; transition: width 0.8s; position: absolute;"></div>')
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {player_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
            elif prev_player_hp < battle.player.current_hp:  # 회복
                # 하늘색이 현재 HP까지, 녹색이 천천히 따라감
                html_parts.append(f'<div style="background: #33ccff; height: 100%; width: {player_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {prev_player_hp_percent}%; transition: width 0.8s; position: absolute;"></div>')
            else:
                # 변화 없음
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {player_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
            
            # 쉴드 바 추가 (HP 바 위에 노란색으로 표시)
            if battle.player.shield > 0:
                shield_percent = min(100, (battle.player.shield / battle.player.max_hp) * 100)
                html_parts.append(f'<div style="background: rgba(255, 215, 0, 0.7); height: 100%; width: {shield_percent}%; transition: width 0.3s; position: absolute; left: {player_hp_percent}%;"></div>')
            
            html_parts.append('</div></div>')
            
            # 적군 HP + 쉴드
            html_parts.append('<div style="flex: 1;">')
            shield_text_enemy = f' + 🛡️{battle.enemy.shield}' if battle.enemy.shield > 0 else ''
            html_parts.append(f'<div style="font-weight: bold; margin-bottom: 5px;">🔴 적군 HP: {battle.enemy.current_hp}/{battle.enemy.max_hp}{shield_text_enemy}</div>')
            html_parts.append('<div style="background: rgba(0,0,0,0.1); height: 25px; border-radius: 5px; overflow: hidden; position: relative;">')
            
            if prev_enemy_hp > battle.enemy.current_hp:  # 데미지
                html_parts.append(f'<div style="background: #ff3333; height: 100%; width: {prev_enemy_hp_percent}%; transition: width 0.8s; position: absolute;"></div>')
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {enemy_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
            elif prev_enemy_hp < battle.enemy.current_hp:  # 회복
                html_parts.append(f'<div style="background: #33ccff; height: 100%; width: {enemy_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {prev_enemy_hp_percent}%; transition: width 0.8s; position: absolute;"></div>')
            else:
                html_parts.append(f'<div style="background: #00cc00; height: 100%; width: {enemy_hp_percent}%; transition: width 0.3s; position: absolute;"></div>')
            
            # 쉴드 바 추가 (HP 바 위에 노란색으로 표시)
            if battle.enemy.shield > 0:
                shield_percent = min(100, (battle.enemy.shield / battle.enemy.max_hp) * 100)
                html_parts.append(f'<div style="background: rgba(255, 215, 0, 0.7); height: 100%; width: {shield_percent}%; transition: width 0.3s; position: absolute; left: {enemy_hp_percent}%;"></div>')
            
            html_parts.append('</div></div>')
            
            html_parts.append('</div>')
            
            status_area.markdown(''.join(html_parts), unsafe_allow_html=True)
            
            # HP 변경 시 이전 값 업데이트
            if action_occurred:
                prev_player_hp = battle.player.current_hp
                prev_enemy_hp = battle.enemy.current_hp
            
            # 로그 업데이트 (스크롤 자동으로 아래로)
            log_text = "\n".join(battle.log[-15:])  # 최근 15줄만 표시
            log_area.markdown(f"""
            <div style="
                height: 250px; 
                overflow-y: auto; 
                padding: 10px; 
                border: 1px solid rgba(128, 128, 128, 0.3); 
                border-radius: 5px;
                background-color: rgba(0, 0, 0, 0.05);
                font-family: monospace;
                white-space: pre-wrap;
                font-size: 0.9em;
            " id="battle-log-{turn_count}">
{log_text}
            </div>
            <script>
                var logDiv = document.getElementById('battle-log-{battle.turn}');
                if (logDiv) {{
                    logDiv.scrollTop = logDiv.scrollHeight;
                }}
            </script>
            """, unsafe_allow_html=True)
            
            # 0.1초 대기 (부드러운 애니메이션)
            time.sleep(0.1)
            
            # 행동 발생 시 0.3초 추가 대기 (게이지 리셋 상태 보여주기)
            if action_occurred:
                time.sleep(0.3)
        
        # 최종 승패 판정 (턴 초과 시)
        if not battle.check_victory():
            # 타임아웃이 아직 체크되지 않았다면
            battle.check_victory()
        
        winner = battle.winner
        
        # 결과 저장
        st.session_state.battle_result = {
            "winner": winner,
            "log": battle.log,
            "player": player_instance,
            "enemy": enemy,
            "player_final_hp": battle.player.current_hp,
            "enemy_final_hp": battle.enemy.current_hp,
            "stage": current_stage,
            "balloons_shown": False  # 풍선 표시 여부 플래그
        }
        
        # 전투 진행 플래그 해제
        st.session_state.battle_in_progress = False
        
        # 승리 시 스테이지 업데이트 및 보상 생성
        if winner == "player":
            st.session_state.current_stage = current_stage + 1
            
            # 보상 개체 생성
            boss_power = calculate_power_score(enemy["stats"])
            reward_instance = generate_battle_reward(boss_power, current_stage)
            st.session_state.battle_reward = reward_instance
            
            save_game_data()
        
        st.rerun()
    
    # 전투 결과 표시
    if "battle_result" in st.session_state:
        result = st.session_state.battle_result
        
        st.markdown("---")
        st.markdown(f"### 📊 전투 결과 - Stage {result.get('stage', 1)}")
        
        if result["winner"] == "player":
            st.success("🎉 승리!")
            # 풍선은 한 번만 표시
            if not result.get("balloons_shown", False):
                st.balloons()
                result["balloons_shown"] = True
            st.info(f"✨ 다음 스테이지 진출! Stage {st.session_state.current_stage} 도전 가능!")
            
            # 보상 수령 UI
            if "battle_reward" in st.session_state:
                st.markdown("---")
                st.markdown("### 🎁 승리 보상")
                
                reward = st.session_state.battle_reward
                
                col_reward1, col_reward2 = st.columns([1, 2])
                with col_reward1:
                    display_instance_card(reward, show_details=False)
                
                with col_reward2:
                    st.markdown(f"**{reward['name']}**")
                    reward_power = calculate_power_score(reward["stats"])
                    st.markdown(f"💪 전투력: **{format_korean_number(reward_power)}**")
                    
                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        st.metric("HP", f"{reward['stats']['hp']:,}")
                    with col_s2:
                        st.metric("ATK", f"{reward['stats']['atk']:,}")
                    with col_s3:
                        st.metric("MS", f"{reward['stats']['ms']:,}")
                    
                    st.markdown("**스킬:**")
                    for i in range(1, 4):
                        acc_key = f"accessory_{i}"
                        if reward.get(acc_key):
                            skill_id = reward[acc_key]["id"]
                            if skill_id in SKILL_MASTER:
                                skill = SKILL_MASTER[skill_id]
                                st.markdown(f"- 슬롯 {i}: {skill['name']} ({skill['grade']})")
                        else:
                            st.markdown(f"- 슬롯 {i}: 없음")
                    
                    if st.button("🎁 보상 수령", type="primary", use_container_width=True):
                        # 인벤토리에 추가
                        st.session_state.instances.append(reward)
                        # 도감 업데이트
                        update_collection(reward)
                        save_game_data()
                        del st.session_state.battle_reward
                        st.success("보상을 획득했습니다!")
                        time.sleep(1)
                        st.rerun()
        
        elif result["winner"] == "enemy":
            st.error("💀 패배...")
        else:
            st.info("🤝 무승부")
        
        # 최종 상태
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🔵 플레이어**")
            player_final_hp = result["player_final_hp"]
            player_max_hp = result["player"]["stats"]["hp"]
            hp_percent = (player_final_hp / player_max_hp) * 100 if player_max_hp > 0 else 0
            
            st.metric("최종 HP", f"{player_final_hp:,}/{player_max_hp:,}")
            st.progress(hp_percent / 100.0)
            
        with col2:
            st.markdown("**🔴 적군**")
            enemy_final_hp = result["enemy_final_hp"]
            enemy_max_hp = result["enemy"]["stats"]["hp"]
            hp_percent = (enemy_final_hp / enemy_max_hp) * 100 if enemy_max_hp > 0 else 0
            
            st.metric("최종 HP", f"{enemy_final_hp:,}/{enemy_max_hp:,}")
            st.progress(hp_percent / 100.0)
        
        # 전투 로그
        st.markdown("### 📜 전투 로그")
        log_text = "\n".join(result["log"])
        st.text_area("로그", value=log_text, height=400, disabled=True)
        
        # 다시 전투 버튼
        if st.button("🔄 다시 전투", use_container_width=True):
            del st.session_state.battle_result
            if "battle_in_progress" in st.session_state:
                del st.session_state.battle_in_progress
            if "battle_reward" in st.session_state:
                del st.session_state.battle_reward
            st.rerun()


def page_breed():
    """믹스 화면"""
    st.title("🧬 믹스")
    
    # 믹스 설명서
    with st.expander("📖 믹스 시스템 설명서", expanded=False):
        st.markdown("""
        ### 🧬 믹스 시스템 가이드
        
        #### 📊 능력치 결정 방식
        - **HP, ATK, MS**: 부모 중 1명의 값을 무작위로 상속
        - 돌연변이가 발생하지 않는 한, 자식은 부모 중 하나의 능력치를 그대로 물려받습니다
        
        #### 🎨 외형 결정 방식
        - **색상/패턴**: 부모의 외형 중 하나를 **등급 가중치** 기반으로 상속
        - **스킬 (악세서리)**: 각 슬롯(1/2/3)별로 부모의 스킬 중 하나를 상속 (없을 수도 있음)
        
        #### 🔥 돌연변이 시스템
        - **1차 돌연변이 확률**: 50% × (1 + 보너스)
        - **2차 연쇄 돌연변이**: 1차 발생 시 40% × (1 + 보너스) 확률
        - **3차 연쇄 돌연변이**: 2차 발생 시 20% × (1 + 보너스) 확률
        
        #### 🎯 돌연변이 카테고리
        각 연쇄 단계마다 다음 중 하나가 변이됩니다:
        - **능력치 변이**: 80% (HP/ATK/MS 중 하나가 증가)
        - **외형 변이**: 15% (색상/패턴이 새로운 등급으로 변경)
        - **스킬 변이**: 5% (악세서리가 새로운 등급/종류로 변경)
        
        ✅ 같은 항목에 중복 돌연변이는 발생하지 않음  
        ✅ 능력치 변이 시 더 높은 부모의 값 기준으로 증가  
        ⚠️ 돌연변이 세부 증가량은 비공개
        
        #### ⏱️ 믹스 쿨타임
        - 믹스 후 10초간 대기 시간이 적용됩니다
        """)
    
    st.markdown("---")
    
    # 믹스 대기시간 체크
    can_breed = True
    remaining_time = 0
    if st.session_state.last_breed_time:
        elapsed = time.time() - st.session_state.last_breed_time
        remaining_time = 10 - elapsed
        if remaining_time > 0:
            can_breed = False
            st.warning(f"⏳ 믹스 대기 중... {remaining_time:.1f}초 남음")
    
    # 부모 선택
    st.markdown("### 부모 선택")
    
    # 즐겨찾기 필터
    show_favorites_only = st.checkbox("⭐ 즐겨찾기만 표시", value=False, key="breed_favorites_filter")
    
    st.markdown("---")
    
    # 개체 목록 필터링
    filtered_instances = st.session_state.instances
    if show_favorites_only:
        filtered_instances = [inst for inst in st.session_state.instances if inst.get("is_favorite", False)]
    
    if not filtered_instances:
        st.warning("⚠️ 필터 조건에 맞는 개체가 없습니다. 즐겨찾기를 설정하거나 필터를 해제하세요.")
        return
    
    # 전체 개체 목록 준비 (역순 정렬, 즐겨찾기 표시) - selectbox용
    all_options = []
    for inst in reversed(filtered_instances):
        favorite_icon = "⭐" if inst.get('is_favorite', False) else ""
        display_name = f"{inst['name']}{favorite_icon}"
        all_options.append((display_name, inst['id']))
    
    all_names = [opt[0] for opt in all_options]
    all_ids = [opt[1] for opt in all_options]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**부모 A**")
        
        # 기본 인덱스 설정
        default_a_index = 0
        if st.session_state.selected_parent_a and st.session_state.selected_parent_a in all_ids:
            default_a_index = all_ids.index(st.session_state.selected_parent_a)
        
        parent_a_selected_name = st.selectbox(
            "부모 A 선택", 
            all_names, 
            index=default_a_index, 
            key=f"parent_a_select_{st.session_state.get('selected_parent_a', 'none')}"
        )
        parent_a_id = all_ids[all_names.index(parent_a_selected_name)]
        st.session_state.selected_parent_a = parent_a_id
        
        parent_a = next(inst for inst in st.session_state.instances if inst['id'] == parent_a_id)
        display_instance_card(parent_a, show_compact=True)
    
    with col2:
        st.markdown("**부모 B**")
        
        # 기본 인덱스 설정
        default_b_index = 0
        if st.session_state.selected_parent_b and st.session_state.selected_parent_b in all_ids:
            default_b_index = all_ids.index(st.session_state.selected_parent_b)
        
        parent_b_selected_name = st.selectbox(
            "부모 B 선택", 
            all_names, 
            index=default_b_index, 
            key=f"parent_b_select_{st.session_state.get('selected_parent_b', 'none')}"
        )
        parent_b_id = all_ids[all_names.index(parent_b_selected_name)]
        st.session_state.selected_parent_b = parent_b_id
        
        parent_b = next(inst for inst in st.session_state.instances if inst['id'] == parent_b_id)
        display_instance_card(parent_b, show_compact=True)
    
    # 동일 개체 체크
    if parent_a_id == parent_b_id:
        st.error("❌ 동일한 개체는 믹스할 수 없습니다. 서로 다른 개체를 선택해주세요.")
        can_breed = False
    
    # 개체 수 제한 체크
    max_instances = st.session_state.get("max_instances", 200)
    if len(st.session_state.instances) >= max_instances:
        st.error(f"⚠️ 개체 목록이 최대 {max_instances}개를 초과했습니다. 일부 개체를 삭제해주세요.")
        can_breed = False
    
    # 믹스 버튼과 자동 선택 버튼을 좌우로 배치
    col_auto_btn, col_breed_btn = st.columns(2)
    
    with col_auto_btn:
        if len(st.session_state.instances) >= 2:
            if st.button("⚡ 최고 스탯 자동 선택", use_container_width=True, key="auto_select_bottom"):
                # 전투력 순으로 정렬
                sorted_instances = sorted(
                    st.session_state.instances,
                    key=lambda x: calculate_power_score(x["stats"]),
                    reverse=True
                )
                # 상위 2개 선택
                st.session_state.selected_parent_a = sorted_instances[0]["id"]
                st.session_state.selected_parent_b = sorted_instances[1]["id"]
                st.rerun()
    
    with col_breed_btn:
        breed_button_clicked = st.button("🧬 믹스 시작", disabled=not can_breed, use_container_width=True)
    
    if breed_button_clicked:
        # 믹스 전 도감 상태 저장
        if "collection" not in st.session_state:
            st.session_state.collection = {
                "colors": {"main": set(), "sub": set(), "pattern": set()},
                "patterns": set(),
                "accessories": set()
            }
        
        collection_before = {
            "colors": {
                "main": st.session_state.collection["colors"]["main"].copy(),
                "sub": st.session_state.collection["colors"]["sub"].copy(),
                "pattern": st.session_state.collection["colors"]["pattern"].copy()
            },
            "patterns": st.session_state.collection["patterns"].copy(),
            "accessories": st.session_state.collection["accessories"].copy()
        }
        
        result = breed(parent_a, parent_b)
        st.session_state.breed_result = result
        
        # 믹스 결과의 새로운 발견 추적
        new_discoveries = []
        if result["appearance"]["main_color"]["id"] not in collection_before["colors"]["main"]:
            new_discoveries.append(("메인 색상", COLOR_MASTER[result["appearance"]["main_color"]["id"]]["name"]))
        if result["appearance"]["sub_color"]["id"] not in collection_before["colors"]["sub"]:
            new_discoveries.append(("서브 색상", COLOR_MASTER[result["appearance"]["sub_color"]["id"]]["name"]))
        if result["appearance"]["pattern_color"]["id"] not in collection_before["colors"]["pattern"]:
            new_discoveries.append(("패턴 색상", COLOR_MASTER[result["appearance"]["pattern_color"]["id"]]["name"]))
        if result["appearance"]["pattern"]["id"] not in collection_before["patterns"]:
            pattern_data = PATTERN_MASTER[result["appearance"]["pattern"]["id"]]
            new_discoveries.append(("패턴", pattern_data.get("name", pattern_data["layout"])))
        
        # 스킬 발견 체크 (슬롯별)
        for i in range(1, 4):
            acc_key = f"accessory_{i}"
            if result.get(acc_key):
                skill_id = result[acc_key]["id"]
                # 기존 컬렉션에 없는 스킬인지 확인
                if skill_id not in collection_before["accessories"]:
                    skill_data = SKILL_MASTER.get(skill_id)
                    if skill_data:
                        new_discoveries.append((f"슬롯 {i} 스킬", f"{skill_data['name']} ({skill_data['grade']})"))
        
        st.session_state.new_discoveries = new_discoveries
        st.session_state.last_breed_time = time.time()
        
        # SVG 미리 렌더링하여 캐싱 (결과 표시 속도 향상)
        _ = get_instance_svg(result, size=120)
        
        # save_game_data() 제거 - 결과 저장 시에만 DB 저장
        
        # 개체 목록 페이지 초기화 (최신 개체가 보이도록)
        if "list_page" in st.session_state:
            st.session_state.list_page = 1
        
        st.rerun()
    
    # 믹스 결과
    if st.session_state.breed_result:
        st.markdown("---")
        st.markdown("### 🎉 믹스 결과")
        
        result = st.session_state.breed_result
        display_instance_card(result, show_compact=True)
        
        # 전투력 비교 (최대 전투력 달성 확인)
        result_power = result.get("power_score", 0)
        max_power = st.session_state.get("max_power", 0)
        if result_power > max_power:
            st.success(f"🎊 역대 최고 전투력 달성! (이전 기록: {max_power})")
        
        # 새로운 발견 알림
        if st.session_state.get("new_discoveries"):
            st.success("✨ 새로운 외형 발견!")
            discoveries_by_type = {}
            for disc_type, disc_name in st.session_state.new_discoveries:
                if disc_type not in discoveries_by_type:
                    discoveries_by_type[disc_type] = []
                discoveries_by_type[disc_type].append(disc_name)
            
            for disc_type, names in discoveries_by_type.items():
                st.write(f"📖 {disc_type}: {', '.join(names)}")
        
        # 돌연변이 리포트
        if result['mutation']['count'] > 0:
            st.success(f"🔥 돌연변이 발생! ({result['mutation']['count']}회 연쇄)")
            st.write(f"변이된 항목: {', '.join(result['mutation']['fields'])}")
        else:
            st.info("돌연변이 없음")
        
        col1, col2 = st.columns(2)
        with col1:
            # 개체 수 제한 체크
            max_instances = st.session_state.get("max_instances", 200)
            if len(st.session_state.instances) >= max_instances:
                st.button("✅ 결과 저장", disabled=True, use_container_width=True)
                st.error(f"⚠️ 개체 {max_instances}개 초과")
            elif st.button("✅ 결과 저장", use_container_width=True):
                st.session_state.instances.append(result)
                # 최대 전투력 갱신
                result_power = result.get("power_score", 0)
                if result_power > st.session_state.get("max_power", 0):
                    st.session_state.max_power = result_power
                st.session_state.breed_result = None
                st.session_state.last_breed_time = None
                if "new_discoveries" in st.session_state:
                    del st.session_state.new_discoveries
                
                # 페이지 초기화 (최신 개체가 보이도록)
                if "list_page" in st.session_state:
                    st.session_state.list_page = 1
                
                save_game_data()
                st.success("새 개체가 추가되었습니다!")
                st.rerun()
        
        with col2:
            if st.button("❌ 버리기", use_container_width=True):
                st.session_state.breed_result = None
                st.session_state.last_breed_time = None
                if "new_discoveries" in st.session_state:
                    del st.session_state.new_discoveries
                # save_game_data() 제거 - 버릴 때는 DB 저장 불필요
                st.info("결과를 버렸습니다.")
                st.rerun()

def page_season_info():
    """시즌 정보 페이지"""
    st.title("🏆 시즌 정보")
    
    # 시즌 데이터 로드
    season_data = load_season_history()
    current_season = season_data["current_season"]
    
    # 현재 시즌 정보
    st.markdown("## 📅 현재 시즌")
    
    if current_season == 0:
        season_display = "Season Beta"
        season_desc = "베타 테스트 시즌"
    elif current_season == "Preseason":
        season_display = "Preseason"
        season_desc = "시즌 1 준비 기간 (1/16 ~ 1/18)"
    else:
        season_display = f"Season {current_season}"
        season_desc = f"정식 시즌 {current_season}"
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**{season_display}**")
        st.markdown(f"_{season_desc}_")
    with col2:
        # 다음 시즌 시작일
        if current_season == "Preseason":
            st.warning("**시즌 1 시작: 2026년 1월 19일**")
            current_date = datetime.now().date()
            season1_start = datetime(2026, 1, 19).date()
            days_left = (season1_start - current_date).days
            if days_left > 0:
                st.markdown(f"⏰ {days_left}일 남음")
            else:
                st.markdown("🎯 시작 가능!")
    
    st.markdown("---")
    
    # 시즌 특전
    st.markdown("## 🎁 시즌 특전")
    
    # Season 0 챔피언 정보
    if "season0_champion" in season_data and season_data["season0_champion"]:
        champion = season_data["season0_champion"]
        st.success(f"**🏅 Season 0 Champion: {champion}**")
        st.markdown("""
        **챔피언 특전:**
        - 🧬 돌연변이 확률 +10%
        - 🔗 최대 연쇄 돌연변이 4개 (일반 3개)
        - 👑 시즌별 리더보드 기록
        """)
    
    # 일반 유저 정보
    st.markdown("### 일반 유저")
    st.markdown("""
    - 🧬 기본 돌연변이 확률
    - 🔗 최대 연쇄 돌연변이 3개
    - 📦 랜덤박스 24시간마다 1회
    """)
    
    st.markdown("---")
    
    # 시즌 히스토리
    st.markdown("## 📜 시즌 히스토리")
    
    if season_data["history"]:
        for idx, season_record in enumerate(reversed(season_data["history"])):
            season_num = season_record["season"]
            season_label = "Beta" if season_num == 0 else f"Season {season_num}"
            end_time = datetime.fromisoformat(season_record["end_time"]).strftime("%Y년 %m월 %d일")
            
            with st.expander(f"🏆 {season_label} (종료일: {end_time})"):
                if season_record["top3"]:
                    cols = st.columns(3)
                    medals = ["🥇", "🥈", "🥉"]
                    
                    for i, user in enumerate(season_record["top3"][:3]):
                        with cols[i]:
                            st.markdown(f"### {medals[i]} {i+1}위")
                            st.markdown(f"**{user['username']}**")
                            
                            # instance 또는 representative 키 모두 지원
                            rep = user.get("instance") or user.get("representative")
                            if rep:
                                # SVG 이미지
                                svg = get_instance_svg(rep, size=120)
                                st.markdown(svg, unsafe_allow_html=True)
                                
                                st.markdown(f"**{rep['name']}**")
                                # power_score는 user 레벨 또는 rep 레벨에 있을 수 있음
                                power = user.get("power_score", rep.get("power_score", 0))
                                st.caption(f"⚔️ {power:,}")
                                
                                # 간단한 스탯
                                stat_col1, stat_col2, stat_col3 = st.columns(3)
                                with stat_col1:
                                    st.metric("HP", f"{rep['stats']['hp']:,}")
                                with stat_col2:
                                    st.metric("ATK", f"{rep['stats']['atk']:,}")
                                with stat_col3:
                                    st.metric("MS", f"{rep['stats']['ms']:,}")
                            else:
                                st.caption("대표 유닛 없음")
                else:
                    st.info("순위 기록 없음")
    else:
        st.info("아직 종료된 시즌이 없습니다")
    
    st.markdown("---")
    
    # 시즌 시스템 설명
    st.markdown("## ℹ️ 시즌 시스템")
    
    with st.expander("🔄 시즌 초기화란?"):
        st.markdown("""
        **시즌이 종료되면:**
        - 모든 유저의 개체가 삭제됩니다
        - 컬렉션이 초기화됩니다
        - 스테이지가 1로 리셋됩니다
        - **비밀번호는 유지**되므로 같은 계정으로 다시 시작할 수 있습니다
        
        **유지되는 것:**
        - 계정 (유저명, 비밀번호)
        - 전 시즌 1등의 챔피언 특전
        """)
    
    with st.expander("🏅 순위 산정 방식"):
        st.markdown("""
        **랭킹 기준:**
        1. 대표 유닛의 전투력 (Power Score)
        2. 대표 유닛이 없으면 순위에서 제외
        
        **전투력 계산:**
        - 기본 스탯 (HP, ATK, MS)
        - 스킬 등급 보너스
        - 색상/패턴 등급 보너스
        """)
    
    with st.expander("📅 시즌 일정"):
        st.markdown("""
        **현재 계획:**
        - **Season 0 (Beta)**: 베타 테스트 기간
        - **Preseason (1/16 ~ 1/18)**: 게임 숙지 기간
        - **Season 1 (1/19~)**: 정식 시즌 시작
        
        향후 시즌 일정은 운영 상황에 따라 결정됩니다.
        """)

def page_admin():
    """관리자 메뉴 - 사용자 관리"""
    st.title("👨‍💼 사용자 관리")
    
    # 탭 분할
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 사용자 목록", "🎮 사용자 개체", "🗑️ 개체 삭제", "🧬 돌연변이 설정", 
        "🗑️ 사용자 삭제", "📬 우편 지급", "🎁 랜덤박스 관리"
    ])
    
    with tab1:
        st.markdown("### 모든 사용자")
        
        from supabase_db import get_all_users, get_user_info
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            st.info(f"총 {len(users)}명의 사용자")
            
            # 테이블 형식으로 표시
            user_data = []
            for user in users:
                created = user.get("created_at", "N/A")
                if isinstance(created, str):
                    created = created.split("T")[0]  # 날짜만 추출
                
                user_data.append({
                    "사용자명": user["username"],
                    "ID": user["id"][:8] + "...",
                    "가입일": created
                })
            
            st.dataframe(user_data, use_container_width=True, hide_index=True)
            
            # 사용자 상세 정보 조회
            st.markdown("---")
            st.markdown("### 사용자 상세 정보")
            
            selected_username = st.selectbox(
                "사용자 선택",
                [u["username"] for u in users]
            )
            
            if selected_username:
                user_info = get_user_info(selected_username)
                if user_info:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**사용자명:** {user_info['username']}")
                        st.markdown(f"**ID:** {user_info['id']}")
                    with col2:
                        created = user_info.get("created_at", "N/A")
                        if isinstance(created, str):
                            created = created.split("T")[0]
                        updated = user_info.get("updated_at", "N/A")
                        if isinstance(updated, str):
                            updated = updated.split("T")[0]
                        st.markdown(f"**가입일:** {created}")
                        st.markdown(f"**마지막 업데이트:** {updated}")
    
    with tab2:
        st.markdown("### 사용자의 보유 개체")
        
        from supabase_db import get_all_users, get_user_instances
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            selected_username = st.selectbox(
                "사용자 선택",
                [u["username"] for u in users],
                key="instance_view_user"
            )
            
            if selected_username:
                instances = get_user_instances(selected_username)
                
                if not instances:
                    st.info(f"'{selected_username}' 사용자가 보유한 개체가 없습니다.")
                else:
                    st.success(f"총 {len(instances)}개의 개체 보유중")
                    
                    # 개체 목록 표시
                    # 최신 생성 순으로 정렬 (birth_time 기준 내림차순)
                    def _birth_key(x):
                        bt = x.get('birth_time')
                        if isinstance(bt, str):
                            try:
                                return datetime.fromisoformat(bt)
                            except:
                                pass
                        return datetime.min
                    instances_sorted = sorted(instances, key=lambda x: _birth_key(x), reverse=True)

                    for idx, inst in enumerate(instances_sorted, 1):
                        # 전투력 계산
                        stats = inst.get('stats', {})
                        if stats:
                            power_score = calculate_power_score(stats)
                        else:
                            power_score = 0
                        
                        with st.expander(f"#{idx} {inst.get('name', 'Unknown')} - 전투력: {format_korean_number(power_score)}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown(f"**이름:** {inst.get('name', 'N/A')}")
                                st.markdown(f"**ID:** {inst.get('id', 'N/A')}")
                            with col2:
                                st.markdown(f"**HP:** {stats.get('hp', 'N/A'):,}")
                                st.markdown(f"**ATK:** {stats.get('atk', 'N/A'):,}")
                                st.markdown(f"**MS:** {stats.get('ms', 'N/A'):,}")
                            
                            st.markdown("---")
                            
                            # 외형 정보
                            appearance = inst.get('appearance', {})
                            if appearance:
                                st.markdown("**🎨 외형**")
                                
                                # 색상 정보
                                try:
                                    main_color_id = appearance.get('main_color', {}).get('id')
                                    if main_color_id and main_color_id in COLOR_MASTER:
                                        main_color = COLOR_MASTER[main_color_id]
                                        st.markdown(f"• **Main Color:** {main_color['name']} ({main_color['grade']})")
                                    
                                    sub_color_id = appearance.get('sub_color', {}).get('id')
                                    if sub_color_id and sub_color_id in COLOR_MASTER:
                                        sub_color = COLOR_MASTER[sub_color_id]
                                        st.markdown(f"• **Sub Color:** {sub_color['name']} ({sub_color['grade']})")
                                    
                                    pattern_color_id = appearance.get('pattern_color', {}).get('id')
                                    if pattern_color_id and pattern_color_id in COLOR_MASTER:
                                        pattern_color = COLOR_MASTER[pattern_color_id]
                                        st.markdown(f"• **Pattern Color:** {pattern_color['name']} ({pattern_color['grade']})")
                                    
                                    pattern_id = appearance.get('pattern', {}).get('id')
                                    if pattern_id and pattern_id in PATTERN_MASTER:
                                        pattern = PATTERN_MASTER[pattern_id]
                                        st.markdown(f"• **Pattern:** {pattern['layout']} ({appearance.get('pattern', {}).get('grade')})")
                                except:
                                    st.caption("외형 정보 표시 중 오류 발생")
                            
                            st.markdown("---")
                            
                            # 스킬 정보
                            st.markdown("**⚔️ 스킬**")
                            has_skill = False
                            for i in range(1, 4):
                                acc_key = f"accessory_{i}"
                                if inst.get(acc_key):
                                    acc = inst[acc_key]
                                    acc_id = acc.get('id')
                                    if acc_id and acc_id in SKILL_MASTER:
                                        skill = SKILL_MASTER[acc_id]
                                        st.markdown(f"• **슬롯 {i}:** {skill['name']} ({skill['grade']})")
                                        st.caption(f"{skill.get('desc', 'N/A')}")
                                        has_skill = True
                                    else:
                                        st.caption(f"슬롯 {i}: ID {acc_id} (마스터 데이터 없음)")
                                else:
                                    st.caption(f"슬롯 {i}: 미장착")
                            
                            if not has_skill:
                                st.caption("장착된 스킬 없음")
    
    with tab3:
        st.markdown("### 개체 삭제")
        st.warning("⚠️ 개체를 삭제하면 복구할 수 없습니다.")
        
        from supabase_db import get_all_users, get_user_instances, delete_user_instance
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            delete_inst_username = st.selectbox(
                "사용자 선택",
                [u["username"] for u in users],
                key="instance_delete_user"
            )
            
            if delete_inst_username:
                instances = get_user_instances(delete_inst_username)
                
                if not instances:
                    st.info(f"'{delete_inst_username}' 사용자가 보유한 개체가 없습니다.")
                else:
                    st.markdown("---")
                    
                    # 개체 선택
                    # 최신 생성 순으로 정렬 (birth_time 기준 내림차순)
                    def _birth_key(x):
                        bt = x.get('birth_time')
                        if isinstance(bt, str):
                            try:
                                return datetime.fromisoformat(bt)
                            except:
                                pass
                        return datetime.min
                    instances_sorted = sorted(instances, key=lambda x: _birth_key(x), reverse=True)

                    instance_options = {}
                    for inst in instances_sorted:
                        inst_name = inst.get('name', 'Unknown')
                        inst_id = inst.get('id', 'N/A')
                        stats = inst.get('stats', {})
                        power_score = calculate_power_score(stats) if stats else 0
                        label = f"{inst_name} - 전투력: {format_korean_number(power_score)} - HP:{stats.get('hp'):,} ATK:{stats.get('atk'):,} MS:{stats.get('ms'):,}"
                        instance_options[label] = inst_id
                    
                    selected_inst_label = st.selectbox(
                        "삭제할 개체 선택",
                        list(instance_options.keys()),
                        key="delete_instance_select"
                    )
                    
                    if selected_inst_label:
                        selected_inst_id = instance_options[selected_inst_label]
                        
                        # 선택된 개체의 상세 정보 표시
                        selected_inst = next((inst for inst in instances if inst.get('id') == selected_inst_id), None)
                        
                        st.markdown("---")
                        st.info(f"**선택된 개체:** {selected_inst_label}")
                        
                        if selected_inst:
                            # 기본 정보
                            stats = selected_inst.get('stats', {})
                            st.markdown("**📊 기본 정보**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown(f"• **이름:** {selected_inst.get('name')}")
                                st.markdown(f"• **전투력:** {format_korean_number(calculate_power_score(stats) if stats else 0)}")
                            with col2:
                                st.markdown(f"• **HP:** {stats.get('hp'):,}")
                                st.markdown(f"• **ATK:** {stats.get('atk'):,}")
                                st.markdown(f"• **MS:** {stats.get('ms'):,}")
                            
                            # 외형 정보
                            appearance = selected_inst.get('appearance', {})
                            if appearance:
                                st.markdown("**🎨 외형**")
                                try:
                                    main_color_id = appearance.get('main_color', {}).get('id')
                                    if main_color_id and main_color_id in COLOR_MASTER:
                                        main_color = COLOR_MASTER[main_color_id]
                                        st.markdown(f"• **Main Color:** {main_color['name']} ({main_color['grade']})")
                                    
                                    sub_color_id = appearance.get('sub_color', {}).get('id')
                                    if sub_color_id and sub_color_id in COLOR_MASTER:
                                        sub_color = COLOR_MASTER[sub_color_id]
                                        st.markdown(f"• **Sub Color:** {sub_color['name']} ({sub_color['grade']})")
                                    
                                    pattern_color_id = appearance.get('pattern_color', {}).get('id')
                                    if pattern_color_id and pattern_color_id in COLOR_MASTER:
                                        pattern_color = COLOR_MASTER[pattern_color_id]
                                        st.markdown(f"• **Pattern Color:** {pattern_color['name']} ({pattern_color['grade']})")
                                    
                                    pattern_id = appearance.get('pattern', {}).get('id')
                                    if pattern_id and pattern_id in PATTERN_MASTER:
                                        pattern = PATTERN_MASTER[pattern_id]
                                        st.markdown(f"• **Pattern:** {pattern['layout']} ({appearance.get('pattern', {}).get('grade')})")
                                except:
                                    st.caption("외형 정보 표시 중 오류")
                            
                            # 스킬 정보
                            st.markdown("**⚔️ 스킬**")
                            for i in range(1, 4):
                                acc_key = f"accessory_{i}"
                                if selected_inst.get(acc_key):
                                    acc = selected_inst[acc_key]
                                    acc_id = acc.get('id')
                                    if acc_id and acc_id in SKILL_MASTER:
                                        skill = SKILL_MASTER[acc_id]
                                        st.markdown(f"• **슬롯 {i}:** {skill['name']} ({skill['grade']}) - {skill.get('desc', '')}")
                                    else:
                                        st.markdown(f"• **슬롯 {i}:** ID {acc_id} (마스터 데이터 없음)")
                                else:
                                    st.markdown(f"• **슬롯 {i}:** 미장착")
                        
                        st.markdown("---")
                        st.warning(f"🔒 삭제를 확인하려면 'DELETE'를 입력하세요:")
                        
                        confirm_delete = st.text_input(
                            "확인 입력",
                            placeholder="DELETE",
                            key="delete_instance_confirm"
                        ).strip().upper()
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("🗑️ 삭제", type="primary", use_container_width=True, key="delete_instance_apply"):
                                if confirm_delete == "DELETE":
                                    success, message = delete_user_instance(delete_inst_username, selected_inst_id)
                                    if success:
                                        st.success(f"✅ {message}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                                else:
                                    st.error("❌ 'DELETE'를 정확히 입력해주세요.")
                        
                        with col2:
                            if st.button("취소", use_container_width=True, key="delete_instance_cancel"):
                                st.info("취소되었습니다.")
    
    with tab4:
        st.markdown("### 돌연변이 설정 변경")
        st.info("사용자의 돌연변이 확률 보너스와 최대 연쇄 횟수를 변경할 수 있습니다.")
        
        from supabase_db import get_all_users, update_user_mutation_settings, load_game_data as load_game_data_db
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            mutation_username = st.selectbox(
                "사용자 선택",
                [u["username"] for u in users],
                key="mutation_user_select"
            )
            
            if mutation_username:
                # 현재 설정값 조회
                user_data = load_game_data_db(mutation_username)
                current_mutation_bonus = user_data.get("mutation_bonus", 0.0) if user_data else 0.0
                current_max_chain = user_data.get("max_chain_mutations", 3) if user_data else 3
                
                # 값 범위 검증
                if current_mutation_bonus < 0.0 or current_mutation_bonus > 0.5:
                    current_mutation_bonus = 0.0
                if current_max_chain not in [3, 4, 5]:
                    current_max_chain = 3
                
                st.markdown("---")
                st.markdown(f"**선택된 사용자:** {mutation_username}")
                
                # 설정 변경
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**돌연변이 확률 보너스**")
                    mutation_bonus = st.slider(
                        "보너스 설정",
                        min_value=0.0,
                        max_value=0.5,
                        value=current_mutation_bonus,
                        step=0.05,
                        help="교배 시 돌연변이 발생 확률에 추가됩니다. (예: 0.1 = +10%)",
                        key=f"mutation_bonus_slider_{mutation_username}"
                    )
                
                with col2:
                    st.markdown("**최대 연쇄 돌연변이 횟수**")
                    max_chain_mutations = st.selectbox(
                        "최대 연쇄 횟수",
                        options=[3, 4, 5],
                        index=[3, 4, 5].index(current_max_chain),
                        help="교배 시 최대 몇 번까지 연쇄 돌연변이가 발생할 수 있는지 설정합니다.",
                        key=f"max_chain_slider_{mutation_username}"
                    )
                
                # 현재 설정 표시
                st.markdown("---")
                st.info(f"""
                **변경할 설정 정보**
                - 돌연변이 보너스: +{mutation_bonus*100:.0f}%
                - 1차 돌연변이: {(0.50 * (1 + mutation_bonus))*100:.1f}%
                - 2차 연쇄: {(0.40 * (1 + mutation_bonus))*100:.1f}%
                - 3차 연쇄: {(0.20 * (1 + mutation_bonus))*100:.1f}%
                {f"- 4차 연쇄: {(0.10 * (1 + mutation_bonus))*100:.1f}% (활성)" if max_chain_mutations >= 4 else "- 4차 연쇄: 비활성"}
                {f"- 5차 연쇄: {(0.05 * (1 + mutation_bonus))*100:.1f}% (활성)" if max_chain_mutations >= 5 else "- 5차 연쇄: 비활성"}
                - 최대 연쇄: {max_chain_mutations}회
                """)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ 변경", type="primary", use_container_width=True, key="mutation_apply"):
                        success, message = update_user_mutation_settings(
                            mutation_username, 
                            mutation_bonus, 
                            max_chain_mutations
                        )
                        if success:
                            st.success(f"✅ {message}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                
                with col2:
                    if st.button("취소", use_container_width=True, key="mutation_cancel"):
                        st.info("취소되었습니다.")
    
    with tab5:
        st.markdown("### 사용자 삭제")
        st.warning("⚠️ 사용자를 삭제하면 해당 계정과 모든 게임 데이터가 영구 삭제됩니다.")
        
        from supabase_db import get_all_users, delete_user
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            delete_username = st.selectbox(
                "삭제할 사용자 선택",
                [u["username"] for u in users],
                key="delete_user_select"
            )
            
            # 확인 메커니즘
            st.markdown("---")
            
            # 선택된 사용자명 표시
            st.info(f"**선택된 사용자:** `{delete_username}`")
            st.warning(f"🔒 이 계정을 삭제하려면 아래에 정확히 '{delete_username}'을 입력하세요:")
            
            confirm_text = st.text_input(
                f"'{delete_username}'을 입력하세요",
                placeholder=delete_username,
                key="delete_confirm_input"
            ).strip()
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ 삭제", type="primary", use_container_width=True, key="delete_user_apply"):
                    # 공백 제거 후 비교
                    if confirm_text.strip() == delete_username.strip():
                        success, message = delete_user(delete_username)
                        if success:
                            st.success(f"✅ {message}")
                            st.info("페이지를 새로고침하면 목록이 업데이트됩니다.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                    else:
                        st.error(f"❌ 입력한 사용자명이 일치하지 않습니다. 입력: '{confirm_text}' vs 선택: '{delete_username}'")
            
            with col2:
                if st.button("취소", use_container_width=True, key="delete_user_cancel"):
                    st.info("취소되었습니다.")
    
    with tab6:
        st.markdown("### 📬 우편 지급")
        st.write("특정 사용자 또는 여러 사용자에게 개체 또는 랜덤박스를 우편으로 발송합니다.")
        
        from supabase_db import get_all_users
        
        users = get_all_users()
        
        if not users:
            st.info("등록된 사용자가 없습니다.")
        else:
            # 발송 모드 선택
            send_mode = st.radio(
                "발송 모드",
                ["단일 사용자", "여러 사용자", "전체 사용자"],
                key="mail_send_mode",
                horizontal=True
            )
            
            # 수신자 선택
            recipients = []
            if send_mode == "단일 사용자":
                recipient = st.selectbox(
                    "수신 사용자",
                    [u["username"] for u in users],
                    key="mail_recipient"
                )
                recipients = [recipient]
            elif send_mode == "여러 사용자":
                recipients = st.multiselect(
                    "수신 사용자 (복수 선택)",
                    [u["username"] for u in users],
                    key="mail_recipients_multi"
                )
                if not recipients:
                    st.warning("⚠️ 최소 1명 이상 선택하세요.")
            else:  # 전체 사용자
                recipients = [u["username"] for u in users]
                st.info(f"📢 전체 {len(recipients)}명의 사용자에게 발송됩니다.")
            
            # 우편 유형 선택
            mail_type = st.radio(
                "우편 유형",
                ["개체 직접 지급", "랜덤박스 지급"],
                key="mail_type"
            )
            
            message = st.text_input(
                "메시지",
                value=f"운영자 지급",
                key="mail_message"
            )
            
            if mail_type == "개체 직접 지급":
                st.markdown("#### 개체 설정")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    hp = st.number_input("HP", min_value=1, max_value=100000, value=100, key="mail_hp")
                with col2:
                    atk = st.number_input("ATK", min_value=1, max_value=10000, value=10, key="mail_atk")
                with col3:
                    ms = st.number_input("MS", min_value=1, max_value=1000, value=10, key="mail_ms")
                
                # 외형 선택
                st.markdown("#### 외형")
                
                def grade_selector(label: str, key: str) -> str:
                    return st.selectbox(label, ["Normal", "Rare", "Epic", "Unique", "Legendary", "Mystic"], key=key)
                
                col1, col2 = st.columns(2)
                with col1:
                    main_grade = grade_selector("Main Color 등급", "mail_main_grade")
                    sub_grade = grade_selector("Sub Color 등급", "mail_sub_grade")
                    pattern_color_grade = grade_selector("Pattern Color 등급", "mail_pattern_color_grade")
                    pattern_grade = grade_selector("Pattern 등급", "mail_pattern_grade")
                
                with col2:
                    main_ids = get_color_ids_by_grade(main_grade)
                    main_color_id = st.selectbox("Main Color", main_ids, key="mail_main_id")
                    
                    sub_ids = get_color_ids_by_grade(sub_grade)
                    sub_color_id = st.selectbox("Sub Color", sub_ids, key="mail_sub_id")
                    
                    pattern_color_ids = get_color_ids_by_grade(pattern_color_grade)
                    pattern_color_id = st.selectbox("Pattern Color", pattern_color_ids, key="mail_pattern_color_id")
                    
                    pattern_ids = get_pattern_ids_by_grade(pattern_grade)
                    pattern_id = st.selectbox("Pattern", pattern_ids, key="mail_pattern_id")
                
                # 스킬 선택
                st.markdown("#### 스킬")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    acc1_enabled = st.checkbox("Accessory 1", value=True, key="mail_acc1_enabled")
                    if acc1_enabled:
                        acc1_grade = grade_selector("등급", "mail_acc1_grade")
                        acc1_ids = get_skill_ids_by_grade_and_slot(acc1_grade, 1)
                        acc1_id = st.selectbox("스킬", acc1_ids, format_func=lambda x: SKILL_MASTER[x]["name"], key="mail_acc1_id")
                
                with col2:
                    acc2_enabled = st.checkbox("Accessory 2", value=False, key="mail_acc2_enabled")
                    if acc2_enabled:
                        acc2_grade = grade_selector("등급", "mail_acc2_grade")
                        acc2_ids = get_skill_ids_by_grade_and_slot(acc2_grade, 2)
                        acc2_id = st.selectbox("스킬", acc2_ids, format_func=lambda x: SKILL_MASTER[x]["name"], key="mail_acc2_id")
                
                with col3:
                    acc3_enabled = st.checkbox("Accessory 3", value=False, key="mail_acc3_enabled")
                    if acc3_enabled:
                        acc3_grade = grade_selector("등급", "mail_acc3_grade")
                        acc3_ids = get_skill_ids_by_grade_and_slot(acc3_grade, 3)
                        acc3_id = st.selectbox("스킬", acc3_ids, format_func=lambda x: SKILL_MASTER[x]["name"], key="mail_acc3_id")
                
                instance_name = st.text_input("개체 이름", value="운영자 지급", key="mail_instance_name")
                
                if st.button("📤 개체 발송", use_container_width=True):
                    if not recipients:
                        st.error("❌ 수신자를 선택하세요.")
                    else:
                        # 개체 생성
                        instance = create_instance(
                            hp=hp, atk=atk, ms=ms,
                            main_color={"grade": main_grade, "id": main_color_id},
                            sub_color={"grade": sub_grade, "id": sub_color_id},
                            pattern_color={"grade": pattern_color_grade, "id": pattern_color_id},
                            pattern={"grade": pattern_grade, "id": pattern_id},
                            accessory_1={"grade": acc1_grade, "id": acc1_id} if acc1_enabled else None,
                            accessory_2={"grade": acc2_grade, "id": acc2_id} if acc2_enabled else None,
                            accessory_3={"grade": acc3_grade, "id": acc3_id} if acc3_enabled else None,
                            name=instance_name,
                            created_by="Admin"
                        )
                        
                        # 여러 명에게 우편 발송
                        success_count = 0
                        fail_count = 0
                        for recipient in recipients:
                            if send_mail(recipient, "instance", message, instance_data=instance):
                                success_count += 1
                            else:
                                fail_count += 1
                        
                        if fail_count == 0:
                            st.success(f"✅ {success_count}명에게 개체를 발송했습니다!")
                        else:
                            st.warning(f"⚠️ {success_count}명 성공, {fail_count}명 실패")
            
            else:  # 랜덤박스 지급
                st.markdown("#### 랜덤박스 선택")
                
                templates = load_box_templates(active_only=True)
                
                if not templates:
                    st.warning("활성화된 랜덤박스 템플릿이 없습니다. '랜덤박스 관리' 탭에서 생성하세요.")
                else:
                    template_options = {f"{t['name']} ({t['id']})": t['id'] for t in templates}
                    selected_template_label = st.selectbox(
                        "랜덤박스 템플릿",
                        list(template_options.keys()),
                        key="mail_box_template"
                    )
                    selected_template_id = template_options[selected_template_label]
                    
                    # 템플릿 정보 표시
                    selected_template = get_box_template(selected_template_id)
                    if selected_template:
                        st.info(f"**설명**: {selected_template.get('description', '없음')}")
                        
                        # 조건 요약
                        conditions = selected_template.get("conditions", {})
                        stat_ranges = conditions.get("stat_ranges", {})
                        
                        if stat_ranges:
                            st.write("**능력치 범위**:")
                            st.write(f"- HP: {stat_ranges.get('hp', {}).get('min', 0)} ~ {stat_ranges.get('hp', {}).get('max', 0)}")
                            st.write(f"- ATK: {stat_ranges.get('atk', {}).get('min', 0)} ~ {stat_ranges.get('atk', {}).get('max', 0)}")
                            st.write(f"- MS: {stat_ranges.get('ms', {}).get('min', 0)} ~ {stat_ranges.get('ms', {}).get('max', 0)}")
                    
                    if st.button("📤 랜덤박스 발송", use_container_width=True):
                        if not recipients:
                            st.error("❌ 수신자를 선택하세요.")
                        else:
                            # 여러 명에게 우편 발송
                            success_count = 0
                            fail_count = 0
                            for recipient in recipients:
                                if send_mail(recipient, "box", message, box_template_id=selected_template_id):
                                    success_count += 1
                                else:
                                    fail_count += 1
                            
                            if fail_count == 0:
                                st.success(f"✅ {success_count}명에게 랜덤박스를 발송했습니다!")
                            else:
                                st.warning(f"⚠️ {success_count}명 성공, {fail_count}명 실패")
    
    with tab7:
        st.markdown("### 🎁 랜덤박스 관리")
        
        subtab1, subtab2, subtab3 = st.tabs(["📋 템플릿 목록", "➕ 새 템플릿", "✏️ 템플릿 수정"])
        
        with subtab1:
            st.markdown("#### 등록된 랜덤박스 템플릿")
            
            templates = load_box_templates(active_only=False)
            
            if not templates:
                st.info("등록된 템플릿이 없습니다.")
            else:
                for template in templates:
                    with st.expander(f"{'✅' if template['is_active'] else '❌'} {template['name']} ({template['id']})"):
                        st.write(f"**설명**: {template.get('description', '없음')}")
                        st.write(f"**생성자**: {template.get('created_by', '?')}")
                        st.write(f"**생성일**: {template.get('created_at', '?')}")
                        st.write(f"**활성화**: {'예' if template['is_active'] else '아니오'}")
                        
                        # 조건 표시
                        conditions = template.get("conditions", {})
                        st.json(conditions)
                        
                        # 활성화/비활성화 토글
                        col1, col2 = st.columns(2)
                        with col1:
                            new_status = not template['is_active']
                            button_label = "🔴 비활성화" if template['is_active'] else "🟢 활성화"
                            if st.button(button_label, key=f"toggle_{template['id']}"):
                                if update_box_template(template['id'], is_active=new_status):
                                    st.success(f"✅ 템플릿이 {'활성화' if new_status else '비활성화'}되었습니다.")
                                    st.rerun()
                        
                        with col2:
                            if st.button("🗑️ 삭제", key=f"delete_{template['id']}"):
                                if delete_box_template(template['id']):
                                    st.success("✅ 템플릿이 삭제되었습니다.")
                                    st.rerun()
        
        with subtab2:
            st.markdown("#### 새 랜덤박스 템플릿 생성")
            
            box_name = st.text_input("박스 이름", key="new_box_name")
            box_desc = st.text_area("설명", key="new_box_desc")
            
            st.markdown("##### 능력치 범위")
            col1, col2 = st.columns(2)
            with col1:
                hp_min = st.number_input("HP 최소", min_value=1, value=20, key="new_hp_min")
                atk_min = st.number_input("ATK 최소", min_value=1, value=2, key="new_atk_min")
                ms_min = st.number_input("MS 최소", min_value=1, value=2, key="new_ms_min")
            with col2:
                hp_max = st.number_input("HP 최대", min_value=1, value=100, key="new_hp_max")
                atk_max = st.number_input("ATK 최대", min_value=1, value=10, key="new_atk_max")
                ms_max = st.number_input("MS 최대", min_value=1, value=10, key="new_ms_max")
            
            st.markdown("##### 외형 등급 제한")
            
            all_grades = ["Normal", "Rare", "Epic", "Unique", "Legendary", "Mystic"]
            
            main_color_grades = st.multiselect("Main Color 허용 등급", all_grades, default=["Normal", "Rare"], key="new_main_grades")
            sub_color_grades = st.multiselect("Sub Color 허용 등급", all_grades, default=["Normal", "Rare"], key="new_sub_grades")
            pattern_color_grades = st.multiselect("Pattern Color 허용 등급", all_grades, default=["Normal", "Rare"], key="new_pattern_color_grades")
            pattern_grades = st.multiselect("Pattern 허용 등급", all_grades, default=["Normal", "Rare"], key="new_pattern_grades")
            
            st.markdown("##### 스킬 등급 제한 (빈 선택 = 지급 안함)")
            
            acc1_grades = st.multiselect("Accessory 1 허용 등급", all_grades, default=["Normal"], key="new_acc1_grades")
            acc2_grades = st.multiselect("Accessory 2 허용 등급", all_grades, default=[], key="new_acc2_grades")
            acc3_grades = st.multiselect("Accessory 3 허용 등급", all_grades, default=[], key="new_acc3_grades")
            
            if st.button("➕ 템플릿 생성", use_container_width=True):
                if not box_name:
                    st.error("박스 이름을 입력하세요.")
                else:
                    new_template_id = f"box_{generate_id()[:8]}"
                    conditions = {
                        "stat_ranges": {
                            "hp": {"min": hp_min, "max": hp_max},
                            "atk": {"min": atk_min, "max": atk_max},
                            "ms": {"min": ms_min, "max": ms_max}
                        },
                        "grades": {
                            "main_color": main_color_grades,
                            "sub_color": sub_color_grades,
                            "pattern_color": pattern_color_grades,
                            "pattern": pattern_grades,
                            "accessory_1": acc1_grades if acc1_grades else None,
                            "accessory_2": acc2_grades if acc2_grades else None,
                            "accessory_3": acc3_grades if acc3_grades else None
                        }
                    }
                    
                    if create_box_template(new_template_id, box_name, box_desc, conditions, 
                                          created_by=st.session_state.username):
                        st.success(f"✅ 템플릿 '{box_name}'이 생성되었습니다! (ID: {new_template_id})")
                        st.rerun()
                    else:
                        st.error("❌ 템플릿 생성에 실패했습니다.")
        
        with subtab3:
            st.markdown("#### 템플릿 수정")
            
            templates = load_box_templates(active_only=False)
            
            if not templates:
                st.info("수정할 템플릿이 없습니다.")
            else:
                template_options = {f"{t['name']} ({t['id']})": t['id'] for t in templates}
                selected_edit_label = st.selectbox(
                    "수정할 템플릿",
                    list(template_options.keys()),
                    key="edit_box_template"
                )
                selected_edit_id = template_options[selected_edit_label]
                
                template = get_box_template(selected_edit_id)
                
                if template:
                    edit_name = st.text_input("박스 이름", value=template['name'], key="edit_box_name")
                    edit_desc = st.text_area("설명", value=template.get('description', ''), key="edit_box_desc")
                    
                    if st.button("💾 수정 저장", use_container_width=True):
                        if update_box_template(selected_edit_id, name=edit_name, description=edit_desc):
                            st.success("✅ 템플릿이 수정되었습니다.")
                            st.rerun()
                        else:
                            st.error("❌ 수정에 실패했습니다.")

def page_mailbox():
    """우편함 페이지"""
    st.title("📬 우편함")
    
    username = st.session_state.username
    
    # 우편 목록 로드
    mails = load_mailbox(username, unclaimed_only=True)
    
    if not mails:
        st.info("📭 받은 우편이 없습니다.")
        return
    
    st.write(f"**받은 우편: {len(mails)}개**")
    st.divider()
    
    # 우편 표시
    for mail in mails:
        mail_id = mail["id"]
        mail_type = mail["type"]
        message = mail.get("message", "")
        created_at = mail.get("created_at", "")
        
        with st.container():
            st.markdown(f"### 📨 {message}")
            st.caption(f"발송일: {created_at}")
            
            if mail_type == "instance":
                # 개체 직접 지급
                instance_data = mail.get("instance_data")
                if instance_data:
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        # 개체 미리보기 (SVG)
                        svg = render_instance_svg_cached(
                            instance_data["id"],
                            instance_data["appearance"]["main_color"]["id"],
                            instance_data["appearance"]["sub_color"]["id"],
                            instance_data["appearance"]["pattern_color"]["id"],
                            instance_data["appearance"]["pattern"]["id"],
                            size=150
                        )
                        st.markdown(svg, unsafe_allow_html=True)
                    
                    with col2:
                        st.write(f"**이름**: {instance_data.get('name', 'Unknown')}")
                        st.write(f"**전투력**: {format_korean_number(instance_data.get('power_score', 0))}")
                        st.write(f"**HP**: {format_korean_number(instance_data['stats']['hp'])}")
                        st.write(f"**ATK**: {format_korean_number(instance_data['stats']['atk'])}")
                        st.write(f"**MS**: {format_korean_number(instance_data['stats']['ms'])}")
                        
                        # 스킬 표시
                        skills_text = []
                        for i in range(1, 4):
                            acc_key = f"accessory_{i}"
                            if instance_data.get(acc_key):
                                skill_id = instance_data[acc_key]["id"]
                                skill_data = SKILL_MASTER.get(skill_id, {})
                                skills_text.append(f"[{skill_data.get('grade', '?')}] {skill_data.get('name', skill_id)}")
                        
                        if skills_text:
                            st.write(f"**스킬**: {', '.join(skills_text)}")
                    
                    # 수령 버튼
                    if st.button("📥 수령하기", key=f"claim_instance_{mail_id}", use_container_width=True):
                        claimed_mail = claim_mail(mail_id)
                        if claimed_mail:
                            # 개체 추가
                            st.session_state.instances.append(instance_data)
                            save_game_data()
                            st.success(f"✅ '{instance_data.get('name')}' 개체를 수령했습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 수령에 실패했습니다.")
            
            elif mail_type == "box":
                # 랜덤박스 지급
                box_template_id = mail.get("box_template_id")
                template = get_box_template(box_template_id)
                
                if template:
                    st.write(f"**박스 이름**: {template['name']}")
                    st.write(f"**설명**: {template.get('description', '랜덤박스')}")
                    
                    # 조건 요약 표시
                    conditions = template.get("conditions", {})
                    stat_ranges = conditions.get("stat_ranges", {})
                    
                    if stat_ranges:
                        st.write("**능력치 범위**:")
                        hp_range = stat_ranges.get("hp", {})
                        atk_range = stat_ranges.get("atk", {})
                        ms_range = stat_ranges.get("ms", {})
                        st.write(f"- HP: {hp_range.get('min', 0)} ~ {hp_range.get('max', 0)}")
                        st.write(f"- ATK: {atk_range.get('min', 0)} ~ {atk_range.get('max', 0)}")
                        st.write(f"- MS: {ms_range.get('min', 0)} ~ {ms_range.get('max', 0)}")
                    
                    # 개봉 버튼
                    if st.button("🎁 개봉하기", key=f"open_box_{mail_id}", use_container_width=True):
                        with st.spinner("박스를 개봉하는 중..."):
                            time.sleep(1)  # 애니메이션 효과
                            new_instance = open_random_box(box_template_id, created_by="Mailbox")
                            
                            if new_instance:
                                # 우편 수령 처리
                                claimed_mail = claim_mail(mail_id)
                                if claimed_mail:
                                    st.session_state.instances.append(new_instance)
                                    save_game_data()
                                    st.success(f"🎉 박스에서 '{new_instance['name']}'이(가) 나왔습니다!")
                                    st.balloons()
                                    
                                    # 획득한 개체 미리보기
                                    st.write("---")
                                    st.write("### 획득한 개체")
                                    col1, col2 = st.columns([1, 2])
                                    
                                    with col1:
                                        svg = render_instance_svg_cached(
                                            new_instance["id"],
                                            new_instance["appearance"]["main_color"]["id"],
                                            new_instance["appearance"]["sub_color"]["id"],
                                            new_instance["appearance"]["pattern_color"]["id"],
                                            new_instance["appearance"]["pattern"]["id"],
                                            size=150
                                        )
                                        st.markdown(svg, unsafe_allow_html=True)
                                    
                                    with col2:
                                        st.write(f"**전투력**: {format_korean_number(new_instance['power_score'])}")
                                        st.write(f"**HP**: {format_korean_number(new_instance['stats']['hp'])}")
                                        st.write(f"**ATK**: {format_korean_number(new_instance['stats']['atk'])}")
                                        st.write(f"**MS**: {format_korean_number(new_instance['stats']['ms'])}")
                                    
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error("❌ 수령에 실패했습니다.")
                            else:
                                st.error("❌ 박스 개봉에 실패했습니다.")
                else:
                    st.error(f"❌ 박스 템플릿을 찾을 수 없습니다: {box_template_id}")
            
            st.divider()

def page_dev():
    """개발자 메뉴"""
    st.title("🛠️ 개발자 메뉴")
    
    # 시즌 관리
    st.markdown("### 🏆 시즌 관리")
    season_data = load_season_history()
    current_season = season_data["current_season"]
    
    if current_season == "Preseason":
        season_display = "Preseason (1/16~1/18)"
    elif current_season == 0:
        season_display = "Beta"
    else:
        season_display = f"{current_season}"
    
    st.info(f"**현재 시즌: Season {season_display}**")
    
    # 시즌 0인 경우: 프리시즌 시작 버튼
    if current_season == 0:
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            st.info("🎯 시즌 0 → 프리시즌 (1/16~1/18)")
            st.caption("1등 유저 기록 후 프리시즌으로 전환 (데이터 유지)")
        with col_s2:
            if st.button("🎮 프리시즌 시작", type="primary", use_container_width=True):
                new_season = end_current_season(to_preseason=True)
                st.success(f"✅ Season 0 종료! Preseason 시작!")
                st.info("1등 유저의 챔피언 자격이 기록되었습니다.")
                time.sleep(2)
                st.rerun()
    
    # 프리시즌인 경우: 시즌 1 시작 버튼 (1/19 이후만 활성화)
    elif current_season == "Preseason":
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            # 한국 시간 기준
            current_date = datetime.now(KST).date()
            season1_start = datetime(2026, 1, 19, tzinfo=KST).date()
            if current_date < season1_start:
                st.warning(f"⏰ 시즌 1은 1/19부터 시작합니다 ({(season1_start - current_date).days}일 남음)")
            else:
                st.warning("⚠️ 시즌 1 시작 시 모든 유저 데이터가 초기화됩니다!")
                st.caption("단, Season 0 챔피언은 특전을 유지합니다.")
        with col_s2:
            button_disabled = datetime.now(KST).date() < season1_start
            if st.button("🏆 시즌 1 시작", type="primary", use_container_width=True, disabled=button_disabled):
                new_season = end_current_season(to_preseason=False)
                st.success(f"✅ Preseason 종료! Season 1 시작!")
                st.info("모든 유저가 로그아웃됩니다.")
                time.sleep(2)
                # 현재 사용자도 로그아웃
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
    
    # 정식 시즌인 경우: 일반 시즌 종료 버튼
    else:
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            st.warning("⚠️ 시즌 종료 시 모든 유저 데이터가 초기화됩니다!")
        with col_s2:
            if st.button("🔚 시즌 종료 및 초기화", type="primary", use_container_width=True):
                new_season = end_current_season(to_preseason=False)
                old_season_display = f"{current_season}"
                new_season_display = f"{new_season}"
                st.success(f"✅ Season {old_season_display} 종료! Season {new_season_display} 시작!")
                st.info("모든 유저가 로그아웃됩니다.")
                time.sleep(2)
                # 현재 사용자도 로그아웃
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
    
    st.markdown("---")
    
    # 돌연변이 보너스 설정
    st.markdown("### 🧬 돌연변이 시스템 설정")
    
    col1, col2 = st.columns(2)
    with col1:
        # 안전하게 범위 내 값으로 제한
        current_bonus = st.session_state.get("mutation_bonus", 0.0)
        if current_bonus < 0.0:
            current_bonus = 0.0
        elif current_bonus > 0.5:
            current_bonus = 0.5
            
        mutation_bonus = st.slider(
            "돌연변이 확률 보너스",
            min_value=0.0,
            max_value=0.5,
            value=current_bonus,
            step=0.05,
            help="교배 시 돌연변이 발생 확률에 추가됩니다. (예: 0.1 = +10%)"
        )
        if mutation_bonus != st.session_state.get("mutation_bonus", 0.0):
            st.session_state.mutation_bonus = mutation_bonus
            save_game_data()
            st.success(f"돌연변이 보너스: +{mutation_bonus*100:.0f}%")
    
    with col2:
        # 안전하게 범위 내 값으로 제한
        current_chain = st.session_state.get("max_chain_mutations", 3)
        if current_chain not in [3, 4, 5]:
            current_chain = 3
            
        max_chain = st.selectbox(
            "최대 연쇄 돌연변이 횟수",
            options=[3, 4, 5],
            index=[3, 4, 5].index(current_chain),
            help="교배 시 최대 몇 번까지 연쇄 돌연변이가 발생할 수 있는지 설정합니다."
        )
        if max_chain != st.session_state.get("max_chain_mutations", 3):
            st.session_state.max_chain_mutations = max_chain
            save_game_data()
            st.success(f"최대 연쇄: {max_chain}회")
    
    # 현재 설정 표시
    st.info(f"""
    **현재 돌연변이 설정**
    - 1차 돌연변이: {(0.50 * (1 + mutation_bonus))*100:.1f}%
    - 2차 연쇄: {(0.40 * (1 + mutation_bonus))*100:.1f}%
    - 3차 연쇄: {(0.20 * (1 + mutation_bonus))*100:.1f}%
    {f"- 4차 연쇄: {(0.10 * (1 + mutation_bonus))*100:.1f}% (활성)" if max_chain >= 4 else "- 4차 연쇄: 비활성"}
    {f"- 5차 연쇄: {(0.05 * (1 + mutation_bonus))*100:.1f}% (활성)" if max_chain >= 5 else "- 5차 연쇄: 비활성"}
    """)
    
    st.markdown("---")
    
    # 개체 수 제한 체크
    max_instances = st.session_state.get("max_instances", 200)
    if len(st.session_state.instances) >= max_instances:
        st.error(f"⚠️ 개체 목록이 최대 {max_instances}개를 초과했습니다. 일부 개체를 삭제해주세요.")
        st.info("🗑️ 개체 목록 페이지에서 일괄 삭제 기능을 사용하세요.")
        return
    
    st.markdown("### 커스텀 개체 생성")
    
    # 능력치
    st.markdown("**능력치**")
    col1, col2, col3 = st.columns(3)
    with col1:
        hp = st.number_input("HP", min_value=10, value=10)
    with col2:
        atk = st.number_input("ATK", min_value=1, value=1)
    with col3:
        ms = st.number_input("MS", min_value=1, value=1)
    
    # 색상 선택
    st.markdown("**색상**")
    
    color_options = {}
    for color_id, color_data in COLOR_MASTER.items():
        label = f"{color_data['name']} ({color_data['grade']}) - {color_id}"
        color_options[label] = color_id
    
    col1, col2, col3 = st.columns(3)
    with col1:
        main_color_label = st.selectbox("Main Color", list(color_options.keys()))
        main_color_id = color_options[main_color_label]
        main_color_grade = COLOR_MASTER[main_color_id]['grade']
    
    with col2:
        sub_color_label = st.selectbox("Sub Color", list(color_options.keys()))
        sub_color_id = color_options[sub_color_label]
        sub_color_grade = COLOR_MASTER[sub_color_id]['grade']
    
    with col3:
        pattern_color_label = st.selectbox("Pattern Color", list(color_options.keys()))
        pattern_color_id = color_options[pattern_color_label]
        pattern_color_grade = COLOR_MASTER[pattern_color_id]['grade']
    
    # 패턴 선택
    st.markdown("**패턴**")
    
    pattern_options = {}
    for pattern_id, pattern_data in PATTERN_MASTER.items():
        label = f"{pattern_data['layout']} ({pattern_data['grade']}) - {pattern_id}"
        pattern_options[label] = pattern_id
    
    pattern_label = st.selectbox("Pattern", list(pattern_options.keys()))
    pattern_id = pattern_options[pattern_label]
    pattern_grade = PATTERN_MASTER[pattern_id]['grade']
    
    # 악세서리 선택
    st.markdown("**악세서리**")
    
    # Slot 1
    acc1_options = {"None": None}
    for acc_id, acc_data in ACCESSORY_MASTER.items():
        if acc_data['slot'] == 1:
            label = f"{acc_data['name']} ({acc_data['grade']}) - {acc_id}"
            acc1_options[label] = acc_id
    
    acc1_label = st.selectbox("Accessory 1 (상단)", list(acc1_options.keys()))
    acc1_id = acc1_options[acc1_label]
    acc1 = {"grade": ACCESSORY_MASTER[acc1_id]['grade'], "id": acc1_id} if acc1_id else None
    
    # Slot 2
    acc2_options = {"None": None}
    for acc_id, acc_data in ACCESSORY_MASTER.items():
        if acc_data['slot'] == 2:
            label = f"{acc_data['name']} ({acc_data['grade']}) - {acc_id}"
            acc2_options[label] = acc_id
    
    acc2_label = st.selectbox("Accessory 2 (좌우)", list(acc2_options.keys()))
    acc2_id = acc2_options[acc2_label]
    acc2 = {"grade": ACCESSORY_MASTER[acc2_id]['grade'], "id": acc2_id} if acc2_id else None
    
    # Slot 3
    acc3_options = {"None": None}
    for acc_id, acc_data in ACCESSORY_MASTER.items():
        if acc_data['slot'] == 3:
            label = f"{acc_data['name']} ({acc_data['grade']}) - {acc_id}"
            acc3_options[label] = acc_id
    
    acc3_label = st.selectbox("Accessory 3 (하단)", list(acc3_options.keys()))
    acc3_id = acc3_options[acc3_label]
    acc3 = {"grade": ACCESSORY_MASTER[acc3_id]['grade'], "id": acc3_id} if acc3_id else None
    
    # 이름
    name = st.text_input("개체 이름", value="Custom")
    
    # 미리보기
    st.markdown("### 미리보기")
    preview_instance = {
        "id": "preview",
        "name": name,
        "is_locked": False,
        "is_favorite": False,
        "created_by": "Dev",
        "birth_time": datetime.now().isoformat(),
        "stats": {"hp": hp, "atk": atk, "ms": ms},
        "appearance": {
            "main_color": {"grade": main_color_grade, "id": main_color_id},
            "sub_color": {"grade": sub_color_grade, "id": sub_color_id},
            "pattern_color": {"grade": pattern_color_grade, "id": pattern_color_id},
            "pattern": {"grade": pattern_grade, "id": pattern_id}
        },
        "accessory_1": acc1,
        "accessory_2": acc2,
        "accessory_3": acc3,
        "mutation": {"count": 0, "fields": []}
    }
    
    display_instance_card(preview_instance, show_details=True)
    
    # 생성 버튼
    if st.button("✨ 개체 생성", use_container_width=True):
        new_instance = create_instance(
            hp=hp,
            atk=atk,
            ms=ms,
            main_color={"grade": main_color_grade, "id": main_color_id},
            sub_color={"grade": sub_color_grade, "id": sub_color_id},
            pattern_color={"grade": pattern_color_grade, "id": pattern_color_id},
            pattern={"grade": pattern_grade, "id": pattern_id},
            accessory_1=acc1,
            accessory_2=acc2,
            accessory_3=acc3,
            name=name,
            created_by="Dev"
        )
        st.session_state.instances.append(new_instance)
        save_game_data()
        st.success(f"✅ '{name}' 개체가 생성되었습니다!")
        time.sleep(1)
        st.rerun()

def page_login():
    """로그인 페이지"""
    # 시즌 정보 로드
    season_data = load_season_history()
    current_season = season_data["current_season"]
    
    # 시즌 표시 (0이면 Beta로 표시)
    season_display = "Beta" if current_season == 0 else f"{current_season}"
    
    st.markdown(f"""
        <div style="text-align: center; padding: 30px 0 20px 0;">
            <h1>🧬 Mutant Paint</h1>
            <p style="font-size: 1.2em; color: #666;">변이 개체 육성 시뮬레이터</p>
            <p style="font-size: 1.1em; color: #4CAF50; font-weight: bold;">⏱️ Season {season_display}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # 레이아웃: 왼쪽(로그인) + 오른쪽(명예의 전당)
    left_col, right_col = st.columns([1, 2])
    
    # 왼쪽: 로그인 폼
    with left_col:
        st.markdown("### 🔑 로그인")
        
        username = st.text_input(
            "이름",
            placeholder="이름을 입력하세요 (최대 20자)",
            key="login_username_input",
            max_chars=20
        )
        
        password = st.text_input(
            "비밀번호",
            type="password",
            placeholder="비밀번호를 입력하세요 (최대 50자)",
            key="login_password_input",
            max_chars=50
        )
        
        if st.button("게임 시작", use_container_width=True, type="primary"):
            if not username or not username.strip():
                st.error("이름을 입력해주세요!")
            elif len(username.strip()) < 2:
                st.error("이름은 최소 2자 이상이어야 합니다!")
            elif not password:
                st.error("비밀번호를 입력해주세요!")
            elif len(password) < 4:
                st.error("비밀번호는 최소 4자 이상이어야 합니다!")
            else:
                username = username.strip()
                
                # 신규 사용자인 경우 이름 안전성 검사
                if not user_exists(username):
                    is_safe, reason = check_content_safety(username)
                    if not is_safe:
                        st.error(f"❌ {reason}")
                        st.stop()
                
                # 사용자 존재 여부 확인
                if user_exists(username):
                    # 기존 사용자 - 비밀번호 확인
                    if verify_password(username, password):
                        # 로그인 성공
                        st.session_state.username = username
                        st.session_state.password_hash = hash_password(password)
                        
                        # 구 버전 데이터 마이그레이션 확인 및 즉시 업데이트
                        data = load_game_data(username)
                        if data and "password" in data and "password_hash" not in data:
                            # 구 버전 발견 - 즉시 해시로 마이그레이션
                            # init_session_state()가 호출되기 전에 파일 업데이트
                            data["password_hash"] = hash_password(password)
                            del data["password"]  # 평문 제거
                            
                            # 파일에 즉시 저장
                            save_file = get_user_save_file(username)
                            create_backup(save_file)
                            temp_fd, temp_path = tempfile.mkstemp(dir="saves", suffix=".tmp")
                            try:
                                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                                    if acquire_file_lock(f, timeout=5.0):
                                        try:
                                            json.dump(data, f, ensure_ascii=False, indent=2)
                                            f.flush()
                                            os.fsync(f.fileno())
                                        finally:
                                            release_file_lock(f)
                                os.replace(temp_path, save_file)
                            except:
                                if os.path.exists(temp_path):
                                    try:
                                        os.remove(temp_path)
                                    except:
                                        pass
                        
                        st.success("로그인 성공!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("비밀번호가 일치하지 않습니다!")
                else:
                    # 신규 사용자 - 계정 생성
                    password_hash = hash_password(password)
                    
                    # DB에 사용자 생성 시도
                    success = create_user(username, password_hash)
                    
                    if success:
                        # 세션 상태 설정
                        st.session_state.username = username
                        st.session_state.password_hash = password_hash
                        st.success(f"'{username}' 계정이 생성되었습니다!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        # 사용자가 이미 존재할 가능성 확인 (동시성 문제)
                        if user_exists(username):
                            st.error("이미 존재하는 사용자명입니다. 다른 이름을 사용하거나 올바른 비밀번호를 입력해주세요.")
                        else:
                            st.error("계정 생성 중 오류가 발생했습니다. 다시 시도해주세요.")
        
        st.markdown("---")
        st.markdown("""
            <div style="text-align: center; color: #888; font-size: 0.85em; padding: 10px;">
                💡 팁: 신규 사용자는 자동으로 계정이 생성됩니다<br/>
                기존 사용자는 올바른 비밀번호를 입력해야 합니다
            </div>
        """, unsafe_allow_html=True)
        
        # 디스코드 링크
        st.markdown("---")
        st.markdown("### 💬 커뮤니티")
        st.markdown("""
        <a href='https://discord.gg/eS2kJ2Zz7Z' target='_blank' 
           style='display: block; width: 100%; padding: 0.5rem 0.75rem; 
                  background-color: #5865F2; color: white; text-decoration: none; 
                  border-radius: 0.375rem; text-align: center;
                  font-size: 1rem; font-weight: 500; box-sizing: border-box;'>
            💬 디스코드 참여하기
        </a>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <div style="text-align: center; color: #888; font-size: 0.8em; padding: 10px; margin-top: 10px;">
                질문, 공략, 친목 등 모두 환영합니다!
            </div>
        """, unsafe_allow_html=True)
        
        # 간단한 게임 소개
        st.markdown("---")
        st.markdown("### 📖 게임 소개")
        with st.expander("🧬 Mutant Paint란?"):
            st.markdown("""
            **변이 개체 육성 시뮬레이터**
            
            - 🎨 색상, 패턴, 스킬을 조합해 독특한 개체 생성
            - 🧬 두 개체를 믹스하여 새로운 돌연변이 발견
            - ⚔️ 전투로 다른 플레이어와 경쟁
            - 🏆 시즌제 랭킹 시스템
            - 📖 도감 수집 (색상, 패턴, 스킬)
            
            **목표:** 최강의 개체를 육성하고 시즌 1위를 달성하세요!
            """)
    
    # 오른쪽: 지난 시즌 명예의 전당
    with right_col:
        if season_data["history"]:
            last_season = season_data["history"][-1]
            last_season_display = "Beta" if last_season['season'] == 0 else f"{last_season['season']}"
            st.markdown(f"### 🏆 Season {last_season_display} 명예의 전당")
            
            if last_season["top3"]:
                # 3명을 가로로 나란히 배치
                hall_cols = st.columns(3)
                medals = ["🥇", "🥈", "🥉"]
                
                for idx, user_data in enumerate(last_season["top3"][:3]):
                    with hall_cols[idx]:
                        # 메달과 순위
                        st.markdown(f"<div style='text-align: center; font-size: 2em;'>{medals[idx]}</div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='text-align: center; font-weight: bold; font-size: 1.1em; margin-bottom: 10px;'>{user_data['username']}</div>", unsafe_allow_html=True)
                        
                        # 대표 개체 정보
                        rep_inst = user_data.get("instance") or user_data.get("representative")
                        if rep_inst:
                            # SVG 렌더링 (중앙 정렬)
                            svg = get_instance_svg(rep_inst, size=100)
                            st.markdown(f"<div style='text-align: center;'>{svg}</div>", unsafe_allow_html=True)
                            
                            # 이름과 전투력
                            st.markdown(f"<div style='text-align: center; font-weight: bold; margin-top: 8px;'>{rep_inst['name']}</div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='text-align: center; color: #4CAF50; font-size: 0.9em;'>💪 {format_korean_number(user_data['power_score'])}</div>", unsafe_allow_html=True)
                            
                            # 스탯 (작게 표시)
                            st.markdown(f"""
                                <div style='text-align: center; font-size: 0.85em; color: #888; margin-top: 5px;'>
                                    HP {rep_inst["stats"]["hp"]:,} | ATK {rep_inst["stats"]["atk"]:,} | MS {rep_inst["stats"]["ms"]:,}
                                </div>
                            """, unsafe_allow_html=True)
            else:
                st.info("아직 시즌 기록이 없습니다.")
        else:
            st.markdown("### 🏆 명예의 전당")
            st.info("첫 시즌입니다! 우승을 향해 도전하세요!")

def main():
    """메인 함수"""
    st.set_page_config(
        page_title="Mutant Paint",
        page_icon="🧬",
        layout="wide"
    )
    
    init_session_state()
    
    # 로그인 체크
    if not st.session_state.username:
        page_login()
        return
    
    # 상단에 사용자 정보와 대표 유닛, 로그아웃 버튼
    col1, col2, col3 = st.columns([3, 5, 2])
    with col1:
        st.markdown(f"### 👤 {st.session_state.username}")
        # 홈이 아닌 페이지에서만 홈으로 버튼 표시
        if st.session_state.page != "home":
            if st.button("🏠 홈으로", key="home_button_top"):
                st.session_state.page = "home"
                st.rerun()
    with col2:
        # 대표 유닛 표시
        rep_id = st.session_state.get("representative_id")
        if rep_id:
            rep_inst = next((inst for inst in st.session_state.instances if inst["id"] == rep_id), None)
            if rep_inst:
                st.markdown("**👑 대표 유닛**")
                rep_col1, rep_col2 = st.columns([1, 3])
                with rep_col1:
                    # SVG 이미지
                    svg = get_instance_svg(rep_inst, size=80)
                    st.markdown(svg, unsafe_allow_html=True)
                with rep_col2:
                    st.markdown(f"**{rep_inst['name']}**")
                    rep_stats_col1, rep_stats_col2, rep_stats_col3 = st.columns(3)
                    with rep_stats_col1:
                        st.metric("HP", f"{rep_inst['stats']['hp']:,}", label_visibility="visible")
                    with rep_stats_col2:
                        st.metric("ATK", rep_inst["stats"]["atk"], label_visibility="visible")
                    with rep_stats_col3:
                        st.metric("MS", rep_inst["stats"]["ms"], label_visibility="visible")
            else:
                st.session_state.representative_id = None
                st.markdown("**👑 대표 유닛:** 미설정")
        else:
            st.markdown("**👑 대표 유닛:** 미설정")
    with col3:
        if st.button("로그아웃", use_container_width=True):
            # 세션 상태 초기화
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        # 디스코드 링크
        st.markdown("""
        <a href='https://discord.gg/eS2kJ2Zz7Z' target='_blank' 
           style='display: block; width: 100%; padding: 0.375rem 0.75rem; 
                  background-color: #5865F2; color: white; text-decoration: none; 
                  border-radius: 0.375rem; text-align: center; margin-top: 0.5rem;
                  font-size: 1rem; font-weight: 400; box-sizing: border-box;'>
            💬 디스코드
        </a>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 페이지 라우팅
    if st.session_state.page == "home":
        page_home()
    elif st.session_state.page == "list":
        page_list()
    elif st.session_state.page == "bulk_delete":
        page_bulk_delete()
    elif st.session_state.page == "breed":
        page_breed()
    elif st.session_state.page == "battle":
        page_battle()
    elif st.session_state.page == "random_box":
        page_random_box()
    elif st.session_state.page == "collection":
        page_collection()
    elif st.session_state.page == "ranking":
        page_ranking()
    elif st.session_state.page == "season_info":
        page_season_info()
    elif st.session_state.page == "mailbox":
        page_mailbox()
    elif st.session_state.page == "admin":
        page_admin()
    elif st.session_state.page == "dev":
        page_dev()

if __name__ == "__main__":
    main()
