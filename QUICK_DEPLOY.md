# 🎯 Streamlit Cloud 배포 - 빠른 요약

5분 안에 배포하기 위한 최소 필수 단계입니다.

---

## ⚡ 3단계 배포 프로세스

### 1️⃣ GitHub에 코드 업로드 (2분)

```bash
cd c:\mutantpaint

# 저장소 초기화
git init
git config user.name "Your Name"
git config user.email "your@email.com"

# GitHub 저장소 주소 추가 (YOUR_USERNAME 변경)
git remote add origin https://github.com/YOUR_USERNAME/mutantpaint.git

# 모든 파일 커밋
git add .
git commit -m "Supabase 연동 완료"

# GitHub에 푸시
git branch -M main
git push -u origin main
```

✅ 완료: GitHub에 모든 코드 업로드됨

---

### 2️⃣ Streamlit Cloud에서 앱 배포 (1분)

**링크:** https://share.streamlit.io

1. **"Deploy an app"** 클릭
2. GitHub 저장소 선택
   - Repository: `YOUR_USERNAME/mutantpaint`
   - Branch: `main`
   - Main file: `streamlit_app.py`
3. **"Deploy"** 클릭
4. 배포 완료 대기 (1-2분)

✅ 완료: 앱이 클라우드에서 실행 중

---

### 3️⃣ 환경 변수 설정 (2분)

**Streamlit Cloud 앱 설정:**

1. 앱 URL 우측 상단 **⋯ (세 점)** 클릭
2. **Settings** → **Secrets** 클릭
3. 다음 코드 복사:

```toml
SUPABASE_URL = "https://your-project-id.supabase.co"
SUPABASE_KEY = "your-anon-public-key-here"
OPENAI_API_KEY = "your-openai-api-key-here"  # 선택사항
```

4. **Save** → 자동 재배포

⚠️ **주의**: 위의 값을 본인의 실제 Supabase 정보로 교체하세요!

✅ 완료: 앱이 Supabase와 연동됨

---

## 🎉 배포 완료!

**앱 URL**: `https://mutantpaint-YOUR_USERNAME.streamlit.app`

### 테스트
- [ ] 앱이 로드되는가?
- [ ] 로그인 페이지가 나타나는가?
- [ ] 기존 계정으로 로그인 가능한가?
- [ ] 게임 데이터가 저장되는가?

---

## 🔄 향후 업데이트

코드 수정 후 배포하려면:

```bash
git add .
git commit -m "설명"
git push origin main
```

Streamlit Cloud가 자동으로 재배포합니다 (1-2분).

---

## ❓ 문제 해결

### 앱이 로드되지 않음
- Streamlit Cloud 로그 확인
- Secrets 설정 재확인

### Supabase 연결 오류
- API URL과 Key 재확인
- `.env` 파일과 일치하는지 확인

### 데이터 미저장
- Supabase 테이블 확인
- RLS 정책 확인

---

**상세 가이드**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)  
**체크리스트**: [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)

---

**배포 준비 완료! 이제 진행하면 됩니다. 🚀**
