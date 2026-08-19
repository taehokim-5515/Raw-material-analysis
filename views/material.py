# -*- coding: utf-8 -*-
"""③ 원료 드릴다운 — 실적 단가·사용량 추이(메인) + ⭐사용량 변화의 제품 귀속(이론)."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers, won, kg, signed_won
from core import decompose as dc

st.title("🧪 원료 드릴다운 — 사용단가·사용량 원인추적")
st.caption("**설비 실적(DB)** 단가·사용량이 기준입니다. 아래 ‘제품 귀속’만 BOM×계획중량 기반 "
           "이론값으로 계산됩니다(실적 DB에는 제품 구분이 없기 때문).")

D = load_all()
usage, price, name_map, bom_codes = D["usage"], D["price"], D["name_map"], D["bom_codes"]

price = price.copy()
price["년월"] = price["년월"].astype(str)
price["원료코드"] = price["원료코드"].astype(str)
usage = usage.copy()
usage["년월"] = usage["년월"].astype(str)
usage["ERP코드"] = usage["ERP코드"].astype(str)

# ---- 원료 목록: 실적 DB 전체(미사용 포함), 실적금액 순 ----
agg = price.groupby("원료코드").agg(금액=("실적금액", "sum"), 사용kg=("실적사용kg", "sum"))
codes = list(agg.sort_values("금액", ascending=False).index)
nm_db = dict(zip(price["원료코드"], price["원료명"]))

def _label(c):
    n = nm_db.get(c) or name_map.get(c, c)
    tail = ""
    if c not in bom_codes:
        tail += " · BOM없음"
    if float(agg.loc[c, "사용kg"]) == 0:
        tail += " · 미사용"
    return f"{n} ({c}){tail}"

code = st.selectbox("원료 선택", codes, format_func=_label,
                    help="실적 DB 전 원료(실적금액 순). ‘BOM없음’은 배합 정보가 없어 제품별 추적이 불가한 원료, "
                         "‘미사용’은 기간 내 사용 실적이 없는 원료입니다.")
has_bom = code in bom_codes
mat_name = nm_db.get(code) or name_map.get(code, code)

pr = price[price["원료코드"] == code].sort_values("년월")
uu = usage[usage["ERP코드"] == code]
um = uu.groupby("년월")["이론사용kg"].sum().reset_index()
theo_map = dict(zip(um["년월"], um["이론사용kg"]))

# ---- KPI (최근월) ----
if len(pr):
    last = pr.iloc[-1]
    prev = pr.iloc[-2] if len(pr) >= 2 else None
    k = st.columns(4)
    k[0].metric(f"{last['년월']} 단가", f"{last['단가']:,.0f}원/kg",
                f"{(last['단가']/prev['단가']-1)*100:+.1f}%" if prev is not None and prev["단가"] else None,
                delta_color="inverse")
    k[1].metric("실적 사용량", f"{last['실적사용kg']:,.0f}kg",
                f"{(last['실적사용kg']/prev['실적사용kg']-1)*100:+.1f}%"
                if prev is not None and prev["실적사용kg"] else None)
    k[2].metric("실적 금액", won(last["실적금액"]) + "원")
    k[3].metric("배합 사용 제품", f"{uu['표준제품'].nunique()}종" if has_bom else "BOM없음",
                help="이 원료가 배합에 들어가는 제품 수(BOM 기준)")

c1, c2 = st.columns(2)
with c1:
    st.subheader("단가 추이 (원/kg)")
    fig = go.Figure(go.Scatter(x=pr["년월"], y=pr["단가"], mode="lines+markers",
                               line=dict(color="#D85A30", width=3), name="실적 단가"))
    fig.update_layout(height=340, margin=dict(t=10, b=10), xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
with c2:
    st.subheader("사용량 추이 (kg)")
    fig = go.Figure()
    fig.add_bar(x=pr["년월"], y=pr["실적사용kg"], name="실적 사용량", marker_color="#0F6E56")
    if has_bom:
        ty = [theo_map.get(m, 0) for m in pr["년월"]]
        if any(v > 0 for v in ty):
            fig.add_scatter(x=pr["년월"], y=ty, name="이론(BOM×계획)", mode="lines+markers",
                            line=dict(color="#BA7517", width=2, dash="dot"))
    fig.update_layout(height=340, margin=dict(t=10, b=10), xaxis=dict(type="category"),
                      legend=dict(orientation="h", y=1.15))
    st.plotly_chart(fig, width='stretch')
    st.caption("막대 = 설비에서 실제 소비된 양. 점선 = 계획중량×BOM 이론값. "
               "둘의 간격이 수율·로스·재고 변동입니다." if has_bom
               else "이 원료는 BOM 정보가 없어 실적만 표시됩니다.")

st.divider()
st.subheader("⭐ 사용량 변화, 어느 제품 생산 때문인가")

if not has_bom:
    st.info(f"**{mat_name}** 은(는) BOM(배합 정보)이 없어 제품별 추적이 불가합니다. "
            "퀴진·트릿·밀·반제품 라인 등 배합비를 등록하지 않은 제품에 쓰이는 원료입니다. "
            "해당 제품의 BOM을 등록하면 이 섹션이 자동으로 열립니다. "
            "(위의 단가·사용량 추이는 실적 기준으로 정상 표시됩니다.)")
else:
    st.caption("이 섹션만 이론 기준입니다 — Δ사용량 = Σ제품(Δ생산중량 × 배합률). "
               "실적 DB에는 제품 구분이 없어 BOM으로 역산합니다.")
    m1, m2 = month_pickers(D["months"], key="mat")
    attr = dc.material_product_attribution(usage, code, m1, m2)
    attr = attr[attr["사용kg증감"].abs() > 1e-6]
    d1 = uu[uu["년월"] == m1]["이론사용kg"].sum(); d2 = uu[uu["년월"] == m2]["이론사용kg"].sum()
    a1 = pr[pr["년월"] == m1]["실적사용kg"].sum(); a2 = pr[pr["년월"] == m2]["실적사용kg"].sum()
    st.markdown(f"**{mat_name}** 이론 사용량 {kg(d1)} → {kg(d2)} "
                f"(Δ {'+' if d2>=d1 else '−'}{abs(d2-d1):,.0f}kg) · "
                f"참고: 실적 {kg(a1)} → {kg(a2)}")
    if len(attr) == 0:
        st.info("두 달 사이 이 원료를 쓰는 제품의 생산 변동이 없습니다.")
    else:
        top = attr.head(12)
        fig = go.Figure(go.Bar(
            x=top["사용kg증감"], y=top["표준제품"], orientation="h",
            marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["사용kg증감"]],
            text=[f"{v:+,.0f}kg" for v in top["사용kg증감"]], textposition="auto"))
        fig.update_layout(height=max(240, 34 * len(top) + 60), margin=dict(t=10, b=10),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width='stretch')
        st.caption("단가가 그대로여도 이 제품들의 생산 증감이 원료 사용량을 움직입니다.")
        show = attr.copy()
        show[f"{m1}(기준)"] = show["사용kg_m1"].map(lambda v: f"{v:,.0f}")
        show[f"{m2}(비교)"] = show["사용kg_m2"].map(lambda v: f"{v:,.0f}")
        show["증감kg"] = show["사용kg증감"].map(lambda v: f"{v:+,.0f}")
        st.dataframe(show[["표준제품", f"{m1}(기준)", f"{m2}(비교)", "증감kg"]],
                     width='stretch', hide_index=True)
