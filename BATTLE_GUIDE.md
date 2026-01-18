# 전투 시스템 구현 문서

실제 구현된 전투 시스템을 설명합니다.

## 📋 개요

- **1:1 턴제 자동 전투**
- **ATB 게이지 시스템** (MS 기반 행동 순서)
- **102개 스킬** (슬롯당 34개)
- **스테이지 모드** (난이도 상승)

---

## 🎯 ATB 게이지 시스템

### 게이지 작동 방식

**행동 임계값** = 플레이어 MS + 적군 MS

```python
while not victory:
    player.gauge += player.ms
    enemy.gauge += enemy.ms
    
    if player.gauge >= threshold:
        player.gauge -= threshold
        player.act()
    
    if enemy.gauge >= threshold:
        enemy.gauge -= threshold
        enemy.act()
```

### 행동 빈도

| MS 비율 | 행동 빈도 |
|---------|----------|
| 1:1 | 동일 |
| 2:1 | 2배 |
| 3:1 | 3배 |
| 10:1 | 10배 |

**예시**:
- 플레이어 MS 10, 적 MS 5 → 플레이어가 약 2배 자주 행동
- 플레이어 MS 20, 적 MS 2 → 플레이어가 약 10배 자주 행동

---

## ⚔️ 턴 구조

```
행동자 결정 (ATB 게이지)
  ↓
버프 적용 (ATK, MS 재계산)
  ↓
Regen 회복 (있는 경우)
  ↓
스턴 체크 → 행동 불가
  ↓
스킬 사용 (AI 선택)
  ↓
기본 공격 (항상 실행)
  ↓
버프/쿨다운 -1
```

---

## 🎮 AI 스킬 선택

```python
def select_skill(attacker):
    available = [스킬 for 스킬 in [1,2,3] 
                 if cooldown[스킬] == 0]
    
    if HP < 30%:
        return 슬롯1  # 회복 우선
    else:
        return random.choice([슬롯2, 슬롯3])  # 공격/유틸
```

---

## 💥 데미지 계산

```python
base_dmg = ATK × random(0.8, 1.2)

# 방어 적용
final_dmg = base_dmg × (1.0 - def_buff + def_debuff)

# 회피 체크
if random() < dodge:
    데미지 0

# 반사
if counter:
    attacker_hp -= final_dmg × counter_value
```

---

## 🏆 승패 조건

1. **HP ≤ 0** → 즉시 패배
2. **50턴 초과** → 타임아웃 패배
3. **적 HP ≤ 0** → 승리

---

## 🎁 스테이지 시스템

### 난이도 계산

```python
stage 1:  HP=90,  ATK=15,  MS=8
stage 2:  HP=120, ATK=20,  MS=10
stage 3:  HP=160, ATK=26,  MS=12
...
```

**공식**:
- HP = 60 + stage × 30
- ATK = 10 + stage × 5  
- MS = 6 + stage × 2

### 보상

- 스테이지 클리어 시 랜덤 개체 획득
- 능력치와 스킬은 스테이지 난이도 기반

---

## 🔧 주요 클래스

### Battle
```python
class Battle:
    def __init__(player, enemy):
        # 초기화
    
    def tick_and_get_next_actor():
        # ATB 게이지 처리
    
    def execute_turn():
        # 턴 실행
    
    def check_victory():
        # 승패 판정
```

### BattleInstance
```python
class BattleInstance:
    max_hp: int
    current_hp: int
    base_atk: int
    current_atk: int
    base_ms: int
    current_ms: int
    
    speed_gauge: int  # ATB 게이지
    cooldowns: {1: 0, 2: 0, 3: 0}
    buffs: []
    debuffs: []
```

---

## 📊 구현된 스킬 효과

### 슬롯 1 (회복)
- `heal`: HP 회복
- `regen`: 지속 회복
- `drain`: HP 흡수
- `heal_def`: 회복 + 방어 버프

### 슬롯 2 (공격)
- `atk_buff`: 공격력 증가
- `multi_hit`: 연속 공격
- `def_break`: 적 방어 감소
- `crit_chance`: 치명타 확률

### 슬롯 3 (유틸)
- `ms_buff`: MS 증가
- `dodge`: 회피
- `counter`: 반격
- `reflect`: 피해 반사

**총 102개 스킬** - [data/skills.json](data/skills.json)

---

## 🚀 미구현 기능

- [ ] PVP 대전
- [ ] 실시간 멀티플레이
- [ ] 토너먼트
- [ ] 리플레이 시스템
