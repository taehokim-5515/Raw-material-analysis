# -*- coding: utf-8 -*-
"""페이지 공통: 캐시 로더, 월 선택, 포맷."""
import streamlit as st
import pandas as pd
from core import db, model, decompose as dc


@st.cache_data(show_spinner=False)
def load_all():
    bom_x = model.explode_bom()
    plan = db.load_plan()
    usage = model.theoretical_usage(plan, bom_x)
    cost = model.cost_table(usage)
    price = db.load_price()
    mm = db.load_material_master()
    name_map = dict(zip(mm["ERP코드"], mm["대표원료명"]))
    # DB 원료명 우선(있으면)
    for m in reversed(sorted(price["년월"].astype(str).unique())):
        sub = price[price["년월"].astype(str) == m]
        for c, n in zip(sub["원료코드"], sub["원료명"]):
            name_map.setdefault(c, n)
    months = sorted(set(plan["년월"].astype(str)) & set(price["년월"].astype(str)))
    bom_codes = set(bom_x["ERP코드"].astype(str))
    return dict(bom_x=bom_x, plan=plan, usage=usage, cost=cost,
                price=price, name_map=name_map, months=months, bom_codes=bom_codes)


def month_pickers(months, key="mp"):
    if len(months) < 2:
        st.warning("비교하려면 생산계획·단가가 모두 있는 월이 2개 이상 필요합니다.")
        st.stop()
    c1, c2 = st.columns(2)
    m2 = c2.selectbox("비교월", months, index=len(months) - 1, key=key + "_m2")
    prev = [m for m in months if m < m2] or months[:1]
    m1 = c1.selectbox("기준월", months, index=months.index(prev[-1]), key=key + "_m1")
    return m1, m2


def won(x):
    x = float(x)
    if abs(x) >= 1e8:
        return f"{x/1e8:,.2f}억"
    if abs(x) >= 1e4:
        return f"{x/1e4:,.0f}만"
    return f"{x:,.0f}"


def kg(x):
    return f"{float(x):,.0f}kg"


def signed_won(x):
    s = "+" if x >= 0 else "−"
    return s + won(abs(x))
