# admin_panel/utils.py
# Şüphe puanı hesaplama, renk kodlama, veri çekme fonksiyonları.

import math
import pandas as pd
from supabase_client import get_supabase


def haversine_mesafe(lat1, lon1, lat2, lon2) -> float:
    """İki GPS noktası arasındaki mesafeyi metre cinsinden hesaplar."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def suphe_puani_hesapla(visit_id: int) -> int:
    """
    Ziyaret için şüphe puanı hesaplar (0-100).
    Kurallar:
      +40 → hastaneden 500m+ uzakta başlanmış
      +30 → süre < 90sn  |  +10 → 90-300sn  |  +0 → 300sn+
      +15 × eksik adım sayısı (max 60)
      +20 → tap yoğunluğu < 2/dakika
    """
    db = get_supabase()
    puan = 0
    try:
        visit = db.table("visits").select("*").eq("id", visit_id).single().execute().data
        if not visit:
            return 0
        sure = visit.get("total_duration_seconds") or 0

        # 1. Konum mesafesi
        if visit.get("gps_latitude") and visit.get("gps_longitude"):
            doc = db.table("doctors").select(
                "hospitals(latitude, longitude)"
            ).eq("id", visit["doctor_id"]).single().execute().data
            if doc and doc.get("hospitals"):
                h = doc["hospitals"]
                mesafe = haversine_mesafe(
                    visit["gps_latitude"], visit["gps_longitude"],
                    h.get("latitude", 0), h.get("longitude", 0)
                )
                if mesafe > 500:
                    puan += 40

        # 2. Süre
        if sure < 90:
            puan += 30
        elif sure < 300:
            puan += 10

        # 3. Eksik adım
        aktif = db.table("visit_flows").select("id").eq("is_active", True).execute().data or []
        tamam = db.table("visit_steps").select("id").eq("visit_id", visit_id).execute().data or []
        eksik = max(0, len(aktif) - len(tamam))
        puan += min(eksik * 15, 60)

        # 4. Tap yoğunluğu
        loglar = db.table("activity_logs").select("event_value").eq("visit_id", visit_id).execute().data or []
        toplam_tap = sum(l.get("event_value", 0) for l in loglar)
        dakika = sure / 60 if sure > 0 else 1
        if (toplam_tap / dakika) < 2:
            puan += 20

    except Exception:
        pass
    return min(puan, 100)


def toplu_puan_guncelle() -> int:
    """Tüm bitmiş ziyaretlerin puanını yeniden hesaplar."""
    db = get_supabase()
    try:
        bitmis = db.table("visits").select("id").not_.is_("end_time", "null").execute().data or []
        for z in bitmis:
            puan = suphe_puani_hesapla(z["id"])
            db.table("visits").update({"suspicion_score": puan}).eq("id", z["id"]).execute()
        return len(bitmis)
    except Exception:
        return 0


def puan_rengi(puan) -> str:
    if puan is None:
        return "#9E9E9E"
    if puan >= 70:
        return "#F44336"
    if puan >= 50:
        return "#FF9800"
    return "#4CAF50"


def puan_etiketi(puan) -> str:
    if puan is None:
        return "⚪ Hesaplanmadı"
    if puan >= 70:
        return "🔴 Çok Şüpheli"
    if puan >= 50:
        return "🟡 Şüpheli"
    return "🟢 Normal"


def ziyaretleri_getir(baslangic=None, bitis=None, kullanici_id=None,
                      doktor_id=None, min_puan=0, max_puan=100) -> pd.DataFrame:
    """Filtrelere göre ziyaretleri çeker, DataFrame döner."""
    db = get_supabase()
    q = db.table("visits").select(
        "id, start_time, end_time, total_duration_seconds, suspicion_score, notes,"
        "gps_latitude, gps_longitude, user_id, doctor_id,"
        "users(full_name),"
        "doctors(name, branch, hospitals(name, latitude, longitude))"
    ).not_.is_("end_time", "null")

    if kullanici_id:
        q = q.eq("user_id", kullanici_id)
    if doktor_id:
        q = q.eq("doctor_id", doktor_id)
    if baslangic:
        q = q.gte("start_time", str(baslangic))
    if bitis:
        q = q.lte("start_time", str(bitis) + "T23:59:59")

    veri = q.order("start_time", desc=True).execute().data or []

    satirlar = []
    for z in veri:
        puan = z.get("suspicion_score")
        if puan is not None and not (min_puan <= puan <= max_puan):
            continue
        doc = z.get("doctors") or {}
        hos = doc.get("hospitals") or {}
        satirlar.append({
            "id":            z["id"],
            "user_id":       z.get("user_id"),
            "doctor_id":     z.get("doctor_id"),
            "Eleman":        (z.get("users") or {}).get("full_name", "?"),
            "Doktor":        doc.get("name", "?"),
            "Branş":         doc.get("branch", "?"),
            "Hastane":       hos.get("name", "?"),
            "Başlama":       (z.get("start_time") or "")[:19].replace("T", " "),
            "Bitiş":         (z.get("end_time") or "")[:19].replace("T", " "),
            "Süre (sn)":     z.get("total_duration_seconds"),
            "Şüphe Puanı":   puan,
            "Not":           z.get("notes", ""),
            "Ziyaret Lat":   z.get("gps_latitude"),
            "Ziyaret Lon":   z.get("gps_longitude"),
            "Hastane Lat":   hos.get("latitude"),
            "Hastane Lon":   hos.get("longitude"),
        })

    return pd.DataFrame(satirlar)
