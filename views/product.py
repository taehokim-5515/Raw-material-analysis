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

st.divider()
# ---- 단위원가 월별 전망 (BOM × 예상단가) + 원인 분해 ----
st.subheader("📈 단위원가 월별 전망 (BOM × 예상단가)")
from core import db as _db, unitprice as up
fp = _db.load_forecast()
if fp.empty:
    st.info("예상단가 DB가 비어 있습니다. ‘데이터 관리 → 예상단가’ 탭에서 업로드하면 "
            "미래 월까지 단위원가 전망과 원인 분해가 여기 표시됩니다.")
else:
    ucf, _bomsub = up.forecast_uc_series(prod, D["bom_x"], fp)
    ucf = ucf[ucf["단위원가"] > 0]
    if len(ucf) == 0:
        st.warning("이 제품의 BOM 원료에 대한 예상단가가 없습니다.")
    else:
        st.caption("BOM(배합)은 고정하고 **원료 단가 변화만** 반영한 1kg당 원가입니다. "
                   "생산이 없는 미래 월도 계산되므로, 단가 전망이 원가에 미칠 영향을 미리 볼 수 있습니다.")
        figf = go.Figure(go.Scatter(x=ucf["년월"], y=ucf["단위원가"], mode="lines+markers+text",
                                    line=dict(color="#0F6E56", width=3),
                                    text=[f"{v:,.0f}" for v in ucf["단위원가"]],
                                    textposition="top center", textfont=dict(size=10)))
        figf.update_layout(height=340, margin=dict(t=30, b=10), xaxis=dict(type="category"))
        st.plotly_chart(figf, width='stretch')
        low_cov = ucf[ucf["단가커버율%"] < 99.5]
        if len(low_cov):
            st.warning("일부 월은 단가 없는 원료가 있어 과소계산됨: " +
                       ", ".join(f"{r['년월']}({r['단가커버율%']:.0f}%)" for _, r in low_cov.iterrows()))

        st.markdown("##### 🔎 단위원가 변화 원인 — 어떤 원료 단가 때문인가")
        fmonths = list(ucf["년월"])
        cc1, cc2 = st.columns(2)
        i2 = len(fmonths) - 1
        fm2 = cc2.selectbox("비교월", fmonths, index=i2, key="fuc_m2")
        prev = [m for m in fmonths if m < fm2] or fmonths[:1]
        fm1 = cc1.selectbox("기준월", fmonths, index=fmonths.index(prev[-1]), key="fuc_m1")
        br = up.forecast_uc_bridge(prod, fm1, fm2, D["bom_x"], fp, D["name_map"])
        u1v = float(ucf[ucf["년월"] == fm1]["단위원가"].iloc[0])
        u2v = float(ucf[ucf["년월"] == fm2]["단위원가"].iloc[0])
        st.markdown(f"단위원가 **{u1v:,.0f} → {u2v:,.0f}원/kg** "
                    f"(**{u2v-u1v:+,.1f}원/kg**, {(u2v/u1v-1)*100:+.1f}%)" if u1v else "")
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

st.divider()
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
