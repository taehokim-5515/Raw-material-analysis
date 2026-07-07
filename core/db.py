# -*- coding: utf-8 -*-
"""누적 메인 DB(Excel) 및 dim 로더/라이터."""
import re
from collections import defaultdict
import pandas as pd
from . import config as C

# ---------- 로더 ----------
def load_price():
    """원료단가사용: 년월·원료코드·원료명·단가·실적사용kg·실적금액"""
    df = pd.read_excel(C.MAIN_DB, sheet_name="원료단가사용", dtype={"원료코드": str})
    return df

def load_plan():
    """생산계획: 년월·표준제품·계획중량"""
    return pd.read_excel(C.MAIN_DB, sheet_name="생산계획")

def load_bom():
    """BOM: 표준명칭·배합비레벨·ERP코드·원료한글명·배합률"""
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
    """해당 월 원료코드→원료명(표시용)."""
    p = load_price()
    sub = p[p["년월"].astype(str) == ym]
    return dict(zip(sub["원료코드"], sub["원료명"]))

# ---------- 라이터(월 마감 append) ----------
def _write_sheet(sheet, df):
    from openpyxl import load_workbook
    with pd.ExcelWriter(C.MAIN_DB, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as w:
        df.to_excel(w, sheet_name=sheet, index=False)

def upsert_plan(ym, plan_rows):
    """plan_rows: DataFrame[표준제품,계획중량]. 같은 년월 덮어쓰기."""
    cur = load_plan()
    cur = cur[cur["년월"].astype(str) != ym]
    add = plan_rows.copy()
    add.insert(0, "년월", ym)
    out = pd.concat([cur, add], ignore_index=True)
    _write_sheet("생산계획", out)
    return out

def upsert_plan_multi(months_dict):
    """여러 달 생산계획을 한 번에 반영. months_dict{ym: DataFrame[표준제품,계획중량]}."""
    cur = load_plan()
    cur = cur[~cur["년월"].astype(str).isin(list(months_dict.keys()))]
    adds = []
    for ym, df in months_dict.items():
        a = df.copy(); a.insert(0, "년월", ym); adds.append(a)
    out = pd.concat([cur] + adds, ignore_index=True) if adds else cur
    _write_sheet("생산계획", out)
    return out


def upsert_price(ym, price_rows):
    """price_rows: DataFrame[원료코드,원료명,단가,실적사용kg,실적금액]. 같은 년월 덮어쓰기."""
    cur = load_price()
    cur = cur[cur["년월"].astype(str) != ym]
    add = price_rows.copy()
    add.insert(0, "년월", ym)
    out = pd.concat([cur, add], ignore_index=True)
    _write_sheet("원료단가사용", out)
    return out


def upsert_price_multi(months_dict):
    """여러 달 단가·사용량을 한 번에 반영. months_dict{ym: DataFrame[원료코드,...]}."""
    cur = load_price()
    cur = cur[~cur["년월"].astype(str).isin(list(months_dict.keys()))]
    adds = []
    for ym, df in months_dict.items():
        a = df.copy(); a.insert(0, "년월", ym); adds.append(a)
    out = pd.concat([cur] + adds, ignore_index=True) if adds else cur
    _write_sheet("원료단가사용", out)
    return out
