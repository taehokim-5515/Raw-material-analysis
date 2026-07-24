# -*- coding: utf-8 -*-
"""데이터 계층 — Supabase(PostgreSQL) 우선, secrets 없으면 Excel(main_db.xlsx) 폴백.
fact 3종(price_actual/production_plan/price_forecast)만 DB, dim(BOM·매핑)은 파일 유지."""
import re
from collections import defaultdict
import pandas as pd
from . import config as C

# ---------------- 백엔드 선택 ----------------
_SB = None          # supabase client (lazy)
_SB_TRIED = False

def _read_secrets():
    """streamlit 런타임 밖(스크립트)에서도 secrets.toml 읽기."""
    try:
        import streamlit as st
        if "supabase" in st.secrets:
            return dict(st.secrets["supabase"])
    except Exception:
        pass
    try:
        import toml
        p = C.ROOT / ".streamlit" / "secrets.toml"
        if p.exists():
            return toml.load(p).get("supabase")
    except Exception:
        pass
    return None

def _sb():
    """Supabase 클라이언트. 미설정이면 None(→Excel 폴백)."""
    global _SB, _SB_TRIED
    if _SB_TRIED:
        return _SB
    _SB_TRIED = True
    cfg = _read_secrets()
    if cfg and cfg.get("url") and cfg.get("key"):
        try:
            from supabase import create_client
            url = str(cfg["url"]).replace("/rest/v1", "").rstrip("/")
            _SB = create_client(url, cfg["key"])
        except Exception:
            _SB = None
    return _SB

def backend():
    return "supabase" if _sb() else "excel"

def _fetch_all(table):
    """PostgREST 1000행 제한 → 페이지네이션 전체 조회."""
    sb = _sb(); out = []; step = 1000; i = 0
    while True:
        rows = sb.table(table).select("*").range(i, i + step - 1).execute().data
        out.extend(rows)
        if len(rows) < step:
            break
        i += step
    return out

def _replace_months(table, months_dict, to_rows):
    """해당 년월 삭제 후 일괄 삽입(월 단위 전체 교체 = 기존 Excel 방식과 동일 의미)."""
    sb = _sb()
    yms = list(months_dict.keys())
    sb.table(table).delete().in_("ym", yms).execute()
    rows = []
    for ym, df in months_dict.items():
        rows.extend(to_rows(ym, df))
    for i in range(0, len(rows), 500):
        sb.table(table).insert(rows[i:i + 500]).execute()

# ---------------- 로더 ----------------
_PRICE_COLS = ["년월", "원료코드", "원료명", "단가", "실적사용kg", "실적금액"]

def load_price():
    """원료단가사용: 년월·원료코드·원료명·단가·실적사용kg·실적금액"""
    if _sb():
        rows = _fetch_all("price_actual")
        if not rows:
            return pd.DataFrame(columns=_PRICE_COLS)
        df = pd.DataFrame(rows).rename(columns={
            "ym": "년월", "code": "원료코드", "name": "원료명",
            "price": "단가", "qty_kg": "실적사용kg", "amount": "실적금액"})
        df["원료코드"] = df["원료코드"].astype(str)
        return df[_PRICE_COLS]
    return pd.read_excel(C.MAIN_DB, sheet_name="원료단가사용", dtype={"원료코드": str})

def load_plan():
    """생산계획: 년월·표준제품·계획중량"""
    if _sb():
        rows = _fetch_all("production_plan")
        if not rows:
            return pd.DataFrame(columns=["년월", "표준제품", "계획중량"])
        df = pd.DataFrame(rows).rename(columns={
            "ym": "년월", "product": "표준제품", "weight_kg": "계획중량"})
        return df[["년월", "표준제품", "계획중량"]]
    return pd.read_excel(C.MAIN_DB, sheet_name="생산계획")

def load_forecast():
    """예상단가: 년월·원료코드·원료명·단가"""
    if _sb():
        rows = _fetch_all("price_forecast")
        if not rows:
            return pd.DataFrame(columns=["년월", "원료코드", "원료명", "단가"])
        df = pd.DataFrame(rows).rename(columns={
            "ym": "년월", "code": "원료코드", "name": "원료명", "price": "단가"})
        df["원료코드"] = df["원료코드"].astype(str)
        return df[["년월", "원료코드", "원료명", "단가"]]
    try:
        return pd.read_excel(C.MAIN_DB, sheet_name="예상단가", dtype={"원료코드": str})
    except Exception:
        return pd.DataFrame(columns=["년월", "원료코드", "원료명", "단가"])

# dim은 파일 유지
def load_bom():
    return pd.read_excel(C.BOM_XLSX, sheet_name="BOM", dtype={"ERP코드": str})

def load_material_master():
    return pd.read_excel(C.BOM_XLSX, sheet_name="원료마스터", dtype={"ERP코드": str})

def load_mapping():
    mp = pd.read_excel(C.MAPPING_XLSX, sheet_name="매핑표")
    base2std = dict(zip(mp["파일_품목명(base)"], mp["표준(MRP)명칭"]))
    return mp, base2std

def months_price():
    return sorted(load_price()["년월"].astype(str).unique())

def months_plan():
    return sorted(load_plan()["년월"].astype(str).unique())

def price_name_map(ym):
    p = load_price()
    sub = p[p["년월"].astype(str) == ym]
    return dict(zip(sub["원료코드"], sub["원료명"]))

# ---------------- 라이터 ----------------
def _write_sheet(sheet, df):
    with pd.ExcelWriter(C.MAIN_DB, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as w:
        df.to_excel(w, sheet_name=sheet, index=False)

def _price_rows(ym, df):
    df = df.fillna({"원료명": "", "단가": 0, "실적사용kg": 0, "실적금액": 0})
    return [{"ym": ym, "code": str(r["원료코드"]), "name": str(r.get("원료명", "")),
             "price": float(r["단가"]), "qty_kg": float(r["실적사용kg"]),
             "amount": float(r["실적금액"])} for _, r in df.iterrows()]

def _plan_rows(ym, df):
    return [{"ym": ym, "product": str(r["표준제품"]),
             "weight_kg": float(r["계획중량"])} for _, r in df.iterrows()]

def _forecast_rows(ym, df):
    df = df.fillna({"원료명": "", "단가": 0})
    return [{"ym": ym, "code": str(r["원료코드"]), "name": str(r.get("원료명", "")),
             "price": float(r["단가"])} for _, r in df.iterrows()]

def upsert_plan(ym, plan_rows):
    return upsert_plan_multi({ym: plan_rows})

def upsert_plan_multi(months_dict):
    if _sb():
        _replace_months("production_plan", months_dict, _plan_rows)
        return load_plan()
    cur = load_plan()
    cur = cur[~cur["년월"].astype(str).isin(list(months_dict.keys()))]
    adds = []
    for ym, df in months_dict.items():
        a = df.copy(); a.insert(0, "년월", ym); adds.append(a)
    out = pd.concat([cur] + adds, ignore_index=True) if adds else cur
    _write_sheet("생산계획", out)
    return out

def upsert_price(ym, price_rows):
    return upsert_price_multi({ym: price_rows})

def upsert_price_multi(months_dict):
    if _sb():
        _replace_months("price_actual", months_dict, _price_rows)
        return load_price()
    cur = load_price()
    cur = cur[~cur["년월"].astype(str).isin(list(months_dict.keys()))]
    adds = []
    for ym, df in months_dict.items():
        a = df.copy(); a.insert(0, "년월", ym); adds.append(a)
    out = pd.concat([cur] + adds, ignore_index=True) if adds else cur
    _write_sheet("원료단가사용", out)
    return out

def upsert_forecast_multi(months_dict):
    if _sb():
        _replace_months("price_forecast", months_dict, _forecast_rows)
        return load_forecast()
    cur = load_forecast()
    cur = cur[~cur["년월"].astype(str).isin(list(months_dict.keys()))]
    adds = []
    for ym, df in months_dict.items():
        a = df.copy(); a.insert(0, "년월", ym); adds.append(a)
    out = pd.concat([cur] + adds, ignore_index=True) if adds else cur
    _write_sheet("예상단가", out)
    return out
