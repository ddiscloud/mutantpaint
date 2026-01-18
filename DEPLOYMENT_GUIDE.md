# 🚀 Streamlit Cloud 배포 가이드

Mutant Paint를 Streamlit Cloud에 배포하는 단계별 가이드입니다.

---

## 📋 필수 요구사항

- GitHub 계정
- Supabase 프로젝트 (이미 설정됨)
- Streamlit Cloud 계정

---

## 🔧 Step 1: GitHub 저장소 생성

### 1-1) GitHub에서 새 저장소 생성
1. [GitHub](https://github.com/new) 접속
2. Repository name: `mutantpaint` (또는 원하는 이름)
3. Public 선택 (무료)
4. **Create repository** 클릭

### 1-2) 로컬 저장소 초기화 및 푸시

```bash
cd c:\mutantpaint

# Git 초기화
git init

# GitHub 저장소 추가 (YOUR_USERNAME을 실제 계정으로 변경)
git remote add origin https://github.com/YOUR_USERNAME/mutantpaint.git

# 모든 파일 스테이징
git add .

# 초기 커밋
git commit -m "Initial commit: Supabase 연동 완료"

# GitHub에 푸시
git branch -M main
git push -u origin main
```

**중요:** GitHub 로그인 창이 나타나면 GitHub 계정으로 인증하세요.

---

## 🔐 Step 2: Streamlit Cloud 계정 설정

### 2-1) Streamlit Cloud 가입
1. [Streamlit Cloud](https://streamlit.io/cloud) 접속
2. **Sign up** 클릭
3. GitHub 계정으로 로그인

### 2-2) 권한 부여
- GitHub 앱 설치 승인
- Repository access에서 `mutantpaint` 선택

---

## 📱 Step 3: Streamlit Cloud에서 앱 배포

### 3-1) 새 앱 배포
1. Streamlit Cloud 대시보드 접속
2. **New app** 클릭
3. 다음 정보 입력:
   - **Repository**: `YOUR_USERNAME/mutantpaint`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`

### 3-2) 배포
- **Deploy** 버튼 클릭
- 배포 진행 중... (1-3분 소요)

---

## 🔑 Step 4: 환경 변수 설정 (중요!)

배포 후, Streamlit Cloud 대시보드에서:

1. 앱 설정 메뉴 접속
2. **Settings** → **Secrets** 클릭
3. 다음 내용 복사:

```toml
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your-anon-public-key-here"
OPENAI_API_KEY = "your-openai-api-key-here"  # 선택사항
```

4. **Save** 클릭

⚠️ **주의**: 실제 배포 시 위의 값을 본인의 실제 값으로 교체하세요!

---

## ✅ Step 5: 배포 확인

1. Streamlit Cloud에서 생성된 URL 확인
   - 형식: `https://mutantpaint-YOUR_USERNAME.streamlit.app`

2. 앱이 정상 로드되는지 확인
   - Supabase 연결 성공 메시지 확인
   - 로그인 페이지 나타나는지 확인

3. 게임 기능 테스트
   - 로그인/회원가입
   - 게임 플레이 및 저장
   - 데이터가 Supabase에 저장되는지 확인

---

## 🔄 배포 후 업데이트

코드를 수정한 후 배포하려면:

```bash
# 코드 수정 후
git add .
git commit -m "수정 내용 설명"
git push origin main
```

Streamlit Cloud가 자동으로 감지하고 재배포합니다 (1-2분 소요).

---

## 🐛 문제 해결

### 앱이 로드되지 않음
- Streamlit Cloud 로그 확인
- 환경 변수 설정 재확인
- Supabase 연결 상태 확인

### Supabase 연결 오류
```
SupabaseException: Could not connect to database
```
- API URL과 Key가 올바른지 확인
- Supabase 프로젝트가 정상 작동 중인지 확인
- 네트워크 연결 상태 확인

### 데이터가 저장되지 않음
- Supabase RLS 정책 확인
- 권한 설정 재확인
- Supabase 대시보드에서 테이블 데이터 확인

---

## 📞 추가 리소스

- [Streamlit Cloud 공식 문서](https://docs.streamlit.io/streamlit-cloud/get-started)
- [Supabase 공식 문서](https://supabase.com/docs)
- [GitHub 기본 사용법](https://docs.github.com/en/get-started)

---

**배포 완료 후, 공유 가능한 URL을 얻게 됩니다!** 🎉
