# mobile_app/main.py
# ============================================================
# PharmaFieldTracker — Flet Mobil Uygulaması (Android APK)
# Flet 0.23.2 + httpx tabanlı Supabase bağlantısı
# GPS: flet_geolocator 0.23.2
# ============================================================

import flet as ft
from datetime import datetime, timezone
import asyncio
import math

from supabase_client import sb_select, sb_insert, sb_update


# ── Yardımcı ──────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def suphe_puani(visit: dict, adimlar: list, loglar: list, aktif_adim_sayisi: int) -> int:
    """Ziyaret bitişinde çağrılır. 0-100 puan döner."""
    puan = 0
    sure = visit.get("total_duration_seconds") or 0

    # 1. Konum
    if visit.get("gps_latitude") and visit.get("gps_longitude"):
        try:
            docs = sb_select("doctors", "hospital_id,hospitals(latitude,longitude)",
                             filters={"id": f"eq.{visit['doctor_id']}"}, single=True)
            h = (docs.get("hospitals") or {})
            if h.get("latitude"):
                m = haversine(visit["gps_latitude"], visit["gps_longitude"],
                              h["latitude"], h["longitude"])
                if m > 500:
                    puan += 40
        except Exception:
            pass

    # 2. Süre
    if sure < 90:
        puan += 30
    elif sure < 300:
        puan += 10

    # 3. Eksik adım
    eksik = max(0, aktif_adim_sayisi - len(adimlar))
    puan += min(eksik * 15, 60)

    # 4. Tap yoğunluğu
    toplam_tap = sum(l.get("event_value", 0) for l in loglar)
    dakika = sure / 60 if sure > 0 else 1
    if (toplam_tap / dakika) < 2:
        puan += 20

    return min(puan, 100)


# ── Uygulama Durumu ───────────────────────────────────────────

class State:
    kullanici     = None           # giriş yapan user dict
    aktif_vid     = None           # ekranda açık visit_id
    tap_sayac: dict[int, int] = {} # {visit_id: tap_count}
    sureler:   dict[int, int] = {} # {visit_id: saniye}
    gorev_aktif   = False


S = State()


# ── Ana Fonksiyon ─────────────────────────────────────────────

async def main(page: ft.Page):
    page.title  = "PharmaFieldTracker"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor    = ft.Colors.GREY_50
    page.padding    = 0

    # ── Arka plan görevleri ───────────────────────────────────

    async def tap_kaydet_gorevi():
        """Her 30 sn'de tap sayılarını Supabase'e yazar."""
        while S.gorev_aktif:
            await asyncio.sleep(30)
            for vid, sayac in list(S.tap_sayac.items()):
                if sayac > 0:
                    try:
                        sb_insert("activity_logs", {
                            "visit_id":   vid,
                            "event_type": "tap",
                            "event_value": sayac,
                            "timestamp":  datetime.now(timezone.utc).isoformat(),
                        })
                        S.tap_sayac[vid] = 0
                    except Exception:
                        pass

    sure_text = ft.Ref[ft.Text]()

    async def sure_gorevi():
        """Her saniye aktif ziyaretlerin süresini artırır."""
        while S.gorev_aktif:
            await asyncio.sleep(1)
            for vid in list(S.sureler):
                S.sureler[vid] = S.sureler.get(vid, 0) + 1
            if S.aktif_vid and sure_text.current:
                s = S.sureler.get(S.aktif_vid, 0)
                dk, sn = divmod(s, 60)
                sure_text.current.value = f"⏱ {dk:02d}:{sn:02d}"
                try:
                    await page.update_async()
                except Exception:
                    pass

    def tap(vid):
        if vid:
            S.tap_sayac[vid] = S.tap_sayac.get(vid, 0) + 1

    # ── GPS yardımcısı ────────────────────────────────────────

    async def gps_al() -> tuple:
        try:
            gl = ft.Geolocator()
            page.overlay.append(gl)
            await page.update_async()
            await gl.request_permission_async(ft.GeolocatorPermission.WHEN_IN_USE)
            k = await gl.get_current_position_async()
            return k.latitude, k.longitude
        except Exception:
            return None, None

    # ══════════════════════════════════════════════════════════
    # GİRİŞ EKRANI
    # ══════════════════════════════════════════════════════════

    async def giris_goster():
        page.controls.clear()
        S.aktif_vid = None

        k_field = ft.TextField(label="Kullanıcı Adı", prefix_icon=ft.Icons.PERSON,
                               border_radius=12, filled=True)
        s_field = ft.TextField(label="Şifre", password=True, can_reveal_password=True,
                               prefix_icon=ft.Icons.LOCK, border_radius=12, filled=True)
        hata    = ft.Text("", color=ft.Colors.RED_600, size=13)

        async def giris(e):
            tap(None)
            kadi = k_field.value.strip()
            sifre = s_field.value.strip()
            if not kadi or not sifre:
                hata.value = "Kullanıcı adı ve şifre girin."
                await page.update_async(); return
            try:
                sonuc = sb_select("users", "*",
                                  filters={"username": f"eq.{kadi}",
                                           "password": f"eq.{sifre}",
                                           "role":     "eq.agent"})
                if sonuc:
                    S.kullanici = sonuc[0]
                    S.gorev_aktif = True
                    asyncio.create_task(tap_kaydet_gorevi())
                    asyncio.create_task(sure_gorevi())
                    await ana_goster()
                else:
                    hata.value = "Hatalı bilgi veya yetki yok."
                    await page.update_async()
            except Exception as ex:
                hata.value = f"Bağlantı hatası: {str(ex)[:60]}"
                await page.update_async()

        page.add(
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                    colors=["#1565C0", "#42A5F5"]
                ),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.LOCAL_PHARMACY, size=72, color=ft.Colors.WHITE),
                        ft.Text("PharmaField", size=28, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE),
                        ft.Text("Tracker", size=18, color=ft.Colors.WHITE70),
                        ft.Container(height=30),
                        ft.Container(
                            width=340, padding=ft.padding.all(24),
                            border_radius=20, bgcolor=ft.Colors.WHITE,
                            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.BLACK26),
                            content=ft.Column(spacing=14, controls=[
                                ft.Text("Giriş Yap", size=20, weight=ft.FontWeight.BOLD),
                                k_field, s_field, hata,
                                ft.ElevatedButton(
                                    "GİRİŞ YAP", on_click=giris, width=300, height=48,
                                    style=ft.ButtonStyle(
                                        bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE,
                                        shape=ft.RoundedRectangleBorder(radius=12)
                                    )
                                ),
                            ])
                        ),
                    ]
                )
            )
        )
        await page.update_async()

    # ══════════════════════════════════════════════════════════
    # ANA EKRAN
    # ══════════════════════════════════════════════════════════

    async def ana_goster():
        page.controls.clear()
        S.aktif_vid = None

        try:
            # Devam eden ziyaretler (end_time IS NULL)
            devam = sb_select(
                "visits",
                "id,start_time,doctor_id,doctors(name,hospitals(name))",
                filters={"user_id": f"eq.{S.kullanici['id']}", "end_time": "is.null"}
            )
            # Tüm doktorlar
            doktorlar = sb_select(
                "doctors", "id,name,branch,hospitals(name)", order="name.asc"
            )
        except Exception as ex:
            page.add(ft.Text(f"Veri hatası: {ex}", color=ft.Colors.RED))
            await page.update_async(); return

        # ── Devam eden kart listesi ──
        devam_cards = []
        for z in (devam or []):
            doc_adi = (z.get("doctors") or {}).get("name", "?")
            has_adi = ((z.get("doctors") or {}).get("hospitals") or {}).get("name", "?")
            bas = datetime.fromisoformat(z["start_time"].replace("Z", "+00:00"))
            gecen = int((datetime.now(timezone.utc) - bas).total_seconds())
            if z["id"] not in S.sureler:
                S.sureler[z["id"]] = gecen
            S.tap_sayac.setdefault(z["id"], 0)
            dk, sn = divmod(gecen, 60)

            async def devam_et(e, vid=z["id"]):
                tap(vid); await ziyaret_goster(vid)

            devam_cards.append(ft.Card(elevation=2, child=ft.ListTile(
                leading=ft.Icon(ft.Icons.MEDICAL_SERVICES, color=ft.Colors.ORANGE_700),
                title=ft.Text(doc_adi, weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f"{has_adi} • {dk:02d}:{sn:02d} geçti"),
                trailing=ft.IconButton(icon=ft.Icons.ARROW_FORWARD, on_click=devam_et),
            )))

        # ── Doktor kart listesi ──
        dok_cards = []
        for d in (doktorlar or []):
            has = (d.get("hospitals") or {}).get("name", "?")

            async def baslat(e, dok=d):
                tap(S.aktif_vid); await yeni_ziyaret(dok)

            dok_cards.append(ft.Card(elevation=1, child=ft.ListTile(
                leading=ft.CircleAvatar(
                    content=ft.Text(d["name"][0], color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700
                ),
                title=ft.Text(d["name"]),
                subtitle=ft.Text(f"{d.get('branch','?')} • {has}"),
                trailing=ft.ElevatedButton(
                    "Ziyaret", on_click=baslat,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
                ),
            )))

        async def cikis(e):
            S.kullanici = None
            S.gorev_aktif = False
            S.tap_sayac.clear(); S.sureler.clear()
            await giris_goster()

        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[
            # Üst bar
            ft.Container(
                padding=ft.padding.symmetric(horizontal=16, vertical=12),
                bgcolor=ft.Colors.BLUE_700,
                content=ft.Row(controls=[
                    ft.Icon(ft.Icons.LOCAL_PHARMACY, color=ft.Colors.WHITE),
                    ft.Text(f"Merhaba, {S.kullanici['full_name']}",
                            color=ft.Colors.WHITE, size=16, expand=True),
                    ft.IconButton(icon=ft.Icons.LOGOUT, icon_color=ft.Colors.WHITE, on_click=cikis),
                ])
            ),
            # Devam edenler
            ft.Container(padding=ft.padding.all(12), content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PLAY_CIRCLE, color=ft.Colors.ORANGE_700),
                    ft.Text("Devam Eden Ziyaretler", size=16, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Text(str(len(devam_cards)), color=ft.Colors.WHITE, size=12),
                        bgcolor=ft.Colors.ORANGE_700, border_radius=10,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2)
                    )
                ]),
                ft.Text("Devam eden ziyaret yok.", color=ft.Colors.GREY_500)
                if not devam_cards else ft.Column(devam_cards),
            ])),
            ft.Divider(),
            # Doktorlar
            ft.Container(padding=ft.padding.symmetric(horizontal=12, vertical=4), content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PERSON_SEARCH, color=ft.Colors.BLUE_700),
                    ft.Text("Doktorlar", size=16, weight=ft.FontWeight.BOLD),
                ]),
                ft.Column(dok_cards) if dok_cards
                else ft.Text("Doktor bulunamadı.", color=ft.Colors.GREY_500),
            ])),
        ]))
        await page.update_async()

    # ══════════════════════════════════════════════════════════
    # YENİ ZİYARET BAŞLAT
    # ══════════════════════════════════════════════════════════

    async def yeni_ziyaret(doktor: dict):
        lat, lon = await gps_al()
        try:
            kayit = sb_insert("visits", {
                "user_id":       S.kullanici["id"],
                "doctor_id":     doktor["id"],
                "start_time":    datetime.now(timezone.utc).isoformat(),
                "gps_latitude":  lat,
                "gps_longitude": lon,
            })
            vid = kayit["id"]
            S.tap_sayac[vid] = 0
            S.sureler[vid]   = 0
            await ziyaret_goster(vid)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Hata: {ex}"), open=True)
            await page.update_async()

    # ══════════════════════════════════════════════════════════
    # ZİYARET EKRANI
    # ══════════════════════════════════════════════════════════

    async def ziyaret_goster(visit_id: int):
        S.aktif_vid = visit_id
        page.controls.clear()

        try:
            z = sb_select(
                "visits", "*, doctors(name,branch,hospitals(name))",
                filters={"id": f"eq.{visit_id}"}, single=True
            )
            adimlar = sb_select(
                "visit_flows", "*",
                filters={"is_active": "eq.true"}, order="step_order.asc"
            )
            tamamlanan_raw = sb_select(
                "visit_steps", "flow_step_id",
                filters={"visit_id": f"eq.{visit_id}"}
            )
            tamamlanan_ids = {s["flow_step_id"] for s in (tamamlanan_raw or [])}
        except Exception as ex:
            page.add(ft.Text(f"Veri hatası: {ex}", color=ft.Colors.RED))
            await page.update_async(); return

        dok_adi = (z.get("doctors") or {}).get("name", "?")
        has_adi = ((z.get("doctors") or {}).get("hospitals") or {}).get("name", "?")
        not_field = ft.TextField(
            label="Ziyaret notu",
            multiline=True, min_lines=2, max_lines=4,
            value=z.get("notes") or "",
            border_radius=10, filled=True,
        )

        # ── Adım listesi ──
        adim_col = ft.Column(spacing=8)

        async def adim_tamamla(e, adim_id: int):
            tap(visit_id)
            if adim_id in tamamlanan_ids:
                return
            alat, alon = await gps_al()
            try:
                sb_insert("visit_steps", {
                    "visit_id":    visit_id,
                    "flow_step_id": adim_id,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "gps_latitude": alat,
                    "gps_longitude": alon,
                })
                tamamlanan_ids.add(adim_id)
                await ziyaret_goster(visit_id)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Hata: {ex}"), open=True)
                await page.update_async()

        for a in (adimlar or []):
            tamam = a["id"] in tamamlanan_ids
            adim_col.controls.append(ft.Container(
                border_radius=10,
                bgcolor=ft.Colors.GREEN_50 if tamam else ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.GREEN_400 if tamam else ft.Colors.GREY_300),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE if tamam else ft.Icons.RADIO_BUTTON_UNCHECKED,
                            color=ft.Colors.GREEN_600 if tamam else ft.Colors.GREY_400, size=22),
                    ft.Text(f"{a['step_order']}. {a['step_name']}", expand=True,
                            color=ft.Colors.GREY_600 if tamam else ft.Colors.BLACK,
                            weight=ft.FontWeight.W_500),
                    ft.IconButton(
                        icon=ft.Icons.CHECK,
                        icon_color=ft.Colors.GREEN_700 if not tamam else ft.Colors.TRANSPARENT,
                        disabled=tamam,
                        on_click=lambda e, aid=a["id"]: adim_tamamla(e, aid),
                    ) if not tamam else ft.Container(width=40),
                ])
            ))

        # ── Ziyareti bitir ──
        async def bitir(e):
            tap(visit_id)
            sure = S.sureler.get(visit_id, 0)

            # Kalan tap'leri kaydet
            kalan = S.tap_sayac.get(visit_id, 0)
            if kalan > 0:
                try:
                    sb_insert("activity_logs", {
                        "visit_id": visit_id, "event_type": "tap",
                        "event_value": kalan,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    pass

            # Şüphe puanı
            try:
                t_adimlar = sb_select("visit_steps", "*", filters={"visit_id": f"eq.{visit_id}"}) or []
                t_loglar  = sb_select("activity_logs", "*", filters={"visit_id": f"eq.{visit_id}"}) or []
                puan = suphe_puani(z, t_adimlar, t_loglar, len(adimlar or []))
            except Exception:
                puan = 0

            try:
                sb_update("visits", {
                    "end_time":                datetime.now(timezone.utc).isoformat(),
                    "total_duration_seconds":  sure,
                    "suspicion_score":         puan,
                    "notes":                   not_field.value.strip() or None,
                }, "id", visit_id)

                S.tap_sayac.pop(visit_id, None)
                S.sureler.pop(visit_id, None)
                S.aktif_vid = None

                page.snack_bar = ft.SnackBar(
                    ft.Text("✓ Ziyaret tamamlandı!", color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.GREEN_700, open=True
                )
                await page.update_async()
                await ana_goster()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Hata: {ex}"), open=True)
                await page.update_async()

        async def geri(e):
            tap(visit_id)
            try:
                sb_update("visits", {"notes": not_field.value.strip() or None}, "id", visit_id)
            except Exception:
                pass
            await ana_goster()

        sure_s = S.sureler.get(visit_id, 0)
        dk, sn = divmod(sure_s, 60)

        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[
            # Üst bar
            ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=10),
                bgcolor=ft.Colors.BLUE_700,
                content=ft.Row([
                    ft.IconButton(icon=ft.Icons.ARROW_BACK,
                                  icon_color=ft.Colors.WHITE, on_click=geri),
                    ft.Column(expand=True, spacing=2, controls=[
                        ft.Text(dok_adi, color=ft.Colors.WHITE, size=16,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(has_adi, color=ft.Colors.WHITE70, size=12),
                    ]),
                    ft.Text(f"⏱ {dk:02d}:{sn:02d}", color=ft.Colors.WHITE,
                            size=16, ref=sure_text),
                ])
            ),
            # Adımlar
            ft.Container(padding=ft.padding.all(12), content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CHECKLIST, color=ft.Colors.BLUE_700),
                    ft.Text("Ziyaret Adımları", size=15, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{len(tamamlanan_ids)}/{len(adimlar or [])}",
                            color=ft.Colors.BLUE_600),
                ]),
                adim_col,
            ])),
            ft.Divider(),
            # Not
            ft.Container(padding=ft.padding.symmetric(horizontal=12, vertical=4), content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.NOTE_ALT, color=ft.Colors.BLUE_700),
                    ft.Text("Ziyaret Notu", size=15, weight=ft.FontWeight.BOLD),
                ]),
                not_field,
            ])),
            # Bitir butonu
            ft.Container(padding=ft.padding.all(16), content=ft.ElevatedButton(
                "ZİYARETİ TAMAMLA", icon=ft.Icons.CHECK_CIRCLE, on_click=bitir,
                width=float("inf"), height=50,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=12)
                )
            )),
        ]))
        await page.update_async()

    # Başlat
    await giris_goster()


if __name__ == "__main__":
    ft.app(target=main)
