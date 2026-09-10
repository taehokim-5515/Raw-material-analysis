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

# ---------------- 배합비(BOM) — 버전 관리 ----------------
_BOM_COLS = ["적용시작", "표준명칭", "ERP코드", "원료한글명", "배합률"]


def load_bom_all():
    """버전 포함 전체 배합비.
    적용시작(YYYY-MM) = 그 배합이 적용되기 시작한 월. 종료월은 두지 않고,
    같은 제품의 다음 버전 적용시작 직전까지 유효하다(공백·중복 구간 불가)."""
    if _sb():
        try:
            rows = _fetch_all("bom")
        except Exception:
            rows = None          # 테이블 미생성 → 파일 시드로 폴백
        if rows:
            df = pd.DataFrame(rows).rename(columns={
                "eff_from": "적용시작", "product": "표준명칭", "code": "ERP코드",
                "name": "원료한글명", "ratio": "배합률"})
            df["ERP코드"] = df["ERP코드"].astype(str)
            df["적용시작"] = df["적용시작"].astype(str)
            for c in _BOM_COLS:
                if c not in df.columns:
                    df[c] = "" if c == "원료한글명" else 0
            return df[_BOM_COLS]
    return _bom_from_file()


def _bom_from_file():
    """bom_master.xlsx(BOM 시트) → 버전 스키마. 적용시작 없으면 기준버전으로 간주."""
    df = pd.read_excel(C.BOM_XLSX, sheet_name="BOM", dtype={"ERP코드": str})
    if "적용시작" not in df.columns:
        df["적용시작"] = C.BOM_BASE_YM
    if "원료한글명" not in df.columns:
        df["원료한글명"] = ""
    df["적용시작"] = df["적용시작"].astype(str)
    df["표준명칭"] = df["표준명칭"].astype(str)
    df["ERP코드"] = df["ERP코드"].astype(str)
    return df[_BOM_COLS]


def pick_bom_version(bom_all, ym=None):
    """제품별로 ym 시점에 유효한 버전만 남긴다(적용시작 ≤ ym 중 최신).
    ym=None이면 제품별 최신 버전."""
    d = bom_all.copy()
    d["적용시작"] = d["적용시작"].astype(str)
    if ym is not None:
        d = d[d["적용시작"] <= str(ym)]
    if d.empty:
        return d
    keep = d.groupby("표준명칭")["적용시작"].transform("max")
    return d[d["적용시작"] == keep]


def load_bom(ym=None):
    """(하위호환) 단일 배합비 표. ym 지정 시 그 달에 유효한 버전."""
    return pick_bom_version(load_bom_all(), ym)


def bom_versions():
    """버전 목록 — 적용시작별 제품수·행수."""
    a = load_bom_all()
    if a.empty:
        return pd.DataFrame(columns=["적용시작", "제품수", "원료행수"])
    g = (a.groupby("적용시작")
         .agg(제품수=("표준명칭", "nunique"), 원료행수=("ERP코드", "size"))
         .reset_index().sort_values("적용시작"))
    return g


def bom_version_products():
    """버전×제품 목록 — 배합률 합계 검증용."""
    a = load_bom_all()
    if a.empty:
        return pd.DataFrame(columns=["적용시작", "표준명칭", "원료수", "배합합%"])
    return (a.groupby(["적용시작", "표준명칭"])
            .agg(원료수=("ERP코드", "size"), **{"배합합%": ("배합률", "sum")})
            .reset_index().sort_values(["표준명칭", "적용시작"]))


def _write_bom(df):
    with pd.ExcelWriter(C.BOM_XLSX, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as w:
        df[_BOM_COLS].to_excel(w, sheet_name="BOM", index=False)


def _bom_rows(df, eff, note=None):
    return [{"eff_from": eff, "product": str(r["표준명칭"]), "code": str(r["ERP코드"]),
             "name": str(r.get("원료한글명") or ""), "ratio": float(r["배합률"]),
             "note": note} for _, r in df.iterrows()]


def upsert_bom_version(eff_from, df, note=None):
    """배합비 버전 저장 — 해당 적용시작월 × **업로드에 포함된 제품만** 교체.
    파일에 없는 제품의 기존 버전은 손대지 않는다."""
    eff = str(eff_from)
    d = df.copy()
    d["표준명칭"] = d["표준명칭"].astype(str)
    d["ERP코드"] = d["ERP코드"].astype(str)
    if "원료한글명" not in d.columns:
        d["원료한글명"] = ""
    prods = sorted(d["표준명칭"].unique())
    if _sb():
        sb = _sb()
        for i in range(0, len(prods), 100):
            sb.table("bom").delete().eq("eff_from", eff).in_("product", prods[i:i + 100]).execute()
        rows = _bom_rows(d, eff, note)
        for i in range(0, len(rows), 500):
            sb.table("bom").insert(rows[i:i + 500]).execute()
        return load_bom_all()
    cur = load_bom_all()
    cur = cur[~((cur["적용시작"] == eff) & (cur["표준명칭"].isin(prods)))]
    d["적용시작"] = eff
    out = pd.concat([cur, d[_BOM_COLS]], ignore_index=True)
    _write_bom(out)
    return out


def delete_bom_version(eff_from, products=None):
    """버전 삭제. products 지정 시 그 제품만."""
    eff = str(eff_from)
    if _sb():
        sb = _sb()
        q = sb.table("bom").delete().eq("eff_from", eff)
        if products:
            q = q.in_("product", list(products))
        q.execute()
        return load_bom_all()
    cur = load_bom_all()
    hit = cur["적용시작"] == eff
    if products:
        hit &= cur["표준명칭"].isin(list(products))
    out = cur[~hit]
    _write_bom(out)
    return out


def seed_bom_from_file(eff_from=None):
    """bom_master.xlsx의 현재 배합비를 기준버전으로 DB에 적재(최초 1회)."""
    base = _bom_from_file()
    eff = str(eff_from or C.BOM_BASE_YM)
    base = base.copy(); base["적용시작"] = eff
    return upsert_bom_version(eff, base, note="bom_master.xlsx 기준버전 시드")


# dim은 파일 유지

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
