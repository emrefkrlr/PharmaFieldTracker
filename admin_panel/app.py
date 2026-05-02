# admin_panel/app.py
# ============================================================
# PharmaFieldTracker — Streamlit Yönetici Paneli
# Ana dosya. Streamlit Cloud'da deploy edilir.
# Main file path: admin_panel/app.py
# ============================================================

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import date, timedelta

from supabase_client import get_supabase
from utils import (
    suphe_puani_hesapla, toplu_puan_guncelle,
    puan_rengi, puan_etiketi, ziyaretleri_getir,
)

# ── Sayfa ayarları ────────────────────────────────────────────
st.set_page_config(
    page_title="PharmaFieldTracker — Yönetici",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Giriş ────────────────────────────────────────────────────
def giris_ekrani():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 💊 PharmaFieldTracker")
        st.markdown("### Yönetici Paneli")
        with st.form("giris"):
            kullanici = st.text_input("Kullanıcı Adı")
            sifre     = st.text_input("Şifre", type="password")
            btn       = st.form_submit_button("Giriş Yap", use_container_width=True)
        if btn:
            if not kullanici or not sifre:
                st.error("Kullanıcı adı ve şifre girin.")
                return
            db = get_supabase()
            r  = db.table("users").select("*")\
                   .eq("username", kullanici).eq("password", sifre)\
                   .eq("role", "admin").execute()
            if r.data:
                st.session_state["kullanici"] = r.data[0]
                st.rerun()
            else:
                st.error("Hatalı bilgi veya yetki yok.")

if "kullanici" not in st.session_state:
    giris_ekrani()
    st.stop()

kullanici = st.session_state["kullanici"]
db = get_supabase()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 💊 PharmaField")
    st.markdown(f"**{kullanici['full_name']}** *(Admin)*")
    st.divider()
    sayfa = st.radio("Menü", [
        "📊 Dashboard",
        "🔄 Akış Yönetimi",
        "👨‍⚕️ Doktor Yönetimi",
        "📋 Ziyaret Raporları",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("🚪 Çıkış", use_container_width=True):
        del st.session_state["kullanici"]
        st.rerun()


# ══════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════
if sayfa == "📊 Dashboard":
    st.title("📊 Ana Gösterge Paneli")

    try:
        ziyaretler = db.table("visits").select(
            "id, start_time, suspicion_score, users(full_name)"
        ).not_.is_("end_time", "null").execute().data or []

        toplam     = len(ziyaretler)
        puanlilar  = [z for z in ziyaretler if z.get("suspicion_score") is not None]
        ort_puan   = round(sum(z["suspicion_score"] for z in puanlilar) / len(puanlilar), 1) if puanlilar else 0
        supheli    = sum(1 for z in puanlilar if z["suspicion_score"] >= 50)
        cok_suph   = sum(1 for z in puanlilar if z["suspicion_score"] >= 70)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏥 Toplam Ziyaret",    toplam)
        c2.metric("📈 Ortalama Puan",     f"{ort_puan}/100")
        c3.metric("🟡 Şüpheli (≥50)",     supheli)
        c4.metric("🔴 Çok Şüpheli (≥70)", cok_suph)
        st.divider()

        col_g, col_b = st.columns(2)

        # Son 7 gün çizgi grafiği
        with col_g:
            st.subheader("📈 Son 7 Gün — Ortalama Puan")
            bugun = date.today()
            gunluk = {}
            for i in range(6, -1, -1):
                gun = bugun - timedelta(days=i)
                gun_str = gun.strftime("%m/%d")
                gun_puanlar = [
                    z["suspicion_score"] for z in puanlilar
                    if (z.get("start_time") or "").startswith(str(gun))
                ]
                gunluk[gun_str] = round(sum(gun_puanlar)/len(gun_puanlar), 1) if gun_puanlar else 0
            df_g = pd.DataFrame({"Ortalama Puan": gunluk}).rename_axis("Tarih")
            st.line_chart(df_g, color="#F44336")

        # Eleman bar chart
        with col_b:
            st.subheader("👤 Eleman Bazlı Ortalama Puan")
            ep, es = {}, {}
            for z in puanlilar:
                ad = (z.get("users") or {}).get("full_name", "?")
                ep[ad] = ep.get(ad, 0) + z["suspicion_score"]
                es[ad] = es.get(ad, 0) + 1
            if ep:
                df_b = pd.DataFrame({
                    "Ortalama Puan": {e: round(ep[e]/es[e], 1) for e in ep}
                }).sort_values("Ortalama Puan", ascending=False)
                st.bar_chart(df_b, color="#FF9800")
            else:
                st.info("Henüz puanlı ziyaret yok.")

        st.divider()
        st.subheader("🔧 Admin Araçları")
        if st.button("🔄 Tüm Puanları Yeniden Hesapla"):
            with st.spinner("Hesaplanıyor..."):
                n = toplu_puan_guncelle()
            st.success(f"✅ {n} ziyaret güncellendi.")

    except Exception as ex:
        st.error(f"Veri hatası: {ex}")


# ══════════════════════════════════════════════════════════════
# AKIŞ YÖNETİMİ
# ══════════════════════════════════════════════════════════════
elif sayfa == "🔄 Akış Yönetimi":
    st.title("🔄 Ziyaret Akış Adımları")

    if "akis_v" not in st.session_state:
        st.session_state["akis_v"] = 0

    try:
        adimlar = db.table("visit_flows").select("*").order("step_order").execute().data or []
    except Exception as ex:
        st.error(f"Veri hatası: {ex}"); st.stop()

    st.subheader(f"Mevcut Adımlar ({len(adimlar)})")

    for i, a in enumerate(adimlar):
        c_no, c_ad, c_tog, c_up, c_dn, c_del = st.columns([1, 4, 2, 1, 1, 1])
        c_no.markdown(f"**{a['step_order']}.**")
        c_ad.markdown(a["step_name"])
        c_tog.markdown("🟢 Aktif" if a["is_active"] else "⚫ Pasif")

        with c_tog:
            lbl = "Pasif Yap" if a["is_active"] else "Aktif Yap"
            if st.button(lbl, key=f"tog_{a['id']}"):
                db.table("visit_flows").update({"is_active": not a["is_active"]}).eq("id", a["id"]).execute()
                st.session_state["akis_v"] += 1; st.rerun()

        with c_up:
            if i > 0 and st.button("⬆", key=f"up_{a['id']}"):
                prev = adimlar[i-1]
                db.table("visit_flows").update({"step_order": -1}).eq("id", a["id"]).execute()
                db.table("visit_flows").update({"step_order": a["step_order"]}).eq("id", prev["id"]).execute()
                db.table("visit_flows").update({"step_order": prev["step_order"]}).eq("id", a["id"]).execute()
                st.session_state["akis_v"] += 1; st.rerun()

        with c_dn:
            if i < len(adimlar)-1 and st.button("⬇", key=f"dn_{a['id']}"):
                nxt = adimlar[i+1]
                db.table("visit_flows").update({"step_order": -1}).eq("id", a["id"]).execute()
                db.table("visit_flows").update({"step_order": a["step_order"]}).eq("id", nxt["id"]).execute()
                db.table("visit_flows").update({"step_order": nxt["step_order"]}).eq("id", a["id"]).execute()
                st.session_state["akis_v"] += 1; st.rerun()

        with c_del:
            if st.button("🗑", key=f"del_{a['id']}"):
                db.table("visit_flows").delete().eq("id", a["id"]).execute()
                st.session_state["akis_v"] += 1; st.rerun()

    st.divider()
    st.subheader("➕ Yeni Adım")
    with st.form("yeni_adim"):
        yeni = st.text_input("Adım Adı")
        if st.form_submit_button("Ekle", use_container_width=True):
            if not yeni.strip():
                st.warning("Adım adı boş olamaz.")
            else:
                max_o = max((a["step_order"] for a in adimlar), default=0)
                db.table("visit_flows").insert({"step_order": max_o+1, "step_name": yeni.strip(), "is_active": True}).execute()
                st.success(f"✅ '{yeni}' eklendi."); st.rerun()


# ══════════════════════════════════════════════════════════════
# DOKTOR YÖNETİMİ
# ══════════════════════════════════════════════════════════════
elif sayfa == "👨‍⚕️ Doktor Yönetimi":
    st.title("👨‍⚕️ Doktor Yönetimi")

    try:
        hastaneler = db.table("hospitals").select("*").order("name").execute().data or []
        doktorlar  = db.table("doctors").select("*, hospitals(name)").order("name").execute().data or []
    except Exception as ex:
        st.error(f"Veri hatası: {ex}"); st.stop()

    h_map  = {h["name"]: h["id"] for h in hastaneler}
    h_list = [h["name"] for h in hastaneler]

    # Doktor listesi
    st.subheader(f"Kayıtlı Doktorlar ({len(doktorlar)})")
    for d in doktorlar:
        h_adi = (d.get("hospitals") or {}).get("name", "?")
        ca, cb, cc, cd, ce = st.columns([3, 3, 2, 1, 1])
        ca.markdown(f"**{d['name']}**")
        cb.markdown(h_adi)
        cc.markdown(d.get("branch") or "-")
        if cd.button("✏️", key=f"ed_{d['id']}"):
            st.session_state["duzenle"] = d
        if ce.button("🗑", key=f"dl_{d['id']}"):
            db.table("doctors").delete().eq("id", d["id"]).execute()
            st.rerun()

    # Düzenleme formu
    if "duzenle" in st.session_state:
        d = st.session_state["duzenle"]
        st.divider()
        st.subheader(f"✏️ Düzenle: {d['name']}")
        with st.form("duzenle_form"):
            ad  = st.text_input("Ad", value=d["name"])
            mh  = (d.get("hospitals") or {}).get("name", h_list[0] if h_list else "")
            hos = st.selectbox("Hastane", h_list, index=h_list.index(mh) if mh in h_list else 0)
            brs = st.text_input("Branş", value=d.get("branch") or "")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Kaydet", use_container_width=True):
                db.table("doctors").update({"name": ad, "hospital_id": h_map[hos], "branch": brs or None}).eq("id", d["id"]).execute()
                del st.session_state["duzenle"]
                st.success("✅ Güncellendi."); st.rerun()
            if c2.form_submit_button("İptal", use_container_width=True):
                del st.session_state["duzenle"]; st.rerun()

    st.divider()

    # Yeni doktor
    st.subheader("➕ Yeni Doktor")
    if not h_list:
        st.warning("Önce hastane ekleyin.")
    else:
        with st.form("yeni_doktor"):
            ad  = st.text_input("Doktor Adı")
            hos = st.selectbox("Hastane", h_list)
            brs = st.text_input("Branş")
            if st.form_submit_button("Ekle", use_container_width=True):
                if not ad.strip():
                    st.warning("Ad boş olamaz.")
                else:
                    db.table("doctors").insert({"name": ad.strip(), "hospital_id": h_map[hos], "branch": brs.strip() or None}).execute()
                    st.success(f"✅ '{ad}' eklendi."); st.rerun()

    st.divider()

    # Hastane yönetimi
    with st.expander("🏥 Hastane Yönetimi"):
        for h in hastaneler:
            c1, c2, c3 = st.columns([4, 4, 1])
            c1.markdown(f"**{h['name']}**")
            c2.markdown(f"📍 {h.get('latitude','?')}, {h.get('longitude','?')}")
            if c3.button("🗑", key=f"dh_{h['id']}"):
                db.table("hospitals").delete().eq("id", h["id"]).execute(); st.rerun()
        st.subheader("Yeni Hastane")
        with st.form("yeni_hastane"):
            had = st.text_input("Hastane Adı")
            c1, c2 = st.columns(2)
            hlat = c1.number_input("Enlem", value=41.0082, format="%.6f")
            hlon = c2.number_input("Boylam", value=28.9784, format="%.6f")
            if st.form_submit_button("Ekle"):
                if not had.strip():
                    st.warning("Ad boş.")
                else:
                    db.table("hospitals").insert({"name": had.strip(), "latitude": hlat, "longitude": hlon}).execute()
                    st.rerun()


# ══════════════════════════════════════════════════════════════
# ZİYARET RAPORLARI
# ══════════════════════════════════════════════════════════════
elif sayfa == "📋 Ziyaret Raporları":
    st.title("📋 Ziyaret Raporları")

    # Filtreler
    with st.expander("🔍 Filtreler", expanded=True):
        with st.form("filtre"):
            c1, c2 = st.columns(2)
            bas = c1.date_input("Başlangıç", value=date.today()-timedelta(days=30))
            bit = c2.date_input("Bitiş",     value=date.today())

            try:
                elemanlar = db.table("users").select("id,full_name").eq("role","agent").execute().data or []
                e_map = {"Tümü": None, **{e["full_name"]: e["id"] for e in elemanlar}}
            except Exception:
                e_map = {"Tümü": None}

            try:
                dokt_raw = db.table("doctors").select("id,name").order("name").execute().data or []
                d_map = {"Tümü": None, **{d["name"]: d["id"] for d in dokt_raw}}
            except Exception:
                d_map = {"Tümü": None}

            c3, c4 = st.columns(2)
            sec_e = c3.selectbox("Eleman", list(e_map))
            sec_d = c4.selectbox("Doktor", list(d_map))
            aralik = st.slider("Şüphe Puanı", 0, 100, (0, 100))
            filtrele = st.form_submit_button("🔍 Filtrele", use_container_width=True)

    if filtrele or "rapor_df" not in st.session_state:
        with st.spinner("Yükleniyor..."):
            df = ziyaretleri_getir(
                baslangic=bas, bitis=bit,
                kullanici_id=e_map.get(sec_e),
                doktor_id=d_map.get(sec_d),
                min_puan=aralik[0], max_puan=aralik[1],
            )
        st.session_state["rapor_df"] = df

    df = st.session_state.get("rapor_df", pd.DataFrame())

    if df.empty:
        st.info("Kayıt bulunamadı."); st.stop()

    st.markdown(f"**{len(df)} ziyaret**")

    # CSV indir
    csv = df.drop(columns=["id","user_id","doctor_id","Ziyaret Lat","Ziyaret Lon",
                             "Hastane Lat","Hastane Lon"], errors="ignore").to_csv(index=False)
    st.download_button("📥 CSV İndir", csv, f"ziyaretler_{date.today()}.csv", "text/csv")
    st.divider()

    # Renkli tablo
    def puan_stil(val):
        if pd.isna(val): return "background-color:#F5F5F5;color:#9E9E9E"
        if val >= 70:    return "background-color:#FFEBEE;color:#C62828;font-weight:bold"
        if val >= 50:    return "background-color:#FFF8E1;color:#E65100;font-weight:bold"
        return "background-color:#E8F5E9;color:#2E7D32"

    goster = df[["Eleman","Doktor","Hastane","Başlama","Bitiş","Süre (sn)","Şüphe Puanı"]].copy()
    st.dataframe(goster.style.applymap(puan_stil, subset=["Şüphe Puanı"]),
                 use_container_width=True, height=300)
    st.divider()

    # Detay expander'lar
    st.subheader("🔎 Ziyaret Detayları")
    for _, row in df.iterrows():
        vid   = row["id"]
        puan  = row["Şüphe Puanı"]
        baslik = f"{puan_etiketi(puan)} | {row['Eleman']} → {row['Doktor']} ({row['Hastane']}) | {row['Başlama']}"

        with st.expander(baslik):
            cm, cp = st.columns([3,1])
            with cm:
                sure = row.get("Süre (sn)")
                if sure:
                    dk, sn = divmod(int(sure), 60)
                    st.markdown(f"⏱ **Süre:** {dk} dk {sn} sn")
                st.markdown(f"📝 **Not:** {row.get('Not') or '—'}")
            with cp:
                renk = puan_rengi(puan)
                st.markdown(
                    f"<div style='background:{renk};color:white;border-radius:8px;"
                    f"padding:12px;text-align:center;font-size:24px;font-weight:bold'>"
                    f"{puan if puan is not None else '?'}</div>",
                    unsafe_allow_html=True
                )

            t1, t2, t3 = st.tabs(["📋 Adımlar", "👆 Aktivite", "🗺️ Harita"])

            with t1:
                try:
                    adim_kayit = db.table("visit_steps").select(
                        "completed_at, visit_flows(step_name, step_order)"
                    ).eq("visit_id", vid).order("completed_at").execute().data or []
                    if adim_kayit:
                        rows = [{"Adım No": (a.get("visit_flows") or {}).get("step_order","?"),
                                 "Adım":    (a.get("visit_flows") or {}).get("step_name","?"),
                                 "Zaman":   a["completed_at"][:19].replace("T"," ")} for a in adim_kayit]
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("Adım kaydı yok.")
                except Exception as ex:
                    st.error(str(ex))

            with t2:
                try:
                    logs = db.table("activity_logs").select("*").eq("visit_id", vid).order("timestamp").execute().data or []
                    if logs:
                        df_a = pd.DataFrame([{"Zaman": l["timestamp"][:19].replace("T"," "),
                                              "Tip": l.get("event_type","?"),
                                              "Tap": l.get("event_value",0)} for l in logs])
                        st.dataframe(df_a, use_container_width=True, hide_index=True)
                        st.metric("Toplam Tap", df_a["Tap"].sum())
                    else:
                        st.info("Aktivite logu yok.")
                except Exception as ex:
                    st.error(str(ex))

            with t3:
                zlat, zlon = row.get("Ziyaret Lat"), row.get("Ziyaret Lon")
                hlat, hlon = row.get("Hastane Lat"), row.get("Hastane Lon")
                if not any([zlat, zlon, hlat, hlon]):
                    st.info("Konum bilgisi yok.")
                else:
                    mlat = zlat or hlat or 41.0082
                    mlon = zlon or hlon or 28.9784
                    m = folium.Map(location=[mlat, mlon], zoom_start=15)
                    if zlat and zlon:
                        folium.Marker([zlat, zlon],
                            tooltip="📍 Ziyaret Başlangıcı",
                            icon=folium.Icon(color="blue", icon="user", prefix="fa")
                        ).add_to(m)
                    if hlat and hlon:
                        folium.Marker([hlat, hlon],
                            tooltip=f"🏥 {row['Hastane']}",
                            icon=folium.Icon(color="red", icon="plus-sign")
                        ).add_to(m)
                    if all([zlat, zlon, hlat, hlon]):
                        folium.PolyLine([[zlat,zlon],[hlat,hlon]],
                            color="#F44336", weight=2, dash_array="5").add_to(m)
                    st_folium(m, width=700, height=300, returned_objects=[])
