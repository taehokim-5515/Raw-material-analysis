# -*- coding: utf-8 -*-
"""① 월 비교 — 실적(설비 DB) 원료비 리뷰. 제품 원인은 BOM×계획중량으로 뒷받침."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers, won, signed_won
from core import decompose as dc, dims

st.title("📊 원료비 원인분석 — 월 비교 (실적)")

D = load_all()
m1, m2 = month_pickers(D["months"], key="home")
cost, plan = D["cost"], D["plan"]
LIMITED = st.session_state.get("role") == "material"  # cham: 요약 3개 섹션만

det = dc.actual_material_detail(m1, m2, D["name_map"], D["bom_codes"])  # 실적·전사
tot1, tot2 = det["전월금액"].sum(), det["당월금액"].sum()
u1, u2 = det["전월사용kg"].sum(), det["당월사용kg"].sum()
price_imp = det["단가영향"].sum()
vol_imp = det["사용량영향"].sum()

if not LIMITED:
    # ---- KPI ----
    c = st.columns(4)
    c[0].metric(f"{m1} 실적 원료비", won(tot1) + "원")
    c[1].metric(f"{m2} 실적 원료비", won(tot2) + "원", f"{(tot2/tot1-1)*100:+.1f}%")
    c[2].metric("총 증감", signed_won(tot2 - tot1) + "원")
    c[3].metric("원료 사용량", f"{u2/1000:,.0f}톤", f"{(u2/u1-1)*100:+.1f}%")
    st.caption("설비에서 실제 소비된 사용량·금액(DB) 기준입니다. 총액이 ERP 실제 지출과 같습니다.")

    # ---- 워터폴 (실적 2분할) ----
    st.subheader("원료비 증감 분해 (워터폴)")
    steps = [("단가영향", price_imp), ("사용량영향", vol_imp)]
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=["absolute"] + ["relative"] * len(steps) + ["total"],
        x=[f"{m1}"] + [s[0] for s in steps] + [f"{m2}"],
        y=[tot1] + [s[1] for s in steps] + [tot2],
        text=[won(tot1)] + [signed_won(s[1]) for s in steps] + [won(tot2)],
        textposition="outside", connector={"line": {"color": "#B4B2A9"}},
        decreasing={"marker": {"color": "#378ADD"}}, increasing={"marker": {"color": "#D85A30"}},
        totals={"marker": {"color": "#888780"}}))
    fig.update_layout(height=420, margin=dict(t=30, b=10), showlegend=False, xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
    st.caption("단가영향 = Σ(단가변동 × 당월사용량) · 사용량영향 = Σ(사용량변동 × 전월단가). "
               "두 막대의 합 = 총 증감(실적, 교호 없는 2분할). 제품 구성까지 보려면 ‘사용단가 분석’ 페이지.")

    # ---- 드릴다운 ----
    st.markdown("##### 🔎 어느 항목이 궁금한가요? — 항목을 고르면 원료별 기여를 보여드립니다")
    pick = st.radio("분해 항목", ["단가영향", "사용량영향"], horizontal=True, label_visibility="collapsed")

    def _hbar(df, xcol, n=14):
        d = df.reindex(df[xcol].abs().sort_values(ascending=False).index).head(n)
        f = go.Figure(go.Bar(x=d[xcol], y=d["원료명"], orientation="h",
            marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in d[xcol]],
            text=[signed_won(v) + "원" for v in d[xcol]], textposition="auto"))
        f.update_layout(height=440, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
        st.plotly_chart(f, width='stretch')

    if pick == "단가영향":
        st.info(f"**단가영향 {signed_won(price_imp)}원** — 단가만 바뀌었을 때의 영향. "
                "각 원료의 (단가변동 × 당월 실적사용량) 합.")
        _hbar(det, "단가영향")
    else:
        st.info(f"**사용량영향 {signed_won(vol_imp)}원** — 사용량이 바뀌어서 생긴 영향. "
                "각 원료의 (사용량변동 × 전월단가) 합. 많이 만든 달일수록 큽니다.")
        _hbar(det, "사용량영향")

    st.divider()

# ---- 제품별(이론) / 원료별(실적) 원료비 증감 ----
left, right = st.columns(2)
with left:
    st.subheader("제품별 원료비 증감 TOP")
    st.caption("제품별 계획중량 × BOM × 단가 (이론). ‘어느 제품이’ 원료비를 움직였나.")
    pb = dc.product_bridge(cost, m1, m2)
    top = pd.concat([pb.head(8), pb.tail(4)])
    fig2 = go.Figure(go.Bar(x=top["금액증감"], y=top["표준제품"], orientation="h",
        marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["금액증감"]],
        text=[signed_won(v) for v in top["금액증감"]], textposition="auto"))
    fig2.update_layout(height=430, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig2, width='stretch')
with right:
    st.subheader("원료별 원료비 증감 TOP")
    st.caption("실적 사용량 × 단가 (설비 DB). ‘어느 원료에서’ 돈이 더 나갔나.")
    ms = det.sort_values("금액변동", ascending=False)
    topm = pd.concat([ms.head(8), ms.tail(4)])
    fig3 = go.Figure(go.Bar(x=topm["금액변동"], y=topm["원료명"], orientation="h",
        marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in topm["금액변동"]],
        text=[signed_won(v) for v in topm["금액변동"]], textposition="auto"))
    fig3.update_layout(height=430, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig3, width='stretch')

st.divider()

# ---- 제품별 계획지시 총량 + 그룹(더리얼/밥이보약 도그·캣 · OEM) ----
st.subheader("제품별 계획지시 총량(생산중량)")
pw = plan.copy(); pw["년월"] = pw["년월"].astype(str)
pw["그룹"] = pw["표준제품"].map(dims.plan_group)
order = ["더리얼 도그", "더리얼 캣", "밥이보약 도그", "밥이보약 캣", "OEM"]
gp = pw[pw["년월"].isin([m1, m2])].pivot_table(index="그룹", columns="년월",
     values="계획중량", aggfunc="sum", fill_value=0).reindex(order).fillna(0)
for mm in (m1, m2):
    if mm not in gp.columns: gp[mm] = 0
ga, gb = st.columns([3, 2])
with ga:
    st.markdown("**그룹별 톤수·비중**")
    t1, t2 = gp[m1].sum(), gp[m2].sum()
    tot_growth = (t2 / t1 - 1) * 100 if t1 else 0
    w1p = [gp.loc[g, m1] / t1 * 100 if t1 else 0 for g in order]
    w2p = [gp.loc[g, m2] / t2 * 100 if t2 else 0 for g in order]
    show = pd.DataFrame({"그룹": order})
    show[f"{m1}(톤)"] = [f"{gp.loc[g, m1]/1000:,.1f}" for g in order]
    show[f"{m2}(톤)"] = [f"{gp.loc[g, m2]/1000:,.1f}" for g in order]
    show["증감(톤)"] = [f"{(gp.loc[g, m2]-gp.loc[g, m1])/1000:+,.1f}" for g in order]
    show["증감률"] = ["신규" if gp.loc[g, m1] == 0 else
                   f"{(gp.loc[g, m2]/gp.loc[g, m1]-1)*100:+.1f}%" for g in order]
    show[f"{m1} 비중"] = [f"{v:.1f}%" for v in w1p]
    show[f"{m2} 비중"] = [f"{v:.1f}%" for v in w2p]
    show["비중차(pp)"] = [f"{b-a:+.1f}" for a, b in zip(w1p, w2p)]
    st.dataframe(show, width='stretch', hide_index=True)
    st.caption(f"총 생산: {m1} {t1/1000:,.1f}톤 → {m2} {t2/1000:,.1f}톤 (**{tot_growth:+.1f}%**). "
               f"실제 증감은 ‘증감(톤)·증감률’ 기준. **비중차(pp)는 감소가 아니라 "
               f"전체 성장률({tot_growth:+.1f}%)보다 느리면 −, 빠르면 +** — 생산 쏠림 지표입니다.")
with gb:
    fig4 = go.Figure()
    fig4.add_bar(name=m1, x=order, y=[gp.loc[g, m1]/1000 for g in order], marker_color="#B5D4F4")
    fig4.add_bar(name=m2, x=order, y=[gp.loc[g, m2]/1000 for g in order], marker_color="#378ADD")
    fig4.update_layout(barmode="group", height=340, margin=dict(t=10, b=10),
                       legend=dict(orientation="h", y=1.15), yaxis_title="톤")
    st.plotly_chart(fig4, width='stretch')

with st.expander("제품 단위 계획중량 TOP 보기"):
    w = pw[pw["년월"].isin([m1, m2])].pivot_table(index="표준제품", columns="년월",
        values="계획중량", aggfunc="sum", fill_value=0)
    for mm in (m1, m2):
        if mm not in w.columns: w[mm] = 0
    w["합"] = w[m1] + w[m2]
    w = w.sort_values("합", ascending=False).head(15)
    fig5 = go.Figure()
    fig5.add_bar(name=m1, x=w.index, y=w[m1], marker_color="#B5D4F4")
    fig5.add_bar(name=m2, x=w.index, y=w[m2], marker_color="#378ADD")
    fig5.update_layout(barmode="group", height=380, margin=dict(t=10, b=10),
                       legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig5, width='stretch')

if not LIMITED:
    st.divider()
    # ---- BOM 이론 vs 실적 대사 ----
    st.subheader("BOM 이론 vs 실적 대사 (수율·로스)")
    yg = dc.yield_gap(cost, m1, m2)
    show = yg.copy()
    for cc in ["이론사용kg", "실적사용kg"]:
        show[cc] = show[cc].map(lambda v: f"{v:,.0f}kg")
    for cc in ["이론금액", "실적금액"]:
        show[cc] = show[cc].map(lambda v: won(v) + "원")
    for cc in ["사용량gap%", "금액gap%"]:
        show[cc] = show[cc].map(lambda v: f"{v:+.2f}%")
    st.dataframe(show, width='stretch', hide_index=True)
    st.caption("이 페이지(실적) 총액엔 BOM 없는 라인(퀴진·트릿·밀·반제품)도 포함됩니다. 상세는 ‘원료상세 실적’ 페이지.")
