-- ============================================================
-- PharmaFieldTracker - Supabase Veritabanı
-- Supabase → SQL Editor'e yapıştırıp Run tıkla
-- ============================================================

DROP TABLE IF EXISTS activity_logs CASCADE;
DROP TABLE IF EXISTS visit_steps CASCADE;
DROP TABLE IF EXISTS visits CASCADE;
DROP TABLE IF EXISTS visit_flows CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS hospitals CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role TEXT CHECK (role IN ('agent', 'admin')) NOT NULL,
  full_name TEXT
);

CREATE TABLE hospitals (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  latitude REAL,
  longitude REAL
);

CREATE TABLE doctors (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  hospital_id INTEGER REFERENCES hospitals(id),
  branch TEXT
);

CREATE TABLE visit_flows (
  id SERIAL PRIMARY KEY,
  step_order INTEGER NOT NULL,
  step_name TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE visits (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  doctor_id INTEGER REFERENCES doctors(id),
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP,
  total_duration_seconds INTEGER,
  gps_latitude REAL,
  gps_longitude REAL,
  notes TEXT,
  suspicion_score INTEGER
);

CREATE TABLE visit_steps (
  id SERIAL PRIMARY KEY,
  visit_id INTEGER REFERENCES visits(id) ON DELETE CASCADE,
  flow_step_id INTEGER REFERENCES visit_flows(id),
  completed_at TIMESTAMP NOT NULL,
  gps_latitude REAL,
  gps_longitude REAL
);

CREATE TABLE activity_logs (
  id SERIAL PRIMARY KEY,
  visit_id INTEGER REFERENCES visits(id) ON DELETE CASCADE,
  event_type TEXT,
  event_value INTEGER,
  timestamp TIMESTAMP
);

-- Örnek veriler
INSERT INTO users (username, password, role, full_name) VALUES
  ('admin',       'admin123', 'admin', 'Admin Kullanıcı'),
  ('ali_eleman',  '123456',   'agent', 'Ali Veli'),
  ('ayse_eleman', '123456',   'agent', 'Ayşe Çelik');

INSERT INTO hospitals (name, latitude, longitude) VALUES
  ('Merkez Hastanesi',      41.0082, 28.9784),
  ('Özel Sağlık Hastanesi', 41.0150, 28.9800),
  ('Devlet Hastanesi',      41.0200, 28.9650);

INSERT INTO doctors (name, hospital_id, branch) VALUES
  ('Dr. Ahmet Yılmaz', 1, 'Kardiyoloji'),
  ('Dr. Ayşe Kaya',    1, 'Dahiliye'),
  ('Dr. Mehmet Demir', 2, 'Çocuk Sağlığı'),
  ('Dr. Fatma Şahin',  2, 'Nöroloji'),
  ('Dr. Hasan Öztürk', 3, 'Ortopedi');

INSERT INTO visit_flows (step_order, step_name, is_active) VALUES
  (1, 'Hastaneye Girdim',      true),
  (2, 'Doktor Bekliyorum',     true),
  (3, 'Doktor Odasına Girdim', true),
  (4, 'Sunumu Başlattım',      true),
  (5, 'Sunumu Bitirdim',       true),
  (6, 'Hastaneden Ayrıldım',   true);

-- RLS'yi kapat (geliştirme ortamı)
ALTER TABLE users          DISABLE ROW LEVEL SECURITY;
ALTER TABLE hospitals      DISABLE ROW LEVEL SECURITY;
ALTER TABLE doctors        DISABLE ROW LEVEL SECURITY;
ALTER TABLE visit_flows    DISABLE ROW LEVEL SECURITY;
ALTER TABLE visits         DISABLE ROW LEVEL SECURITY;
ALTER TABLE visit_steps    DISABLE ROW LEVEL SECURITY;
ALTER TABLE activity_logs  DISABLE ROW LEVEL SECURITY;
