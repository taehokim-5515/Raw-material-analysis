# -*- coding: utf-8 -*-
"""⑦ 원료 상세 (실적·전사) — 기존 Material cost impact analysis 방식 그대로."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers, won, signed_won
from core import decompose as dc

st.title("📋 원료 상세 — 실적·전사")
st.caption("**설비 실적(DB) 전 원료** 기준. 기존 원가영향 분석과 동일하게 "
           "`금액변동 = 단가영향(단가변동×당월사용량) + 사용량영향(사용량변동×전월단가)`로 나눕니다. "
           "BOM·계획중량 기반 이론과 달리, 여기 총액이 ERP 실제 지출입니다.")

D = load_all()
m1, m2 = month_pickers(D["months"], key="act")
det = dc.actual_material_detail(m1, m2, D["name_map"], D["bom_codes"])
rec = dc.actual_vs_theo_recon(D["cost"], m1, m2, D["bom_codes"])

# ---- KPI ----
tot_chg = det["금액변동"].sum()
k = st.columns(4)
k[0].metric(f"{m1} 실적 원료비", won(rec["실적_m1"]) + "원")
k[1].metric(f"{m2} 실적 원료비", won(rec["실적_m2"]) + "원",
            f"{(rec['실적_m2']/rec['실적_m1']-1)*100:+.1f}%")
k[2].metric("단가영향 합", signed_won(det["단가영향"].sum()) + "원")
k[3].metric("사용량영향 합", signed_won(det["사용량영향"].sum()) + "원")
st.caption("단가영향 합 + 사용량영향 합 = 총 금액변동. 물량(사용량)이 대부분이면 생산량 주도, 단가영향이 크면 시세 주도.")

# ---- 범위 갭: 실적(전사) vs 이론(BOM 60제품) ----
with st.expander("🔍 왜 ‘월 비교(이론)’ 총액과 다른가 — 범위 대사", expanded=True):
    g = pd.DataFrame({
        "구분": ["실적·전사 (이 페이지)", "이론·BOM 60제품 (월 비교)", "차이 = 범위밖+수율"],
        m1: [won(rec["실적_m1"])+"원", won(rec["이론_m1"])+"원", signed_won(rec["실적_m1"]-rec["이론_m1"])+"원"],
        m2: [won(rec["실적_m2"])+"원", won(rec["이론_m2"])+"원", signed_won(rec["실적_m2"]-rec["이론_m2"])+"원"],
    })
    st.dataframe(g, width='stretch', hide_index=True)
    st.markdown(f"이 중 **BOM 없는 실적 소비 {rec['범위밖_종수']}종** "
                f"(퀴진·트릿·밀·반제품 등)이 {m1} {won(rec['범위밖_m1'])}원 · {m2} {won(rec['범위밖_m2'])}원. "
                "이 라인들은 제품 BOM이 없어 ‘월 비교(이론)’엔 안 잡히고, 여기 실적엔 잡힙니다.")
    oos = det[det["BOM포함"] == "아니오"].sort_values("당월금액", ascending=False).head(10)
    show = oos[["원료코드", "원료명", "원료군", "당월금액"]].copy()
    show["당월금액"] = show["당월금액"].map(lambda v: won(v) + "원")
    st.dataframe(show, width='stretch', hide_index=True)

# ---- 금액변동 TOP ----
st.subheader("금액변동 TOP (증가·감소)")
top = pd.concat([det.head(12), det.tail(8)])
fig = go.Figure(go.Bar(
    x=top["금액변동"], y=top["원료명"], orientation="h",
    marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["금액변동"]],
    text=[signed_won(v) for v in top["금액변동"]], textposition="auto"))
fig.update_layout(height=560, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, width='stretch')

# ---- 전체 상세 표 ----
st.subheader(f"전체 품목 상세 ({len(det)}종)")
only_active = st.checkbox("사용량 있는 품목만", value=True)
f = det[(det["전월사용kg"] > 0) | (det["당월사용kg"] > 0)] if only_active else det
t = f.copy()
t["단가(원/kg)"] = t.apply(lambda r: f"{r['전월단가']:,.0f}→{r['당월단가']:,.0f}", axis=1)
t["단가변동%"] = t["단가변동률%"].map(lambda v: f"{v:+.1f}%")
t["사용량(kg)"] = t.apply(lambda r: f"{r['전월사용kg']:,.0f}→{r['당월사용kg']:,.0f}", axis=1)
t["금액변동"] = t["금액변동"].map(lambda v: signed_won(v) + "원")
t["단가영향"] = t["단가영향"].map(lambda v: signed_won(v) + "원")
t["사용량영향"] = t["사용량영향"].map(lambda v: signed_won(v) + "원")
st.dataframe(
    t[["원료코드", "원료명", "원료군", "BOM포함", "단가(원/kg)", "단가변동%",
       "사용량(kg)", "금액변동", "단가영향", "사용량영향"]],
    width='stretch', hide_index=True, height=460)
st.download_button("📥 상세표 CSV 다운로드",
                   f.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"원료상세_실적_{m1}_{m2}.csv", mime="text/csv")
