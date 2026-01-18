# ✅ Streamlit Cloud 배포 체크리스트

배포 전 확인사항을 정리한 체크리스트입니다.

---

## 📦 코드 준비

- [x] `requirements.txt` 최신 상태
  - streamlit >= 1.28.0
  - supabase >= 2.0.0
  - python-dotenv >= 1.0.0

- [x] 필수 모듈 생성
  - `supabase_config.py` ✅
  - `supabase_db.py` ✅
  - `.streamlit/config.toml` ✅

- [x] `streamlit_app.py` 수정 완료
  - 마스터 데이터 로드 → Supabase
  - `save_game_data()` → Supabase
  - `load_game_data()` → Supabase
  - `load_season_history()` → Supabase
  - `save_season_history()` → Supabase

- [x] 버그 수정
  - 무한 재귀 문제 해결

- [x] 로컬 테스트
  - `streamlit run streamlit_app.py` 정상 작동 확인

---

## 🔐 환경 설정

- [x] Supabase 프로젝트 생성
  - Project URL: ✅
  - Anon Key: ✅
  - 테이블 생성: ✅
  - 데이터 마이그레이션: ✅

- [x] `.env` 파일 설정
  ```
  SUPABASE_URL=...
  SUPABASE_KEY=...
  OPENAI_API_KEY=...
  ```

- [ ] GitHub 저장소 준비
  - [ ] 저장소 생성
  - [ ] 로컬 코드 푸시

- [ ] Streamlit Cloud 계정 준비
  - [ ] 계정 생성
  - [ ] GitHub 연동

---

## 🚀 배포 단계

### 1단계: GitHub 푸시
```bash
git init
git remote add origin https://github.com/YOUR_USERNAME/mutantpaint.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

### 2단계: Streamlit Cloud 배포
- [ ] Streamlit Cloud에서 새 앱 생성
- [ ] GitHub 저장소 선택
- [ ] 배포 진행

### 3단계: 환경 변수 설정
- [ ] Streamlit Cloud Secrets 설정
- [ ] SUPABASE_URL 추가
- [ ] SUPABASE_KEY 추가
- [ ] OPENAI_API_KEY 추가
- [ ] 저장 및 재배포

### 4단계: 배포 확인
- [ ] 앱 URL 접속 가능
- [ ] Supabase 연결 메시지 확인
- [ ] 로그인 페이지 표시
- [ ] 로그인 기능 테스트
- [ ] 게임 저장 기능 테스트

---

## 📋 파일 체크리스트

### 필수 파일
- [x] `streamlit_app.py` (메인 앱)
- [x] `supabase_config.py` (Supabase 설정)
- [x] `supabase_db.py` (DB 함수)
- [x] `requirements.txt` (패키지 의존성)
- [x] `.env` (로컬 환경 변수)
- [x] `.gitignore` (Git 제외 파일)
- [x] `README.md` (프로젝트 설명)

### 설정 파일
- [x] `.streamlit/config.toml` (Streamlit 설정)

### 데이터 파일
- [x] `data/colors.json` (마스터 데이터)
- [x] `data/patterns.json` (마스터 데이터)
- [x] `data/skills.json` (마스터 데이터)

### 마이그레이션 스크립트
- [x] `migrate_to_supabase.py` (데이터 마이그레이션)
- [x] `supabase_schema.sql` (DB 스키마)

---

## ⚠️ 주의사항

- **API 키 보안**: `.env` 파일을 `.gitignore`에 추가
- **Secrets 설정**: Streamlit Cloud에서 반드시 설정
- **RLS 정책**: Supabase RLS가 올바르게 설정되어 있는지 확인
- **네트워크**: Supabase API에 접근 가능한지 확인

---

## 📞 배포 후 연락처

배포 완료 후:
1. 생성된 URL을 사용자들과 공유
2. 버그 리포트 받기
3. 주기적으로 업데이트 배포

---

**모든 항목을 확인했다면 배포 준비 완료입니다! 🎉**
