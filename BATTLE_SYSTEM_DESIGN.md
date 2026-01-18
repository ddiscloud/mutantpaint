# 전투 시스템 구현 문서

## 📋 개요

**Mutant Paint 전투 시스템**은 1:1 턴제 자동 전투로, 두 개체가 스킬과 능력치를 활용해 대결합니다. **ATB(Active Time Battle) 게이지 시스템**으로 행동 순서가 결정되며, 각 개체는 3개의 스킬 슬롯을 보유합니다.

> **주의**: 이 문서는 실제 구현된 시스템을 설명합니다. 미구현 기능은 별도 표시됩니다.

---

## ⚔️ 1. 전투 기본 구조

### 1.1 전투 참가자
- **아군(Player)**: 사용자가 선택한 개체
- **적군(Enemy)**: AI 또는 다른 사용자의 개체

### 1.2 개체 능력치
- **HP (체력)**: 전투 중 체력, 0이 되면 패배
- **ATK (공격력)**: 기본 공격 데미지
- **MS (이동속도)**: 행동 순서 결정, 높을수록 유리

### 1.3 스킬 슬롯
- **슬롯 1**: 체력 회복 스킬 (34종)
- **슬롯 2**: 공격력 증가 스킬 (34종)
- **슬롯 3**: MS/유틸 스킬 (34종)
- **총 102개 스킬** (data/skills.json)

---

## 🔄 2. 전투 흐름

``` (Battle.__init__)
    ↓
초기화 (HP, 게이지=0, 쿨다운=0, 버프=[], 디버프=[])
    ↓
┌─── 턴 실행 (execute_turn)
│      ↓
│   ATB 게이지 증가 (tick_and_get_next_actor)
│   - 플레이어 게이지 += MS
│   - 적군 게이지 += MS
│   - 임계값 도달 시 행동
│      ↓
│   행동자 결정 (게이지가 임계값 이상인 개체)
│      ↓
│   턴 시작 효과 (Regen 등)
│      ↓
│   스킬 사용 (쿨다운 체크 → AI 선택)
│      ↓
│   기본 공격 (항상 실행)
│      ↓
│   버프/디버프 지속시간 감소
│      ↓
│   승패 판정 (HP ≤ 0 or 턴 ≥ 50)
│      ↓
└── 다음 행동자 (승패 미결정 시)
    ↓
전투 종료 (check_victory)
    ↓
보상 지급 (스테이지 클리어 시)
보상 지급
```

---

## 🎯 3. ATB 게이지 시스템 (실제 구현)

### 3.1 게이지 작동 방식

**행동 임계값**: 플레이어 MS + 적군 MS
- 예: 플레이어 MS 10, 적군 MS 5 → 임계값 = 15

**게이지 증가**:
```python
while True:
    player.speed_gauge += player.current_ms
    enemy.speed_gauge += enemy.current_ms
    
    # 임계값 도달 시 행동
    if player.speed_gauge >= threshold:
        player.speed_gauge -= threshold
        return player  # 플레이어 행동
    
    if enemy.speed_gauge >= threshold:
        enemy.speed_gauge -= threshold
        return enemy  # 적군 행동
```

### 3.2 행동 순서 결정

- **게이지가 먼저 임계값 도달** → 해당 개체 행동
- **동시 도달 시** → 게이지가 더 높은 쪽 우선
- **게이지도 동일 시** → 랜덤 선택

### 3.3 MS 효과

| MS 비율 | 효과 |
|---------|------|
| 2배 | 약 2배 빈도로 행동 |
| 3배 | 약 3배 빈도로 행동 |
| 10배 | 약 10배 빈도로 행동 |

**실제 예시**:
```
플레이어 MS: 10, 적군 MS: 5 (임계값 = 15)

턴 1: P=10, E=5  → P=20, E=10 → P 행동 (P=5, E=10)
턴 2: P=15, E=15 → P 행동 (P=0, E=15) [동시 도달, 플레이어 우선]
턴 3: P=10, E=20 → E 행동 (P=10, E=5)
턴 4: P=20, E=10 → P 행동 (P=5, E=10)
...
```

---

## 🎮 4. 행동 시스템

### 4.1 행동 단계

각 개체의 턴은 다음 순서로 진행됩니다:

1. **턴 시작 효과 발동**
   - 지속 회복/피해 적용
   - 버프/디버프 효과 적용

2. **스킬 선택 (AI)**
   - 사용 가능한 스킬 중 선택
   - 쿨다운 중인 스킬은 제외
   - 우선순위 시스템 적용

3. **스킬 발동**
   - 효과 적용
   - 쿨다운 시작

4. **기본 공격**
   - ATK 기반 데미지
   - 스킬 효과와 별개로 항상 실행

5. **턴 종료 효과**
   - 버프/디버프 지속시간 -1
   - 쿨다운 -1

### 4.2 스킬 선택 AI 우선순위

#### 슬롯 1 (회복 스킬)
```python
if HP < 30%:
    우선순위: 최상
elif HP < 60%:
    우선순위: 높음
else:
    우선순위: 낮음
```

#### 슬롯 2 (공격 스킬)
```python
if 적 HP < 40%:
    우선순위: 최상 (피니셔)
elif 적 HP > 80%:
    우선순위: 높음 (딜 극대화)
else:
    우선순위: 중간
```

#### 슬롯 3 (MS/유틸 스킬)
```python
ms_ratio = 적_MS / 아군_MS  # 적이 빠른 정도

if ms_ratio > 1.2:
    우선순위: 최상 (선공 확보 필요)
elif ms_ratio > 1.0:
    우선순위: 높음
elif "회피" in 스킬_효과:
    우선순위: 중간
else:
    우선순위: 낮음
```

### 4.3 기본 공격 데미지 계산

```python
base_damage = ATK * (0.8 ~ 1.2)  # ±20% 랜덤
final_damage = base_damage * (1 + 공격_버프) * (1 - 방어_버프)
actual_damage = max(1, final_damage)  # 최소 1 데미지
```

---

## 🛡️ 5. 버프/디버프 시스템

### 5.1 버프 종류

| 버프 타입 | 설명 | 중첩 |
|----------|------|------|
| ATK 증가 | 공격력 % 증가 | 가산 |
| 방어 증가 | 받는 피해 % 감소 | 가산 |
| MS 증가 | 이동속도 +N | 가산 |
| 지속 회복 | 매턴 HP % 회복 | 가산 |
| 반사 | 받은 피해 % 반사 | 최대값 |
| 회피 | 공격 회피 확률 % | 최대값 |
| 무적 | 모든 피해 무효 | 불가 |
| 치명타 | 데미지 배율 증가 | 곱연산 |

### 5.2 디버프 종류

| 디버프 타입 | 설명 | 중첩 |
|-----------|------|------|
| ATK 감소 | 공격력 % 감소 | 가산 |
| 방어 감소 | 받는 피해 % 증가 | 가산 |
| MS 감소 | 이동속도 -N | 가산 |
| 지속 피해 | 매턴 HP % 피해 | 가산 |
| 행동 불가 | 스킬/공격 불가 | 불가 |
| 힐 차단 | 회복 효과 % 감소 | 가산 |

### 5.3 버프/디버프 관리

- **지속시간**: 턴 종료 시 -1
- **중첩**: 타입별 규칙에 따름
- **제거**: 특정 스킬로 디버프 해제 가능
- **최대/최소 제한**: ATK ±90%, 방어 ±90%

---

## ⏱️ 6. 쿨다운 시스템

### 6.1 기본 규칙
- 스킬 사용 시 쿨다운 시작
- 매 턴 종료 시 쿨다운 -1
- 쿨다운 0이 되면 사용 가능
- 전투 시작 시 모든 스킬 즉시 사용 가능

### 6.2 쿨다운 특수 효과
- **쿨다운 감소 스킬**: 모든 쿨다운 -N턴
- **쿨다운 초기화**: 특정 스킬의 쿨다운 0으로
- **쿨다운 무시**: 1회 쿨다운 관계없이 사용

### 6.3 Mystic 스킬 제한
- **전투당 1회 제한** (쿨다운 무관)
- 사용 시 해당 전투에서 다시 사용 불가
- 쿨다운 초기화 효과도 적용 안됨

---

## 🏆 7. 승패 판정

### 7.1 승리 조건
1. **적 HP 0 이하**: 아군 승리
2. **아군 HP 0 이하**: 아군 패배
3. **50턴 초과**: 남은 HP% 비교
4. **동시 사망**: 무승부

### 7.2 HP% 계산 (타임아웃 시)
```python
hp_percent = (current_hp / max_hp) * 100
if 아군_hp% > 적군_hp%:
    아군 승리
elif 아군_hp% < 적군_hp%:
    아군 패배
else:
    무승부
```

---

## 🎁 8. 보상 시스템

### 8.1 승리 보상
- **배틀 포인트 (BP)**: 50-200 BP
- **경험치**: 개체 레벨 시스템 (향후 확장)
- **랜덤박스 티켓**: 낮은 확률 (5%)

### 8.2 BP 계산식
```python
base_bp = 100
difficulty_multiplier = 적_총스탯 / 아군_총스탯
turn_bonus = max(0, 50 - 전투_턴수) * 2
mystic_bonus = 적_mystic_스킬_개수 * 50

final_bp = base_bp * difficulty_multiplier + turn_bonus + mystic_bonus
```

### 8.3 연승 보너스
- **2연승**: +10% BP
- **5연승**: +25% BP
- **10연승**: +50% BP
- **패배 시**: 연승 초기화

---

## 🎨 9. UI/UX 설계

### 9.1 전투 화면 레이아웃

```
┌─────────────────────────────────────────────┐
│  [아군]                         [적군]       │
│   HP: ████████░░ 80%   HP: ██████████ 100%  │
│   ATK: 15              ATK: 12               │
│   MS: 8                MS: 5                 │
│                                              │
│   [스킬1] [스킬2] [스킬3]                     │
│   쿨:3턴  쿨:0턴  쿨:1턴                      │
│                                              │
│  ┌─────────── 전투 로그 ─────────────┐       │
│  │ 턴 5: 아군이 "Fury" 사용!        │       │
│  │ ATK +25% (5턴 지속)              │       │
│  │ 아군이 적에게 18 데미지!         │       │
│  │ 적 HP: 62 → 44                   │       │
│  │                                  │       │
│  │ 턴 5: 적이 "Greater Heal" 사용!  │       │
│  │ 적 HP 25% 회복!                  │       │
│  └──────────────────────────────────┘       │
│                                              │
│  [⏸️ 일시정지]  [⏩ 빠르게]  [⏭️ 스킵]      │
└─────────────────────────────────────────────┘
```

### 9.2 전투 속도 옵션
- **1배속**: 각 행동 1초 간격
- **2배속**: 각 행동 0.5초 간격
- **4배속**: 각 행동 0.25초 간격
- **결과만 보기**: 즉시 결과 표시

### 9.3 전투 로그
- 최근 20개 행동 표시
- 스킬 사용, 데미지, 회복 등 모든 행동 기록
- 색상 코딩: 공격(빨강), 회복(초록), 버프(파랑)

---

## 🤖 10. AI 전투 알고리즘

### 10.1 스킬 선택 로직

```python
def select_skill(self, enemy):
    available_skills = self.get_available_skills()
    priorities = []
    
    for skill in available_skills:
        priority = 0
        
        # HP 기반 우선순위
        if skill.slot == 1:  # 회복 스킬
            if self.hp_percent < 30:
                priority += 100
            elif self.hp_percent < 60:
                priority += 50
            else:
                priority += 10
        
        elif skill.slot == 2:  # 공격 스킬
            if enemy.hp_percent < 40:
                priority += 80  # 마무리
            elif enemy.hp_percent > 80:
                priority += 60
            ms_ratio = enemy.ms / self.ms if self.ms > 0 else 999
            if ms_ratio > 1.5:
                priority += 90  # 매우 느림, 선공 확보 필수
            elif ms_ratio > 1.2:
                priority += 70  # 느림, 선공 확보 필요
            elif ms_ratio > 1.0:
                priority += 50  # 약간 느림
            elif "dodge" in skill.effect:
                priority += 40
            else:
                priority += 20  # 선공 확보
            elif "dodge" in skill.effect:
                priority += 50
            else:
                priority += 30
        
        # 등급 보너스
        grade_bonus = {
            "Normal": 5, "Rare": 10, "Epic": 15,
            "Unique": 20, "Legendary": 25, "Mystic": 30
        }
        priority += grade_bonus.get(skill.grade, 0)
        
        # 랜덤 요소 (±10)
        priority += random.randint(-10, 10)
        
        priorities.append((skill, priority))
    
    # 가장 높은 우선순위 스킬 선택
    priorities.sort(key=lambda x: x[1], reverse=True)
    return priorities[0][0] if priorities else None
```

### 10.2 전략 패턴

#### 공격형 (ATK 높음)
- 공격 스킬 우선
- 회복은 최소한만

#### 방어형 (HP 높음)
- 회복 스킬 우선
- 장기전 지향

#### 속도형 (MS 높음)
- 유틸 스킬로 선공 유지
- 연속 타격

---

## 📊 11. 전투 모드

### 11.1 PvE 모드

#### 스토리 배틀
- 고정된 적 개체
- 난이도별 구성
- 클리어 보상

#### 랜덤 배틀
- 랜덤 생성된 적
- 난이도 선택 가능
- 무한 도전

### 11.2 PvP 모드 (향후 확장)

#### 실시간 대전
- 다른 플레이어와 대결
- 랭킹 시스템
- 시즌 보상

#### 비동기 대전
- 상대방 AI가 대신 전투
- 방어 덱 설정
- 공격/방어 기록

### 11.3 토너먼트 모드 (향후 확장)
- 8강/16강 토너먼트
- 단일 패배 탈락
- 우승 보상

---

## 🎮 12. 전투 준비 시스템

### 12.1 개체 선택
- 보유 개체 목록 표시
- 능력치/스킬 정보 확인
- 최대 3개 덱 저장 가능

### 12.2 적 선택/생성
- **랜덤 생성**: AI가 능력치 범위 내 생성
- **특정 개체**: 저장된 적 선택
- **난이도 조절**: Easy / Normal / Hard

### 12.3 배틀 프리셋
```json
{
  "easy": {
    "stat_range": "50-80% of player",
    "skill_grade": "mostly Normal/Rare",
    "ai_intelligence": "basic"
  },
  "normal": {
    "stat_range": "80-120% of player",
    "skill_grade": "balanced",
    "ai_intelligence": "standard"
  },
  "hard": {
    "stat_range": "120-150% of player",
    "skill_grade": "mostly Epic/Unique",
    "ai_intelligence": "advanced"
  }
}
```

---

## 🔧 13. 특수 메커니즘

### 13.1 콤보 시스템
- 연속 공격 시 콤보 카운터 증가
- 콤보마다 데미지 +5% (최대 +50%)
- 피격 시 콤보 초기화

### 13.2 분노 게이지
- 피해 받을 때마다 증가
- 100% 도달 시 "분노 폭발"
  - 다음 공격 데미지 2배
  - ATK +30% (3턴)
  - 게이지 초기화

### 13.3 크리티컬 시스템
- 기본 크리티컬 확률: 5%
- 크리티컬 데미지: 1.5배
- 특정 스킬로 확률 증가 가능

---

## 📈 14. 밸런스 조정 가이드

### 14.1 등급별 전투력

| 등급 | 스킬 영향력 | 권장 쿨다운 | 전투 기여도 |
|------|-------------|-------------|-------------|
| Normal | 10-20% | 2-5턴 | 기본 |
| Rare | 20-35% | 4-6턴 | 1.5배 |
| Epic | 35-50% | 6-10턴 | 2배 |
| Unique | 50-80% | 8-15턴 | 3배 |
| Legendary | 70-100% | 15-20턴 | 5배 |
| Mystic | 80-150% | 전투당 1회 | 10배 |

### 14.2 능력치 밸런스
```
스탯 범위: 무한 성장 가능

실제 유저 스탯 예시:
HP: 520 ~ 2,080
ATK: 70 ~ 288
MS: 54 ~ 209

권장 비율:
HP : ATK = 10 : 1 (돌연변이 설계로 자연스럽게 유지됨)
MS: 독립적 성장 (비율 기반 전투 시스템으로 해결)
```

### 14.3 전투 길이 목표
- **빠른 전투**: 5-10턴
- **일반 전투**: 10-20턴
- **긴 전투**: 20-40턴
- **최대 길이**: 50턴 (타임아웃)

---

## 🎯 15. 전투 통계

### 15.1 개체별 전적
- 총 전투 횟수
- 승/패/무 기록
- 승률
- 평균 턴 수
- 평균 데미지
- 스킬 사용 통계

### 15.2 사용자별 전적
- 총 전투 횟수
- 전체 승률
- 최고 연승
- 획득 BP 합계
- 즐겨 사용하는 개체

---

## 🚀 16. 구현 단계

### Phase 1: 기본 전투 시스템
- [x] 스킬 데이터 정의
- [ ] 전투 로직 구현
- [ ] 턴 순서 시스템
- [ ] 기본 AI

### Phase 2: 스킬 효과 구현
- [ ] 슬롯 1 스킬 (34개)
- [ ] 슬롯 2 스킬 (34개)
- [ ] 슬롯 3 스킬 (34개)
- [ ] 버프/디버프 시스템

### Phase 3: UI/UX
- [ ] 전투 화면
- [ ] 애니메이션
- [ ] 전투 로그
- [ ] 결과 화면

### Phase 4: 보상 및 통계
- [ ] BP 시스템
- [ ] 전적 기록
- [ ] 랭킹 시스템

### Phase 5: 확장 콘텐츠
- [ ] PvP 모드
- [ ] 토너먼트
- [ ] 특수 이벤트 배틀

---

## 📝 17. 코드 구조 설계

### 17.1 클래스 구조
```python
class BattleInstance:
    """전투용 개체 (임시 스탯 보관)"""
    original_instance: Dict
    current_hp: int
    current_atk: int
    current_ms: int
    buffs: List[Buff]
    debuffs: List[Debuff]
    cooldowns: Dict[int, int]  # {slot: remaining_turns}
    mystic_used: Set[int]  # 사용한 Mystic 스킬 슬롯

class Skill:
    """스킬 정의"""
    id: str
    slot: int
    grade: str
    name: str
    effect_type: str
    values: Dict
    cooldown: int
    is_mystic: bool

class Buff/Debuff:
    """버프/디버프"""
    type: str
    value: float
    duration: int

class Battle:
    """전투 매니저"""
    player: BattleInstance
    enemy: BattleInstance
    turn: int
    log: List[str]
    
    def start()
    def execute_turn()
    def select_action(instance)
    def apply_skill(skill, caster, target)
    def basic_attack(attacker, defender)
    def check_victory()
    def get_result()
```

---

**문서 버전**: 1.0  
**최종 수정일**: 2026년 1월 15일  
**연관 문서**: SYSTEM_DESIGN.md, 스킬 설계서
