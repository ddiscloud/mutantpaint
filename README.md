# 🎨 Mutant Paint

외형과 스킬을 진화시키는 크리처 육성 게임

## 🎮 빠른 시작

### 1. 로컬 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# 게임 실행
streamlit run streamlit_app.py
```

브라우저에서 `http://localhost:8501` 접속

### 2. Streamlit Cloud 배포 (권장)

이 프로젝트는 **Streamlit Cloud**에서 호스팅됩니다.

1. GitHub 저장소 생성
2. 코드 푸시
3. Streamlit Cloud에서 앱 배포
4. `Secrets` 설정에서 환경 변수 추가

### 3. 외부 공유 (Cloudflare Tunnel)

```powershell
# 터널 시작 (로컬 개발용)
.\start-tunnel.ps1
```

---

## 🔐 환경 변수 설정

### Streamlit Cloud 대시보드에서:

**Settings → Secrets** 에 다음 추가:

```toml
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_KEY = "eyJhbGc..."
OPENAI_API_KEY = "sk-proj-..."
```

### 로컬 개발:

`.env` 파일에 위 내용을 입력하세요.

---

## 💾 데이터 저장 방식

- **로컬**: JSON 파일 (`saves/`)
- **클라우드**: Supabase PostgreSQL

---

## 📋 게임 시스템

### 🧬 개체 시스템
- **능력치**: HP, ATK, MS (전투력 결정)
- **외형**: 3가지 색상 + 패턴 (34색 × 18패턴)
- **스킬**: 3개 슬롯 (102종 전투 스킬)
- **등급**: Normal → Rare → Epic → Unique → Legendary → Mystic

### 🔄 믹스 (교배)
- 2개체 선택 → 유전자 조합
- **돌연변이** 확률로 희귀 등급 획득
- 부모보다 강한 자손 생성 가능

### 📦 랜덤 박스
- **하루 1회** 무료 개체 획득
- 높은 확률로 고등급 보상:
  - Mystic: 1%
  - Legendary: 3%
  - Unique: 6%
  - Epic+: 25%

### ⚔️ 전투 시스템
- **1:1 턴제 자동 전투**
- MS 기반 행동 순서 (ATB 게이지)
- 3개 스킬로 전략적 전투
- 스테이지 클리어 시 보상 획득

### 📚 도감
- 획득한 색상, 패턴, 스킬 기록
- 컬렉션 완성도 확인
- 희귀 항목 수집 목표

---

## 📁 프로젝트 구조

```
mutantpaint/
├── streamlit_app.py          # 메인 애플리케이션
├── data/                      # 마스터 데이터 (JSON)
│   ├── colors.json           # 34개 색상
│   ├── patterns.json         # 18개 패턴
│   └── skills.json           # 102개 스킬
├── saves/                     # 사용자 데이터
│   ├── {username}_data.json  # 플레이어별 저장
│   └── backups/              # 자동 백업
├── .streamlit/
│   └── config.toml           # 다크모드 설정
├── requirements.txt          # Python 패키지
└── start-tunnel.ps1          # 외부 공유 스크립트
```

---

## 🔧 데이터 커스터마이징

### 새 색상 추가

[data/colors.json](data/colors.json) 편집:
```json
{
  "epic07": {"grade": "Epic", "name": "Neon", "hex": "#00FF41"}
}
```

### 새 스킬 추가

[data/skills.json](data/skills.json) 편집:
```json
{
  "acc1_rare09": {
    "grade": "Rare",
    "slot": 1,
    "name": "Mega Heal",
    "resource": "icon.svg",
    "effect": "heal",
    "value": 0.30,
    "cooldown": 4,
    "desc": "HP 30% 회복"
  }
}
```

자세한 가이드: [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md)

---

## 🔒 보안

- SHA-256 비밀번호 해싱
- 파일 잠금으로 동시 접근 방지
- 자동 백업 시스템 (최근 5개 보관)
- 원자적 파일 쓰기

---

## 🌐 외부 공유

### Quick Tunnel (권장)
```powershell
.\start-tunnel.ps1
```
- 즉시 사용 가능
- 랜덤 URL 생성
- 재시작 시 URL 변경

### Streamlit Cloud
- 영구 URL
- 무료 호스팅
- GitHub 연동 필요

자세한 가이드: [README_TUNNEL.md](README_TUNNEL.md)

---

## 🎯 업데이트 계획

- [x] 기본 육성 시스템
- [x] 믹스 (교배) 시스템
- [x] 랜덤 박스
- [x] 전투 시스템 (스테이지)
- [x] 도감 시스템
- [x] 외부 공유 (Cloudflare)
- [x] 데이터 JSON 분리
- [ ] PVP 대전
- [ ] 시즌 랭킹
- [ ] 추가 전투 모드

---

## 📞 문의

게임 버그나 제안사항이 있다면 Discord에서 공유하세요!

Discord: https://discord.gg/eS2kJ2Zz7Z

---

**즐거운 플레이 되세요!** 🎮✨
