# -*- coding: utf-8 -*-
"""④ 단가 감시 — DB 실적(설비 데이터) 단가·사용량 기준. 정확 금액(원) 표기."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers
from core import decompose as dc

st.title("🚨 단가 감시")
st.caption("**생산 자동화 설비에서 집계된 실제(DB) 단가·사용량 기준**입니다. "
           "BOM 이론이 아니라 ERP에 실제로 찍힌 값이라, 실구매 단가 변동과 그 금액 파장을 그대로 봅니다.")

def w(v):   # 정확 금액(원)
    return f"{v:,.0f}원"
def sw(v):
    return ("+" if v >= 0 else "−") + f"{abs(v):,.0f}원"

D = load_all()
m1, m2 = month_pickers(D["months"], key="watch")
pw = dc.price_watch(m1, m2, D["name_map"])

thr = st.slider("단가 변동 임계값 (±%)", 1, 30, 1)
flag = pw[pw["단가변동%"].abs() >= thr].copy()
up = flag[flag["단가변동%"] > 0]
dn = flag[flag["단가변동%"] < 0]

k = st.columns(4)
k[0].metric(f"±{thr}% 이상 변동", f"{len(flag)}종")
k[1].metric("상승 원료", f"{len(up)}종", f"영향 {sw(up['단가효과'].sum())}")
k[2].metric("하락 원료", f"{len(dn)}종", f"영향 {sw(dn['단가효과'].sum())}")
k[3].metric("단가효과 합계", sw(flag["단가효과"].sum()))
st.caption("‘단가효과’ = 그 원료의 (단가변동 × **당월(비교월) 실적사용량**). "
           "이번 달 실제로 쓴 양에 단가 변동을 곱한 값 = 실제 돈으로 본 파장. "
           "(월 비교·원료 상세 페이지와 동일한 당월 가중)")

if len(flag) == 0:
    st.info(f"±{thr}% 이상 변동한 원료가 없습니다.")
    st.stop()

st.subheader(f"단가 {thr}% 이상 변동 — 원료비 영향도순 (전체 {len(flag)}종)")
tv = flag.reindex(flag["단가효과"].abs().sort_values(ascending=False).index).copy()
tv["단가(원/kg)"] = tv.apply(lambda r: f"{r['단가_m1']:,.0f} → {r['단가_m2']:,.0f}", axis=1)
tv["단가변동"] = tv["단가변동%"].map(lambda v: "신규" if v == float("inf") else f"{v:+.1f}%")
tv["실적사용(kg)"] = tv.apply(lambda r: f"{r['실적사용kg_m1']:,.0f} → {r['실적사용kg_m2']:,.0f}", axis=1)
tv["단가효과(원)"] = tv["단가효과"].map(sw)
st.dataframe(tv[["원료코드", "원료명", "단가(원/kg)", "단가변동", "실적사용(kg)", "단가효과(원)"]],
             width='stretch', hide_index=True, height=440)

st.subheader("단가효과(원료비 영향) 큰 원료 TOP")
top = tv.head(15)
fig = go.Figure(go.Bar(
    x=top["단가효과"], y=top["원료명"], orientation="h",
    marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["단가효과"]],
    text=[sw(v) for v in top["단가효과"]], textposition="auto"))
fig.update_layout(height=460, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, width='stretch')
st.caption("빨강=단가 상승으로 원료비 증가, 파랑=단가 하락으로 절감. "
           "단가가 크게 올라도 안 쓰는 원료면 영향은 작고, 조금 올라도 많이 쓰면 큽니다.")
