# -*- coding: utf-8 -*-
"""② 제품 드릴다운 — 생산량·원료비·단위원가(원/kg) 추이 + 원료 구성."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, won
from core import model

st.title("📦 제품 드릴다운")

D = load_all()
cost, plan, usage = D["cost"], D["plan"], D["usage"]
prods = sorted(plan["표준제품"].unique())
prod = st.selectbox("제품 선택", prods)

pc = model.by_product(cost)
pc = pc[pc["표준제품"] == prod].copy(); pc["년월"] = pc["년월"].astype(str)
pw = plan[plan["표준제품"] == prod].copy(); pw["년월"] = pw["년월"].astype(str)
# 단위원가(원/kg) = 원료비 / 생산중량
uc = pc.merge(pw[["년월", "계획중량"]], on="년월", how="left").sort_values("년월")
uc["원가원단위"] = (uc["원료비"] / uc["계획중량"]).replace([float("inf")], 0).fillna(0)

st.caption("‘원료비 추이’는 생산량이 많은 달일수록 커집니다(물량 영향). "
           "‘단위원가(원/kg)’는 1kg당 원료비라 **물량을 걷어낸 순수 단가·레시피 흐름**을 보여줍니다.")

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("생산량 (계획중량)")
    fig = go.Figure(go.Bar(x=pw.sort_values("년월")["년월"], y=pw.sort_values("년월")["계획중량"],
                           marker_color="#1D9E75",
                           text=[f"{v/1000:,.1f}t" for v in pw.sort_values("년월")["계획중량"]],
                           textposition="auto"))
    fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
with c2:
    st.subheader("원료비 (총액)")
    fig = go.Figure(go.Scatter(x=pc.sort_values("년월")["년월"], y=pc.sort_values("년월")["원료비"],
                               mode="lines+markers", line=dict(color="#534AB7", width=3)))
    fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
with c3:
    st.subheader("단위원가 (원/kg)")
    fig = go.Figure(go.Scatter(x=uc["년월"], y=uc["원가원단위"], mode="lines+markers",
                               line=dict(color="#D85A30", width=3),
                               text=[f"{v:,.0f}" for v in uc["원가원단위"]]))
    fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
    st.caption("1kg 만드는 데 드는 원료비. 오르면 단가↑ 또는 레시피 변경 신호.")

st.subheader("원료 구성 (선택 월)")
months = sorted(usage["년월"].astype(str).unique())
ym = st.select_slider("월", months, value=months[-1])
sub = cost[(cost["표준제품"] == prod) & (cost["년월"].astype(str) == ym)].copy()
sub = sub.merge(pd.DataFrame({"ERP코드": list(D["name_map"].keys()),
                              "원료명": list(D["name_map"].values())}), on="ERP코드", how="left")
sub = sub.sort_values("이론금액", ascending=False)
sub["원료비"] = sub["이론금액"].map(lambda v: won(v) + "원")
sub["사용량"] = sub["이론사용kg"].map(lambda v: f"{v:,.1f}kg")
sub["단가"] = sub["단가"].map(lambda v: f"{v:,.0f}원/kg")
tot = sub["이론금액"].sum()
sub["원가비중"] = (sub["이론금액"] / tot * 100).map(lambda v: f"{v:.1f}%")
st.dataframe(sub[["ERP코드", "원료명", "사용량", "단가", "원료비", "원가비중"]],
             width='stretch', hide_index=True)
w_ym = pw[pw['년월'] == ym]['계획중량'].sum()
st.caption(f"{ym} · {prod} — 총 원료비 {won(tot)}원 · 생산 {w_ym:,.0f}kg · "
           f"단위원가 {tot/w_ym:,.0f}원/kg" if w_ym else f"{ym} · {prod} — 생산 없음")
