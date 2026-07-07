# -*- coding: utf-8 -*-
"""이론 사용량·원료비 모델. (BOM 키블 전개 → 사용량 → ×단가)"""
from collections import defaultdict
import pandas as pd
from . import config as C
from . import db


def explode_bom(bom=None):
    """반제품 키블(6000001/6000002)을 하위 원료로 전개한 제품×원료 배합률.
    반환: DataFrame[표준명칭, ERP코드, 배합률]  (원료코드 기준 합산)"""
    if bom is None:
        bom = db.load_bom()
    kib = {k: bom[bom["표준명칭"] == v][["ERP코드", "배합률"]].values.tolist()
           for k, v in C.KIBBLE_CODES.items()}
    out = defaultdict(lambda: defaultdict(float))  # 제품 -> 코드 -> 배합률
    for _, r in bom.iterrows():
        p, code, ratio = r["표준명칭"], r["ERP코드"], r["배합률"]
        if code in kib:
            for sc, sr in kib[code]:
                out[p][sc] += ratio * sr / 100.0
        else:
            out[p][code] += ratio
    rows = [(p, c, v) for p, d in out.items() for c, v in d.items()]
    return pd.DataFrame(rows, columns=["표준명칭", "ERP코드", "배합률"])


def bom_material_codes(bom=None):
    """BOM(60제품, 키블 전개 후)이 사용하는 원료코드 집합."""
    return set(explode_bom(bom)["ERP코드"].astype(str))


def theoretical_usage(plan=None, bom_x=None):
    """이론 사용량(kg) = 계획중량 × 배합률/100.
    반환: DataFrame[년월, 표준제품, ERP코드, 이론사용kg]"""
    if plan is None:
        plan = db.load_plan()
    if bom_x is None:
        bom_x = explode_bom()
    m = plan.merge(bom_x, left_on="표준제품", right_on="표준명칭", how="left")
    m["이론사용kg"] = m["계획중량"] * m["배합률"] / 100.0
    return m[["년월", "표준제품", "ERP코드", "이론사용kg"]]


def cost_table(usage=None, price=None):
    """이론 원료비 = 이론사용kg × 단가(해당 월).
    반환: DataFrame[년월, 표준제품, ERP코드, 이론사용kg, 단가, 이론금액]"""
    if usage is None:
        usage = theoretical_usage()
    if price is None:
        price = db.load_price()
    price = price.copy()
    price["년월"] = price["년월"].astype(str)
    usage = usage.copy()
    usage["년월"] = usage["년월"].astype(str)
    m = usage.merge(price[["년월", "원료코드", "단가"]],
                    left_on=["년월", "ERP코드"], right_on=["년월", "원료코드"], how="left")
    m["단가"] = m["단가"].fillna(0)
    m["이론금액"] = m["이론사용kg"] * m["단가"]
    return m[["년월", "표준제품", "ERP코드", "이론사용kg", "단가", "이론금액"]]


# ---------- 집계 헬퍼 ----------
def by_product(cost):
    return (cost.groupby(["년월", "표준제품"])["이론금액"].sum()
            .reset_index().rename(columns={"이론금액": "원료비"}))

def by_material(cost, name_map=None):
    g = (cost.groupby(["년월", "ERP코드"])
         .agg(이론사용kg=("이론사용kg", "sum"), 이론금액=("이론금액", "sum")).reset_index())
    if name_map:
        g["원료명"] = g["ERP코드"].map(name_map)
    return g

def product_month_weight(plan=None):
    if plan is None:
        plan = db.load_plan()
    return plan.rename(columns={"계획중량": "생산kg"})
