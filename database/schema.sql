-- =============================================
-- FitBot v2 — Полная схема базы данных
-- Выполни в Supabase SQL Editor
-- =============================================

DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS user_patterns CASCADE;
DROP TABLE IF EXISTS events_log CASCADE;
DROP TABLE IF EXISTS mood_log CASCADE;
DROP TABLE IF EXISTS body_metrics CASCADE;
DROP TABLE IF EXISTS daily_checkins CASCADE;
DROP TABLE IF EXISTS pending_actions CASCADE;
DROP TABLE IF EXISTS user_notes CASCADE;
DROP TABLE IF EXISTS time_blocks CASCADE;
DROP TABLE IF EXISTS daily_plan CASCADE;
DROP TABLE IF EXISTS schedule CASCADE;
DROP TABLE IF EXISTS reminders CASCADE;
DROP TABLE IF EXISTS workout_plans CASCADE;
DROP TABLE IF EXISTS workout_log CASCADE;
DROP TABLE IF EXISTS nutrition_log CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS profile CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS exercises CASCADE;
DROP TABLE IF EXISTS products CASCADE;

-- =============================================
-- СПРАВОЧНИКИ
-- =============================================

CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    name_ru TEXT NOT NULL,
    name_en TEXT,
    calories NUMERIC(6,1) NOT NULL,
    protein NUMERIC(5,1) NOT NULL,
    fat NUMERIC(5,1) NOT NULL,
    carbs NUMERIC(5,1) NOT NULL,
    per_grams INTEGER DEFAULT 100,
    category TEXT,
    source TEXT DEFAULT 'manual',
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE exercises (
    id BIGSERIAL PRIMARY KEY,
    name_ru TEXT NOT NULL,
    muscle_primary TEXT NOT NULL,
    muscle_secondary TEXT[],
    equipment TEXT[],
    difficulty INTEGER DEFAULT 1,
    contraindications TEXT[],
    instructions_ru TEXT,
    met_value NUMERIC(4,1) DEFAULT 4.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ПОЛЬЗОВАТЕЛИ
-- =============================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT DEFAULT 'user',
    status TEXT DEFAULT 'active',
    onboarding_done BOOLEAN DEFAULT FALSE,
    onboarding_step TEXT DEFAULT 'start',
    sleep_time_last TIMESTAMPTZ,
    language TEXT DEFAULT 'ru',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ПРОФИЛЬ (расширенный)
-- =============================================

CREATE TABLE profile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    age INTEGER,
    gender TEXT,
    height INTEGER,
    weight NUMERIC(5,1),
    waist_cm NUMERIC(5,1),
    target_weight NUMERIC(5,1),
    goal TEXT,
    goal_deadline TEXT,
    experience TEXT,
    activity_level INTEGER,
    work_type TEXT,
    wake_time TIME,
    sleep_time TIME,
    chronotype TEXT,
    peak_energy_time TIME,
    equipment TEXT,
    days_per_week INTEGER,
    session_duration INTEGER,
    travel_time_gym INTEGER DEFAULT 0,
    gym_name TEXT,
    weak_movements TEXT[],
    diet_type TEXT DEFAULT 'standard',
    food_allergies TEXT[],
    cooking_skill TEXT,
    meals_per_day INTEGER DEFAULT 3,
    injuries TEXT[],
    communication_style TEXT DEFAULT 'friendly',
    motivation_type TEXT,
    reaction_to_failure TEXT,
    bmr NUMERIC(7,1),
    tdee NUMERIC(7,1),
    daily_calories NUMERIC(7,1),
    daily_protein NUMERIC(6,1),
    daily_fat NUMERIC(6,1),
    daily_carbs NUMERIC(6,1),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- СООБЩЕНИЯ (память AI)
-- =============================================

CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_user ON messages(user_id, created_at DESC);

-- =============================================
-- СВОБОДНАЯ ПАМЯТЬ
-- =============================================

CREATE TABLE user_notes (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_mentioned TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ПИТАНИЕ И ТРЕНИРОВКИ
-- =============================================

CREATE TABLE nutrition_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    food_description TEXT NOT NULL,
    calories NUMERIC(7,1),
    protein NUMERIC(6,1),
    fat NUMERIC(6,1),
    carbs NUMERIC(6,1),
    is_approximate BOOLEAN DEFAULT FALSE,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workout_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    workout_type TEXT,
    duration_minutes INTEGER,
    status TEXT DEFAULT 'done',
    feeling INTEGER,
    calories_burned NUMERIC(6,1),
    notes TEXT,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE workout_plans (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    plan_text TEXT NOT NULL,
    week_start DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- РАСПИСАНИЕ
-- =============================================

CREATE TABLE schedule (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    day_of_week TEXT NOT NULL,
    wake_time TIME,
    sleep_time TIME,
    work_start TIME,
    work_end TIME,
    workout_time TIME,
    dnd_start TIME,
    dnd_end TIME,
    is_rest_day BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, day_of_week)
);

CREATE TABLE daily_plan (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    status TEXT DEFAULT 'planned',
    UNIQUE(user_id, date)
);

CREATE TABLE time_blocks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    daily_plan_id BIGINT REFERENCES daily_plan(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    type TEXT NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE,
    buffer_before INTEGER DEFAULT 0,
    buffer_after INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
);

-- =============================================
-- ЧЕКИНЫ И ЗАМЕРЫ
-- =============================================

CREATE TABLE daily_checkins (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    weight NUMERIC(5,1),
    sleep_hours NUMERIC(3,1),
    sleep_time_actual TIME,
    wake_time_actual TIME,
    energy_level INTEGER,
    mood INTEGER,
    workout_done BOOLEAN,
    workout_feeling INTEGER,
    water_ml INTEGER,
    evening_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE TABLE body_metrics (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    weight NUMERIC(5,1),
    waist_cm NUMERIC(5,1),
    chest_cm NUMERIC(5,1),
    hips_cm NUMERIC(5,1),
    arms_cm NUMERIC(5,1),
    photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- СОБЫТИЯ, ПАТТЕРНЫ, СИСТЕМА
-- =============================================

CREATE TABLE events_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    description TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE user_patterns (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    best_workout_time TEXT,
    worst_skip_day TEXT,
    skip_reason_pattern TEXT,
    avg_calories_weekday NUMERIC(7,1),
    avg_calories_weekend NUMERIC(7,1),
    avg_sleep NUMERIC(3,1),
    weight_trend_7d NUMERIC(4,1),
    weight_trend_30d NUMERIC(4,1),
    plan_adherence_percent INTEGER,
    streak_current INTEGER DEFAULT 0,
    streak_record INTEGER DEFAULT 0,
    last_calculated TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pending_actions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    action_type TEXT NOT NULL,
    action_data JSONB NOT NULL,
    preview_text TEXT,
    status TEXT DEFAULT 'pending',
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '10 minutes',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reminders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    type TEXT NOT NULL,
    message TEXT,
    time_of_day TIME,
    days_of_week TEXT[],
    use_gpt BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    last_sent TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reports (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    bad_message TEXT,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ТРИГГЕР: авто-создание профиля
-- =============================================

CREATE OR REPLACE FUNCTION on_user_created()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO profile (user_id) VALUES (NEW.id);
    INSERT INTO user_patterns (user_id) VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_init_user
    AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION on_user_created();

-- =============================================
-- БАЗОВЫЕ ПРОДУКТЫ
-- =============================================

INSERT INTO products (name_ru, calories, protein, fat, carbs, category, verified) VALUES
('Куриная грудка варёная', 165, 31.0, 3.6, 0.0, 'мясо', true),
('Яйцо куриное', 155, 13.0, 11.0, 1.1, 'яйца', true),
('Овсянка сухая', 371, 13.0, 7.0, 67.0, 'злаки', true),
('Рис варёный', 130, 2.7, 0.3, 28.0, 'злаки', true),
('Гречка варёная', 110, 4.2, 1.1, 21.0, 'злаки', true),
('Творог 5%', 121, 17.0, 5.0, 1.8, 'молочное', true),
('Молоко 2.5%', 52, 2.9, 2.5, 4.7, 'молочное', true),
('Греческий йогурт', 97, 9.0, 5.0, 3.6, 'молочное', true),
('Банан', 89, 1.1, 0.3, 23.0, 'фрукты', true),
('Яблоко', 52, 0.3, 0.2, 14.0, 'фрукты', true),
('Огурец', 15, 0.7, 0.1, 3.6, 'овощи', true),
('Помидор', 18, 0.9, 0.2, 3.9, 'овощи', true),
('Брокколи', 34, 2.8, 0.4, 7.0, 'овощи', true),
('Картофель варёный', 87, 1.9, 0.1, 20.0, 'овощи', true),
('Лосось', 208, 20.0, 13.0, 0.0, 'рыба', true),
('Тунец консервированный', 116, 26.0, 1.0, 0.0, 'рыба', true),
('Говядина варёная', 254, 26.0, 16.0, 0.0, 'мясо', true),
('Хлеб белый', 265, 9.0, 3.2, 49.0, 'хлеб', true),
('Хлеб чёрный', 214, 6.6, 1.2, 41.0, 'хлеб', true),
('Макароны варёные', 158, 5.5, 0.9, 31.0, 'злаки', true),
('Сыр твёрдый', 380, 23.0, 31.0, 0.0, 'молочное', true),
('Масло оливковое', 884, 0.0, 100.0, 0.0, 'жиры', true),
('Грецкий орех', 654, 15.0, 65.0, 14.0, 'орехи', true),
('Миндаль', 579, 21.0, 50.0, 22.0, 'орехи', true),
('Протеин сывороточный', 400, 80.0, 5.0, 10.0, 'спортпит', true),
('Борщ домашний', 57, 2.8, 2.1, 6.5, 'блюда', true),
('Пельмени варёные', 275, 12.0, 13.0, 29.0, 'блюда', true),
('Кофе чёрный', 2, 0.3, 0.0, 0.0, 'напитки', true),
('Кофе с молоком', 58, 3.1, 3.2, 4.5, 'напитки', true),
('Апельсиновый сок', 45, 0.7, 0.2, 10.0, 'напитки', true);

-- =============================================
-- БАЗОВЫЕ УПРАЖНЕНИЯ
-- =============================================

INSERT INTO exercises (name_ru, muscle_primary, muscle_secondary, equipment, difficulty, contraindications, met_value) VALUES
('Жим штанги лёжа', 'грудь', ARRAY['трицепс','плечи'], ARRAY['штанга','скамья'], 2, ARRAY['травма плеча'], 5.0),
('Приседания со штангой', 'ноги', ARRAY['ягодицы','спина'], ARRAY['штанга'], 3, ARRAY['травма колена','травма спины'], 6.0),
('Становая тяга', 'спина', ARRAY['ноги','ягодицы'], ARRAY['штанга'], 3, ARRAY['грыжа','травма спины'], 6.0),
('Подтягивания', 'спина', ARRAY['бицепс'], ARRAY['турник'], 2, ARRAY['травма плеча'], 5.0),
('Отжимания', 'грудь', ARRAY['трицепс','плечи'], ARRAY[]::TEXT[], 1, ARRAY[]::TEXT[], 3.8),
('Жим гантелей сидя', 'плечи', ARRAY['трицепс'], ARRAY['гантели'], 2, ARRAY['травма плеча'], 4.0),
('Тяга гантели в наклоне', 'спина', ARRAY['бицепс'], ARRAY['гантели'], 2, ARRAY['травма спины'], 4.0),
('Выпады', 'ноги', ARRAY['ягодицы'], ARRAY[]::TEXT[], 2, ARRAY['травма колена'], 4.0),
('Планка', 'пресс', ARRAY['спина','плечи'], ARRAY[]::TEXT[], 1, ARRAY[]::TEXT[], 3.0),
('Скручивания', 'пресс', ARRAY[]::TEXT[], ARRAY[]::TEXT[], 1, ARRAY['грыжа'], 3.0),
('Бег', 'ноги', ARRAY['сердце'], ARRAY[]::TEXT[], 1, ARRAY['травма колена'], 9.8),
('Велотренажёр', 'ноги', ARRAY['сердце'], ARRAY['велотренажёр'], 1, ARRAY[]::TEXT[], 7.0),
('Прыжки на скакалке', 'ноги', ARRAY['сердце'], ARRAY['скакалка'], 2, ARRAY['травма колена'], 11.0),
('Сгибание рук с гантелями', 'бицепс', ARRAY[]::TEXT[], ARRAY['гантели'], 1, ARRAY[]::TEXT[], 3.5),
('Французский жим', 'трицепс', ARRAY[]::TEXT[], ARRAY['гантели'], 2, ARRAY['травма локтя'], 3.5),
('Румынская тяга', 'ягодицы', ARRAY['спина','ноги'], ARRAY['штанга'], 2, ARRAY['травма спины'], 5.0),
('Ягодичный мостик', 'ягодицы', ARRAY[]::TEXT[], ARRAY[]::TEXT[], 1, ARRAY[]::TEXT[], 3.5),
('Жим ногами', 'ноги', ARRAY['ягодицы'], ARRAY['тренажёр'], 2, ARRAY['травма колена'], 5.0);
