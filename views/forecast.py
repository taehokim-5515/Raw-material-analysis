# -*- coding: utf-8 -*-
"""단위원가 전망 — BOM(고정) × 예상단가 → 월별 단위원가 + 원료 단가 기여 분해."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all
from core import db, unitprice as up

st.title("📈 단위원가 전망 (BOM × 예상단가)")
st.caption("배합(BOM)은 고정하고 **원료 단가 변화만** 반영한 제품 1kg당 원가입니다. "
           "예상단가를 넣어두면 생산이 없는 **미래 월까지** 원가 흐름을 미리 볼 수 있고, "
           "변화가 **어떤 원료 단가 때문인지** 정확히 분해됩니다. "
           "데이터는 ‘데이터 관리 → ③ 예상단가’에서 업로드합니다.")

D = load_all()
fp = db.load_forecast()
if fp.empty:
    st.info("예상단가 DB가 비어 있습니다. ‘데이터 관리 → ③ 예상단가’ 탭에서 업로드하세요.")
    st.stop()

prods = sorted(set(D["bom_x"]["표준명칭"].unique()))
prod = st.selectbox("제품 선택", prods,
                    index=prods.index("더리얼 GF 닭고기 어덜트") if "더리얼 GF 닭고기 어덜트" in prods else 0)

ucf, _sub = up.forecast_uc_series(prod, D["bom_x"], fp)
ucf = ucf[ucf["단위원가"] > 0]
if len(ucf) == 0:
    st.warning("이 제품의 BOM 원료에 대한 예상단가가 없습니다.")
    st.stop()

# ---- 월별 전망 곡선 ----
st.subheader("단위원가 월별 추이·전망 (원/kg)")
fig = go.Figure(go.Scatter(x=ucf["년월"], y=ucf["단위원가"], mode="lines+markers+text",
                           line=dict(color="#0F6E56", width=3),
                           text=[f"{v:,.0f}" for v in ucf["단위원가"]],
                           textposition="top center", textfont=dict(size=10)))
fig.update_layout(height=380, margin=dict(t=30, b=10), xaxis=dict(type="category"))
st.plotly_chart(fig, width='stretch')
low_cov = ucf[ucf["단가커버율%"] < 99.5]
if len(low_cov):
    st.warning("일부 월은 단가 없는 원료가 있어 과소계산됨: " +
               ", ".join(f"{r['년월']}({r['단가커버율%']:.0f}%)" for _, r in low_cov.iterrows()))

st.divider()

# ---- 원인 분해 ----
st.subheader("🔎 단위원가 변화 원인 — 어떤 원료 단가 때문인가")
fmonths = list(ucf["년월"])
c1, c2 = st.columns(2)
fm2 = c2.selectbox("비교월", fmonths, index=len(fmonths) - 1, key="fc_m2")
prev = [m for m in fmonths if m < fm2] or fmonths[:1]
fm1 = c1.selectbox("기준월", fmonths, index=fmonths.index(prev[-1]), key="fc_m1")

br = up.forecast_uc_bridge(prod, fm1, fm2, D["bom_x"], fp, D["name_map"])
u1v = float(ucf[ucf["년월"] == fm1]["단위원가"].iloc[0])
u2v = float(ucf[ucf["년월"] == fm2]["단위원가"].iloc[0])
k = st.columns(3)
k[0].metric(f"{fm1} 단위원가", f"{u1v:,.0f}원/kg")
k[1].metric(f"{fm2} 단위원가", f"{u2v:,.0f}원/kg",
            f"{(u2v/u1v-1)*100:+.1f}%" if u1v else None)
k[2].metric("변화", f"{u2v-u1v:+,.1f}원/kg")

moved = br[br["기여(원/kg)"].abs() > 0.005]
if len(moved) == 0:
    st.info("두 달 사이 단가가 변한 원료가 없습니다.")
else:
    top = moved.head(12)
    figb = go.Figure(go.Bar(
        x=top["기여(원/kg)"], y=top["원료명"], orientation="h",
        marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["기여(원/kg)"]],
        text=[f"{v:+,.1f}" for v in top["기여(원/kg)"]], textposition="auto"))
    figb.update_layout(height=max(240, 34 * len(top) + 60), margin=dict(t=10, b=10),
                       yaxis=dict(autorange="reversed"))
    st.plotly_chart(figb, width='stretch')
    st.caption("기여(원/kg) = 배합률 × 단가변동. 배합이 고정이라 **기여의 합 = 단위원가 변화**로 정확히 떨어집니다.")
    tt = moved.copy()
    tt["배합률"] = tt["배합률%"].map(lambda v: f"{v:.2f}%")
    tt["단가(원/kg)"] = tt.apply(lambda r: f"{r['단가_m1']:,.0f} → {r['단가_m2']:,.0f}", axis=1)
    tt["기여"] = tt["기여(원/kg)"].map(lambda v: f"{v:+,.2f}원/kg")
    st.dataframe(tt[["원료코드", "원료명", "배합률", "단가(원/kg)", "기여"]],
                 width='stretch', hide_index=True)

with st.expander("전체 배합 원료 보기 (단가 변화 없는 원료 포함)"):
    aa = br.copy()
    aa["배합률"] = aa["배합률%"].map(lambda v: f"{v:.2f}%")
    aa["단가(원/kg)"] = aa.apply(lambda r: f"{r['단가_m1']:,.0f} → {r['단가_m2']:,.0f}", axis=1)
    aa["기여"] = aa["기여(원/kg)"].map(lambda v: f"{v:+,.2f}원/kg")
    st.dataframe(aa[["원료코드", "원료명", "배합률", "단가(원/kg)", "기여"]],
                 width='stretch', hide_index=True, height=380)
