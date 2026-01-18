# 마스터 데이터 관리 가이드

## 개요

게임의 마스터 데이터(색상, 패턴, 스킬)가 코드에서 분리되어 JSON 파일로 관리됩니다.
이제 코드 수정 없이 데이터 파일만 편집하여 새로운 컨텐츠를 추가할 수 있습니다.

## 파일 구조

```
mutantpaint/
├── streamlit_app.py          # 메인 애플리케이션 (4,526 lines)
├── data/                      # 마스터 데이터 폴더
│   ├── colors.json           # 색상 데이터 (34개)
│   ├── patterns.json         # 패턴 데이터 (18개)
│   └── skills.json           # 스킬 데이터 (102개)
└── saves/                     # 사용자 데이터
    └── ...
```

## 데이터 파일 형식

### colors.json
```json
{
  "color_id": {
    "grade": "Normal|Rare|Epic|Unique|Legendary|Mystic",
    "name": "색상 이름",
    "hex": "#RRGGBB"
  }
}
```

**예시:**
```json
{
  "normal01": {"grade": "Normal", "name": "White", "hex": "#FFFFFF"},
  "rare01": {"grade": "Rare", "name": "Crimson", "hex": "#DC143C"}
}
```

### patterns.json
```json
{
  "pattern_id": {
    "grade": "Normal|Rare|Epic|Unique|Legendary|Mystic",
    "layout": "레이아웃 타입"
  }
}
```

**예시:**
```json
{
  "normal01": {"grade": "Normal", "layout": "full_main"},
  "epic01": {"grade": "Epic", "layout": "cross"}
}
```

### skills.json
```json
{
  "skill_id": {
    "grade": "Normal|Rare|Epic|Unique|Legendary|Mystic",
    "slot": 1|2|3,
    "name": "스킬 이름",
    "resource": "아이콘 파일명.svg",
    "effect": "효과 타입",
    "value": 0.0,
    "cooldown": 0,
    "desc": "스킬 설명"
  }
}
```

**예시:**
```json
{
  "acc1_normal01": {
    "grade": "Normal",
    "slot": 1,
    "name": "Minor Heal",
    "resource": "cap.svg",
    "effect": "heal",
    "value": 0.10,
    "cooldown": 3,
    "desc": "HP 10% 회복"
  }
}
```

## 새 컨텐츠 추가 방법

### 1. 새로운 색상 추가

1. `data/colors.json` 파일 열기
2. 적절한 등급 섹션에 새 항목 추가:
```json
"unique06": {"grade": "Unique", "name": "Midnight", "hex": "#191970"}
```
3. 파일 저장
4. 게임 재시작

### 2. 새로운 패턴 추가

1. `data/patterns.json` 파일 열기
2. 새 패턴 추가:
```json
"legendary03": {"grade": "Legendary", "layout": "galaxy"}
```
3. 파일 저장
4. 게임 재시작

### 3. 새로운 스킬 추가

1. `data/skills.json` 파일 열기
2. 슬롯과 등급에 맞는 ID 사용 (acc{slot}_{grade}{number})
3. 새 스킬 추가:
```json
"acc1_epic07": {
  "grade": "Epic",
  "slot": 1,
  "name": "Super Heal",
  "resource": "new_icon.svg",
  "effect": "heal",
  "value": 0.45,
  "cooldown": 6,
  "desc": "HP 45% 회복"
}
```
4. 파일 저장
5. 게임 재시작

## 등급별 가이드라인

| 등급 | 개수 가이드 | 확률 | 특징 |
|------|------------|------|------|
| Normal | 10개 | 70% | 기본 효과 |
| Rare | 8개 | 20% | 강화된 효과 |
| Epic | 6개 | 7% | 고급 효과 |
| Unique | 5개 | 2% | 특수 메커니즘 |
| Legendary | 3개 | 0.8% | 극강 효과 |
| Mystic | 2개 | 0.2% | 전투당 1회 제한 |

## 주의사항

⚠️ **중요:**
- JSON 문법을 정확히 지켜주세요 (쉼표, 중괄호, 따옴표)
- 기존 ID를 변경하면 저장된 캐릭터가 손상될 수 있습니다
- 새 항목은 항상 끝에 추가하세요
- 파일 수정 전 백업 권장

## 데이터 검증

데이터 파일이 올바른지 확인하려면:

```bash
python -c "
import json

with open('data/colors.json') as f:
    colors = json.load(f)
    print(f'✅ Colors: {len(colors)} items')

with open('data/patterns.json') as f:
    patterns = json.load(f)
    print(f'✅ Patterns: {len(patterns)} items')

with open('data/skills.json') as f:
    skills = json.load(f)
    print(f'✅ Skills: {len(skills)} items')
"
```

## 개선 효과

- ✅ 코드 크기: 5,132 lines → 4,526 lines (606 lines 감소)
- ✅ 데이터 관리: 코드 수정 불필요
- ✅ 유지보수성: 데이터만 편집하여 컨텐츠 추가
- ✅ 협업 용이: 비개발자도 데이터 추가 가능
- ✅ 버전 관리: 데이터 파일 독립적으로 추적 가능

## 문제 해결

### JSON 파싱 에러
- 문법 오류 확인 (쉼표, 따옴표)
- JSON validator 사용 권장

### 게임 시작 안 됨
- `streamlit run streamlit_app.py` 재실행
- 콘솔 에러 메시지 확인

### 새 데이터가 안 보임
- 브라우저 캐시 삭제 (Ctrl+F5)
- 애플리케이션 재시작
