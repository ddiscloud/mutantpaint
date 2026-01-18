-- ============================================================================
-- MutantPaint Supabase 데이터베이스 스키마
-- 생성일: 2026-01-18
-- ============================================================================

-- 1. 사용자 테이블
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 게임 데이터 테이블 (사용자별 전체 게임 상태)
CREATE TABLE IF NOT EXISTS game_data (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  username TEXT UNIQUE NOT NULL REFERENCES users(username) ON DELETE CASCADE,
  data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 시즌 히스토리 테이블
CREATE TABLE IF NOT EXISTS season_history (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  season_data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. 마스터 데이터: 색상
CREATE TABLE IF NOT EXISTS master_colors (
  id TEXT PRIMARY KEY,
  grade TEXT NOT NULL,
  name TEXT NOT NULL,
  hex TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. 마스터 데이터: 패턴
CREATE TABLE IF NOT EXISTS master_patterns (
  id TEXT PRIMARY KEY,
  grade TEXT NOT NULL,
  layout TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. 마스터 데이터: 스킬
CREATE TABLE IF NOT EXISTS master_skills (
  id TEXT PRIMARY KEY,
  grade TEXT NOT NULL,
  slot INTEGER NOT NULL,
  skill_data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- 인덱스 생성 (성능 최적화)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_game_data_username ON game_data(username);
CREATE INDEX IF NOT EXISTS idx_master_colors_grade ON master_colors(grade);
CREATE INDEX IF NOT EXISTS idx_master_patterns_grade ON master_patterns(grade);
CREATE INDEX IF NOT EXISTS idx_master_skills_grade_slot ON master_skills(grade, slot);

-- ============================================================================
-- Row Level Security (RLS) 정책
-- ============================================================================

-- RLS 활성화
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE season_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE master_colors ENABLE ROW LEVEL SECURITY;
ALTER TABLE master_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE master_skills ENABLE ROW LEVEL SECURITY;

-- 사용자는 자신의 데이터만 읽고 쓸 수 있음
CREATE POLICY "Users can read own data" ON game_data
  FOR SELECT USING (true);

CREATE POLICY "Users can insert own data" ON game_data
  FOR INSERT WITH CHECK (true);

CREATE POLICY "Users can update own data" ON game_data
  FOR UPDATE USING (true);

-- 마스터 데이터는 모두가 읽을 수 있음
CREATE POLICY "Anyone can read colors" ON master_colors
  FOR SELECT USING (true);

CREATE POLICY "Anyone can read patterns" ON master_patterns
  FOR SELECT USING (true);

CREATE POLICY "Anyone can read skills" ON master_skills
  FOR SELECT USING (true);

-- 시즌 히스토리는 모두가 읽을 수 있음
CREATE POLICY "Anyone can read season history" ON season_history
  FOR SELECT USING (true);

CREATE POLICY "Anyone can insert season history" ON season_history
  FOR INSERT WITH CHECK (true);

-- ============================================================================
-- 트리거: updated_at 자동 업데이트
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_game_data_updated_at
  BEFORE UPDATE ON game_data
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_season_history_updated_at
  BEFORE UPDATE ON season_history
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
