# -*- coding: utf-8 -*-
"""③ 원료 드릴다운 — 단가·사용량 추이 + ⭐사용량 변화의 제품 귀속."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers, won, kg, signed_won
from core import decompose as dc

st.title("🧪 원료 드릴다운 — 사용단가·사용량 원인추적")

D = load_all()
cost, usage, price, name_map = D["cost"], D["usage"], D["price"], D["name_map"]

# 원료 선택(사용량 있는 코드)
codes = sorted(usage["ERP코드"].unique(), key=lambda c: -usage[usage["ERP코드"] == c]["이론사용kg"].sum())
label = {c: f"{name_map.get(c, c)} ({c})" for c in codes}
code = st.selectbox("원료 선택", codes, format_func=lambda c: label[c])

pr = price.copy(); pr["년월"] = pr["년월"].astype(str)
pr = pr[pr["원료코드"] == code].sort_values("년월")
uu = usage[usage["ERP코드"] == code].copy(); uu["년월"] = uu["년월"].astype(str)
um = uu.groupby("년월")["이론사용kg"].sum().reset_index()

c1, c2 = st.columns(2)
with c1:
    st.subheader("단가 추이 (원/kg)")
    fig = go.Figure(go.Scatter(x=pr["년월"], y=pr["단가"], mode="lines+markers",
                               line=dict(color="#D85A30", width=3)))
    fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
with c2:
    st.subheader("이론 사용량 추이 (kg)")
    fig = go.Figure(go.Bar(x=um["년월"], y=um["이론사용kg"], marker_color="#0F6E56"))
    fig.update_layout(height=320, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')

st.divider()
st.subheader("⭐ 사용량 변화, 어느 제품 생산 때문인가")
m1, m2 = month_pickers(D["months"], key="mat")
attr = dc.material_product_attribution(usage, code, m1, m2)
attr = attr[attr["사용kg증감"].abs() > 1e-6]
d1 = uu[uu["년월"] == m1]["이론사용kg"].sum(); d2 = uu[uu["년월"] == m2]["이론사용kg"].sum()
st.markdown(f"**{name_map.get(code, code)}** 사용량 {kg(d1)} → {kg(d2)}  "
            f"(Δ {'+' if d2>=d1 else '−'}{abs(d2-d1):,.0f}kg)")
top = attr.head(12)
fig = go.Figure(go.Bar(
    x=top["사용kg증감"], y=top["표준제품"], orientation="h",
    marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["사용kg증감"]],
    text=[f"{v:+,.0f}kg" for v in top["사용kg증감"]], textposition="auto"))
fig.update_layout(height=420, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, width='stretch')
st.caption("Δ사용량 = Σ제품( Δ생산중량 × 배합률 ). 단가 변화가 없어도 이 제품들의 생산 증감이 사용량을 움직입니다.")

show = attr.copy()
show["5월(기준)"] = show["사용kg_m1"].map(lambda v: f"{v:,.0f}")
show["6월(비교)"] = show["사용kg_m2"].map(lambda v: f"{v:,.0f}")
show["증감kg"] = show["사용kg증감"].map(lambda v: f"{v:+,.0f}")
st.dataframe(show[["표준제품", "5월(기준)", "6월(비교)", "증감kg"]],
             width='stretch', hide_index=True)
