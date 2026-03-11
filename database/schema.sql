-- =============================================
-- FitBot Database Schema
-- Выполни это в Supabase SQL Editor
-- =============================================

-- Удаляем старые таблицы если есть
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS reminders CASCADE;
DROP TABLE IF EXISTS nutrition_log CASCADE;
DROP TABLE IF EXISTS workout_log CASCADE;
DROP TABLE IF EXISTS profile CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- =============================================
-- ПОЛЬЗОВАТЕЛИ
-- =============================================
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT DEFAULT 'user',         -- user / admin / superadmin
    status TEXT DEFAULT 'active',     -- active / banned
    onboarding_done BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ПРОФИЛЬ (данные анкеты)
-- =============================================
CREATE TABLE profile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    
    -- Физические данные
    age INTEGER,
    gender TEXT,                      -- male / female
    height INTEGER,                   -- см
    weight NUMERIC(5,1),              -- кг
    
    -- Цели и опыт
    goal TEXT,                        -- lose / gain / maintain / health
    activity_level INTEGER,           -- 1-4
    experience TEXT,                  -- beginner / intermediate / advanced
    
    -- Ограничения
    health_restrictions TEXT,         -- травмы, болезни
    equipment TEXT,                   -- home / gym / both
    
    -- Предпочтения
    workout_preferences TEXT,         -- что нравится
    diet_preferences TEXT,            -- веган, без глютена и тд
    diet_restrictions TEXT,           -- аллергии
    
    -- Расчётные данные (обновляются автоматически)
    bmr NUMERIC(7,1),
    tdee NUMERIC(7,1),
    daily_calories NUMERIC(7,1),
    daily_protein NUMERIC(6,1),
    daily_fat NUMERIC(6,1),
    daily_carbs NUMERIC(6,1),
    
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- =============================================
-- ИСТОРИЯ СООБЩЕНИЙ (память AI)
-- =============================================
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,               -- user / assistant
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для быстрой выборки последних сообщений
CREATE INDEX idx_messages_user_created ON messages(user_id, created_at DESC);

-- =============================================
-- ЛОГ ПИТАНИЯ
-- =============================================
CREATE TABLE nutrition_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    food_description TEXT NOT NULL,   -- что написал юзер
    calories NUMERIC(7,1),
    protein NUMERIC(6,1),
    fat NUMERIC(6,1),
    carbs NUMERIC(6,1),
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ЛОГ ТРЕНИРОВОК
-- =============================================
CREATE TABLE workout_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    workout_type TEXT,                -- название тренировки
    duration_minutes INTEGER,
    notes TEXT,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- НАПОМИНАНИЯ
-- =============================================
CREATE TABLE reminders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    type TEXT NOT NULL,               -- workout / food / custom / water
    message TEXT,
    remind_at TIMESTAMPTZ,            -- для разовых
    time_of_day TIME,                 -- для ежедневных
    days_of_week TEXT[],              -- ['mon','tue','wed']
    is_recurring BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ПЛАНЫ ТРЕНИРОВОК
-- =============================================
CREATE TABLE workout_plans (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    plan_text TEXT NOT NULL,          -- полный план от AI
    week_start DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- RLS (безопасность - отключаем для сервис ключа)
-- =============================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE nutrition_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_plans ENABLE ROW LEVEL SECURITY;

-- Политика - сервис ключ имеет полный доступ
CREATE POLICY "Service role full access" ON users FOR ALL USING (true);
CREATE POLICY "Service role full access" ON profile FOR ALL USING (true);
CREATE POLICY "Service role full access" ON messages FOR ALL USING (true);
CREATE POLICY "Service role full access" ON nutrition_log FOR ALL USING (true);
CREATE POLICY "Service role full access" ON workout_log FOR ALL USING (true);
CREATE POLICY "Service role full access" ON reminders FOR ALL USING (true);
CREATE POLICY "Service role full access" ON workout_plans FOR ALL USING (true);

-- =============================================
-- ФУНКЦИЯ: авто-создание профиля при регистрации
-- =============================================
CREATE OR REPLACE FUNCTION create_profile_on_user_insert()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO profile (user_id) VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_create_profile
    AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION create_profile_on_user_insert();
