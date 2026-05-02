# mobile_app/supabase_client.py
# -------------------------------------------------------
# supabase-py paketi YOK — httpx ile direkt REST API.
# APK build süresi: ~15 dakika (supabase paketi ile 3+ saat)
# -------------------------------------------------------

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

_URL = os.getenv("SUPABASE_URL", "")
_KEY = os.getenv("SUPABASE_ANON_KEY", "")

_HEADERS = {
    "apikey":        _KEY,
    "Authorization": f"Bearer {_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


class Table:
    """Tek tablo için sorgu zinciri."""

    def __init__(self, table: str):
        self._table   = table
        self._select  = "*"
        self._filters = {}
        self._order   = None
        self._single  = False
        self._is_null_col = None

    def select(self, cols: str):
        self._select = cols
        return self

    def eq(self, col: str, val):
        self._filters[col] = f"eq.{val}"
        return self

    def is_(self, col: str, val: str):
        # val: "null" veya "not.null"
        self._filters[col] = f"is.{val}"
        return self

    def not_(self):
        return _NotWrapper(self)

    def gte(self, col: str, val):
        self._filters[col] = f"gte.{val}"
        return self

    def lte(self, col: str, val):
        self._filters[col] = f"lte.{val}"
        return self

    def order(self, col: str, desc: bool = False):
        self._order = f"{col}.{'desc' if desc else 'asc'}"
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        params = {"select": self._select}
        params.update(self._filters)
        if self._order:
            params["order"] = self._order

        headers = dict(_HEADERS)
        if self._single:
            headers["Accept"] = "application/vnd.pgrst.object+json"

        with httpx.Client(timeout=20) as c:
            r = c.get(f"{_URL}/rest/v1/{self._table}", headers=headers, params=params)
            r.raise_for_status()
            return _Result(r.json())


class _NotWrapper:
    """not_ zinciri için yardımcı."""
    def __init__(self, table):
        self._t = table

    def is_(self, col: str, val: str):
        self._t._filters[col] = f"not.is.{val}"
        return self._t


class _Result:
    def __init__(self, data):
        self.data = data if isinstance(data, list) else [data] if data else []

    def single(self):
        return _SingleResult(self.data[0] if self.data else None)


class _SingleResult:
    def __init__(self, data):
        self.data = data


class SupabaseClient:
    """Basit Supabase REST istemcisi."""

    def table(self, name: str) -> Table:
        return Table(name)

    def _post(self, table: str, data: dict):
        with httpx.Client(timeout=20) as c:
            r = c.post(f"{_URL}/rest/v1/{table}", headers=_HEADERS, json=data)
            r.raise_for_status()
            j = r.json()
            return _Result(j if isinstance(j, list) else [j])

    def _patch(self, table: str, data: dict, filters: dict):
        params = {k: f"eq.{v}" for k, v in filters.items()}
        with httpx.Client(timeout=20) as c:
            r = c.patch(f"{_URL}/rest/v1/{table}", headers=_HEADERS, params=params, json=data)
            r.raise_for_status()
            j = r.json()
            return _Result(j if isinstance(j, list) else [j])


# Kullanım kolaylığı için yardımcı fonksiyonlar
def sb_select(table: str, cols: str = "*", filters: dict = None,
              order: str = None, single: bool = False):
    """SELECT sorgusu."""
    params = {"select": cols}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    headers = dict(_HEADERS)
    if single:
        headers["Accept"] = "application/vnd.pgrst.object+json"
    with httpx.Client(timeout=20) as c:
        r = c.get(f"{_URL}/rest/v1/{table}", headers=headers, params=params)
        r.raise_for_status()
        return r.json()


def sb_insert(table: str, data: dict) -> dict:
    """INSERT ve eklenen kaydı döner."""
    with httpx.Client(timeout=20) as c:
        r = c.post(f"{_URL}/rest/v1/{table}", headers=_HEADERS, json=data)
        r.raise_for_status()
        result = r.json()
        return result[0] if isinstance(result, list) else result


def sb_update(table: str, data: dict, eq_col: str, eq_val) -> None:
    """UPDATE — eq_col = eq_val şartıyla."""
    params = {eq_col: f"eq.{eq_val}"}
    with httpx.Client(timeout=20) as c:
        r = c.patch(f"{_URL}/rest/v1/{table}", headers=_HEADERS, params=params, json=data)
        r.raise_for_status()
