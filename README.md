# 💊 PharmaFieldTracker

Saha satış elemanlarının doktor ziyaretlerini takip eden **sıfır maliyetli** sistem.

## 📁 Proje Yapısı

```
PharmaFieldTracker/
├── admin_panel/                  ← Streamlit Cloud'a deploy edilir
│   ├── app.py                    # Ana uygulama (Main file path burası)
│   ├── supabase_client.py        # st.secrets ile bağlantı
│   ├── utils.py                  # Şüphe puanı, yardımcı fonksiyonlar
│   ├── requirements.txt          # Streamlit bağımlılıkları
│   └── .streamlit/
│       └── secrets.toml          # ⚠️ .gitignore'da — GitHub'a gitmiyor
├── mobile_app/                   ← Codespaces'te APK olarak build edilir
│   ├── main.py                   # Flet uygulaması
│   ├── supabase_client.py        # httpx ile REST API (supabase paketi YOK)
│   ├── requirements.txt          # Minimal bağımlılıklar (hızlı build)
│   └── .env.example              # .env şablonu
├── sql/
│   └── create_tables.sql         # Supabase SQL Editor'de çalıştır
├── .gitignore
└── README.md
```

---

## 🚀 Kurulum

### 1. Supabase

1. [supabase.com](https://supabase.com) → New project
2. SQL Editor → `sql/create_tables.sql` yapıştır → Run
3. Settings → API → **Legacy anon, service_role API keys** sekmesi
4. `anon public` key'i kopyala → `SUPABASE_ANON_KEY`
5. Project URL'yi kopyala → `SUPABASE_URL`

---

### 2. Streamlit Cloud (Admin Paneli)

1. Bu repoyu GitHub'a push'la
2. [share.streamlit.io](https://share.streamlit.io) → New app
3. **Main file path:** `admin_panel/app.py`
4. **Manage App → Settings → Secrets:**
```toml
SUPABASE_URL = "https://xxxxx.supabase.co"
SUPABASE_ANON_KEY = "eyJ..."
```
5. Deploy → Test: `admin` / `admin123`

---

### 3. APK Build (Codespaces)

Codespaces terminalinde sırayla:

```bash
# Java
sudo rm /etc/apt/sources.list.d/yarn.list
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk

# Flutter
cd ~
wget https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.19.6-stable.tar.xz
tar xf flutter_linux_3.19.6-stable.tar.xz
echo 'export PATH="$HOME/flutter/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
flutter upgrade   # Dart 3.4+ için şart

# Android SDK
wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip commandlinetools-linux-11076708_latest.zip -d ~/android-sdk
mkdir -p ~/android-sdk/cmdline-tools/latest
mv ~/android-sdk/cmdline-tools/{bin,lib,NOTICE.txt,source.properties} ~/android-sdk/cmdline-tools/latest/
echo 'export ANDROID_HOME=$HOME/android-sdk' >> ~/.bashrc
echo 'export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools' >> ~/.bashrc
source ~/.bashrc
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-33" "build-tools;33.0.2"
flutter config --android-sdk ~/android-sdk

# Flet kur
pip install flet==0.23.2

# .env oluştur
cp mobile_app/.env.example mobile_app/.env
nano mobile_app/.env   # Kendi key'lerini gir

# mobile_app klasörüne gir ve build et
cd mobile_app
flet build apk --include-packages flet_geolocator
```

APK çıktısı: `mobile_app/build/apk/app-release.apk`

---

## 🔑 Test Hesapları

| Kullanıcı | Şifre | Rol |
|---|---|---|
| `admin` | `admin123` | Yönetici |
| `ali_eleman` | `123456` | Saha Elemanı |
| `ayse_eleman` | `123456` | Saha Elemanı |

---

## 📊 Şüphe Puanı (0-100)

| Kural | Puan |
|---|---|
| Hastaneden 500m+ uzakta | +40 |
| Süre < 90 sn | +30 |
| Süre 90–300 sn | +10 |
| Her eksik adım | +15 (max 60) |
| Tap < 2/dakika | +20 |

🟢 0-49 Normal | 🟡 50-69 Şüpheli | 🔴 70+ Çok Şüpheli
