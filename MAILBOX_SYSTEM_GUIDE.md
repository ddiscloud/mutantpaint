# 우편함 & 랜덤박스 시스템 설치 가이드

## 📦 개요

3가지 새 기능이 추가되었습니다:
1. **우편함 시스템** - 유저별 우편 수신 및 수령
2. **우편 지급 기능** - 관리자가 특정 유저에게 개체/박스 지급
3. **랜덤박스 템플릿 관리** - 조건부 랜덤 개체 생성 시스템

## 🗄️ 1단계: Supabase 테이블 생성

### 방법 1: Supabase 대시보드에서 직접 실행

1. https://app.supabase.com 접속
2. 프로젝트 선택
3. **SQL Editor** 메뉴 클릭
4. **create_mailbox_tables.sql** 파일 내용 복사 & 붙여넣기
5. **Run** 버튼 클릭

### 테이블 구조

**box_templates** - 랜덤박스 템플릿
```sql
- id: TEXT (PRIMARY KEY)
- name: TEXT (박스 이름)
- description: TEXT (설명)
- conditions: JSONB (능력치 범위, 등급 제한)
- created_by: TEXT
- created_at: TIMESTAMP
- is_active: BOOLEAN
```

**mailbox** - 우편함
```sql
- id: TEXT (PRIMARY KEY)
- user_id: TEXT (수신자)
- type: TEXT ('instance' or 'box')
- instance_data: JSONB (type='instance'일 때)
- box_template_id: TEXT (type='box'일 때)
- message: TEXT (메시지)
- created_at: TIMESTAMP
- claimed: BOOLEAN (수령 여부)
- claimed_at: TIMESTAMP
```

### 샘플 데이터

SQL 파일 실행 시 2개의 기본 템플릿이 자동 생성됩니다:
- **box_starter**: 초보자 박스 (Normal/Rare 등급, 낮은 능력치)
- **box_advanced**: 고급 박스 (Rare/Epic/Unique 등급, 높은 능력치)

## 🎮 2단계: 기능 사용법

### 우편함 시스템 (일반 유저)

1. **홈 화면**에서 **📬 우편함** 버튼 클릭
2. 수령하지 않은 우편 목록 표시
3. 우편 타입별 처리:
   - **개체 우편**: 미리보기 → "📥 수령하기" 클릭
   - **랜덤박스 우편**: 조건 확인 → "🎁 개봉하기" 클릭
4. 수령 시 개체 목록에 자동 추가 + 우편 삭제

### 랜덤박스 관리 (관리자)

**관리자 메뉴 → 🎁 랜덤박스 관리 탭**

#### 📋 템플릿 목록
- 등록된 템플릿 조회
- 활성화/비활성화 토글
- 템플릿 삭제
- 조건 JSON 확인

#### ➕ 새 템플릿 생성
1. 박스 이름, 설명 입력
2. **능력치 범위** 설정:
   - HP/ATK/MS 최소~최대값
3. **외형 등급 제한** (multiselect):
   - Main/Sub/Pattern Color 허용 등급
   - Pattern 허용 등급
4. **스킬 등급 제한** (빈 선택 = 지급 안함):
   - Accessory 1/2/3 허용 등급
5. "➕ 템플릿 생성" 클릭

#### ✏️ 템플릿 수정
- 이름, 설명만 수정 가능
- 조건 변경은 삭제 후 재생성 권장

### 우편 지급 (관리자)

**관리자 메뉴 → 📬 우편 지급 탭**

#### 개체 직접 지급
1. 수신 사용자 선택
2. "개체 직접 지급" 선택
3. 메시지 입력
4. 개체 설정:
   - HP/ATK/MS 값
   - 외형 등급 및 ID 선택
   - 스킬 3개 선택 (체크박스로 활성화)
   - 개체 이름
5. "📤 개체 발송" 클릭

#### 랜덤박스 지급
1. 수신 사용자 선택
2. "랜덤박스 지급" 선택
3. 메시지 입력
4. 등록된 템플릿 선택
5. 조건 확인 (능력치 범위 표시)
6. "📤 랜덤박스 발송" 클릭

## 🔧 핵심 로직

### 박스 개봉 알고리즘

```python
def open_random_box(template_id):
    1. 템플릿 로드
    2. 능력치 랜덤 생성 (min~max 범위)
    3. 외형 요소 가중치 선택:
       - 허용된 등급 내에서 GRADE_WEIGHTS 적용
       - Normal: 100, Rare: 80, Epic: 55, Unique: 35, Legendary: 20, Mystic: 10
       - 누적 확률 방식으로 랜덤 선택
    4. 스킬 가중치 선택 (외형과 동일)
    5. 개체 생성 (created_by="Mailbox")
```

### 가중치 시스템

등급이 낮을수록 높은 가중치:
- **Normal**: 가장 높은 확률 (100)
- **Rare**: 높은 확률 (80)
- **Epic**: 중간 확률 (55)
- **Unique**: 낮은 확률 (35)
- **Legendary**: 매우 낮은 확률 (20)
- **Mystic**: 극히 낮은 확률 (10)

## 📊 데이터베이스 함수 (supabase_db.py)

### 랜덤박스 함수
```python
load_box_templates(active_only=True)     # 템플릿 목록
get_box_template(template_id)           # 단일 템플릿
create_box_template(...)                # 템플릿 생성
update_box_template(...)                # 템플릿 수정
delete_box_template(template_id)        # 템플릿 삭제
```

### 우편함 함수
```python
load_mailbox(username, unclaimed_only)  # 우편 목록
send_mail(user_id, type, message, ...)  # 우편 발송
claim_mail(mail_id)                     # 우편 수령
delete_mail(mail_id)                    # 우편 삭제
```

### 개체 생성 함수
```python
open_random_box(template_id, created_by) # 박스 개봉 → 개체 생성
```

## 🎯 사용 시나리오

### 시나리오 1: 이벤트 보상
```
1. 관리자: "이벤트 우승자에게 고급 박스 지급"
2. 관리자 메뉴 → 우편 지급 → 랜덤박스 지급
3. 수신자: "우승자123" 선택
4. 박스: "box_advanced" 선택
5. 메시지: "🎉 이벤트 우승 축하 보상"
6. 발송 클릭

→ 우승자123의 우편함에 박스 도착
→ 우승자123이 박스 개봉
→ Rare~Unique 등급 개체 획득
```

### 시나리오 2: 보상 개체 직접 지급
```
1. 관리자: "버그 보고자에게 특별 개체 지급"
2. 관리자 메뉴 → 우편 지급 → 개체 직접 지급
3. 능력치: HP 500, ATK 50, MS 30
4. 외형: Epic Sapphire + Epic Emerald + Epic Cross
5. 스킬: 3개 Epic 스킬 장착
6. 이름: "Bug Hunter Reward"
7. 발송 클릭

→ 정확히 설계된 개체가 우편함에 도착
→ 수령 시 즉시 사용 가능
```

### 시나리오 3: 신규 유저 환영 박스
```
1. 관리자: 새 템플릿 생성
   - 이름: "신규 환영 박스"
   - HP: 30~80, ATK: 3~8, MS: 3~8
   - 외형: Normal만 허용
   - 스킬: Accessory 1만 Normal 1개
2. 모든 신규 가입자에게 자동 발송 (스크립트 연동 가능)
3. 신규 유저가 첫 로그인 → 우편함 확인
4. 박스 개봉 → 균형잡힌 시작 개체 획득
```

## ⚠️ 주의사항

1. **SQL 실행 필수**: Supabase 대시보드에서 create_mailbox_tables.sql 실행 필요
2. **권한 관리**: 우편 지급 및 템플릿 관리는 관리자 권한 필요 (cheat_level="dev")
3. **템플릿 설계**: 조건이 너무 제한적이면 개체 생성 실패 가능
4. **등급 선택**: multiselect에서 최소 1개 등급 선택 필요 (빈 선택 = 지급 안함)
5. **박스 개봉**: 랜덤 생성이므로 매번 다른 개체 획득
6. **수령 처리**: claim_mail() 호출 시 claimed=True로 변경, 재수령 불가

## 🐛 트러블슈팅

### "템플릿을 찾을 수 없습니다"
→ create_mailbox_tables.sql 실행 확인
→ load_box_templates() 호출해서 목록 확인

### "박스 개봉에 실패했습니다"
→ 템플릿 조건이 너무 제한적 (예: 존재하지 않는 등급)
→ 등급 선택에 최소 1개 이상 포함 확인

### "우편 발송에 실패했습니다"
→ mailbox 테이블 생성 확인
→ user_id가 game_data 테이블에 존재하는지 확인

### 우편함 카운트가 표시 안됨
→ load_mailbox() 함수 호출 확인
→ Supabase 연결 상태 확인

## 📝 파일 목록

- **streamlit_app.py**: 메인 앱 (우편함 페이지, 관리자 탭 추가)
- **supabase_db.py**: DB 함수 (랜덤박스, 우편함 함수 추가)
- **create_mailbox_tables.sql**: 테이블 생성 SQL
- **setup_mailbox_tables.py**: SQL 안내 스크립트
- **MAILBOX_SYSTEM_GUIDE.md**: 이 문서

## ✅ 완료 체크리스트

- [ ] Supabase SQL Editor에서 create_mailbox_tables.sql 실행
- [ ] 테이블 생성 확인 (box_templates, mailbox)
- [ ] 샘플 템플릿 확인 (box_starter, box_advanced)
- [ ] 관리자 계정으로 로그인
- [ ] 관리자 메뉴 → 랜덤박스 관리 탭 확인
- [ ] 새 템플릿 생성 테스트
- [ ] 테스트 유저에게 우편 발송
- [ ] 테스트 유저로 우편함 확인 및 수령
- [ ] 박스 개봉 정상 작동 확인

---

**구현 완료일**: 2026-01-18
**개발자**: GitHub Copilot (Claude Sonnet 4.5)
