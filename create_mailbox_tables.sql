-- 랜덤박스 템플릿 테이블
CREATE TABLE IF NOT EXISTS box_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  conditions JSONB NOT NULL,
  created_by TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  is_active BOOLEAN DEFAULT true
);

-- 우편함 테이블
CREATE TABLE IF NOT EXISTS mailbox (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('instance', 'box')),
  instance_data JSONB,
  box_template_id TEXT,
  message TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  claimed BOOLEAN DEFAULT false,
  claimed_at TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_mailbox_user_id ON mailbox(user_id);
CREATE INDEX IF NOT EXISTS idx_mailbox_claimed ON mailbox(claimed);
CREATE INDEX IF NOT EXISTS idx_box_templates_active ON box_templates(is_active);

-- 샘플 랜덤박스 템플릿
INSERT INTO box_templates (id, name, description, conditions, created_by, is_active)
VALUES (
  'box_starter',
  '초보자 박스',
  '기본 능력치와 Normal/Rare 등급 외형이 포함된 박스',
  '{
    "stat_ranges": {
      "hp": {"min": 20, "max": 50},
      "atk": {"min": 2, "max": 5},
      "ms": {"min": 2, "max": 5}
    },
    "grades": {
      "main_color": ["Normal", "Rare"],
      "sub_color": ["Normal", "Rare"],
      "pattern_color": ["Normal", "Rare"],
      "pattern": ["Normal", "Rare"],
      "accessory_1": ["Normal"],
      "accessory_2": null,
      "accessory_3": null
    }
  }',
  'system',
  true
),
(
  'box_advanced',
  '고급 박스',
  '높은 능력치와 Rare/Epic 등급 외형, 스킬 3개 포함',
  '{
    "stat_ranges": {
      "hp": {"min": 100, "max": 300},
      "atk": {"min": 10, "max": 30},
      "ms": {"min": 10, "max": 25}
    },
    "grades": {
      "main_color": ["Rare", "Epic", "Unique"],
      "sub_color": ["Rare", "Epic"],
      "pattern_color": ["Rare", "Epic"],
      "pattern": ["Rare", "Epic"],
      "accessory_1": ["Rare", "Epic"],
      "accessory_2": ["Rare", "Epic"],
      "accessory_3": ["Normal", "Rare"]
    }
  }',
  'system',
  true
);
