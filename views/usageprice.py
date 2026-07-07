# -*- coding: utf-8 -*-
"""⑥ 사용단가(원/kg) 분석 — 실적으로 본 결과, BOM×계획중량으로 원인 뒷받침."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, month_pickers
from core import unitprice as up

st.title("⚖️ 사용단가 분석 (원/kg)")
st.caption("**사용단가 = 원료금액 ÷ 원료사용량**, 즉 ‘원료를 kg당 평균 얼마에 쓰고 있나’입니다. "
           "전체·원료군은 **실적(설비 DB)**, 제품·브랜드는 **BOM×계획중량 이론**으로 계산합니다. "
           "실적이 결과라면, BOM·계획중량은 ‘왜 그렇게 됐나’를 설명해줍니다.")

D = load_all()
cost = D["cost"]
m1, m2 = month_pickers(D["months"], key="up")
nm = D["name_map"]


def eok_kg(v):  # 원/kg 표기
    return f"{v:,.0f}원/kg"

def sgn(v, unit="원/kg"):
    return ("+" if v >= 0 else "−") + f"{abs(v):,.1f}{unit}"


def hbar(df, xcol, ycol, unit="원/kg", n=12, fmt=None):
    d = df.reindex(df[xcol].abs().sort_values(ascending=False).index).head(n)
    fmt = fmt or (lambda v: sgn(v, unit))
    f = go.Figure(go.Bar(x=d[xcol], y=d[ycol], orientation="h",
        marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in d[xcol]],
        text=[fmt(v) for v in d[xcol]], textposition="auto"))
    f.update_layout(height=380, margin=dict(t=10, b=10), yaxis=dict(autorange="reversed"))
    st.plotly_chart(f, width='stretch')


# ================= 1) 전체 사용단가 (실적) =================
st.header("1. 전체 사용단가 — 실적 기준")
acts = up.actual_up_series(); acts["년월"] = acts["년월"].astype(str)
theos = up.theo_up_series(cost)
sm, mat = up.actual_material_decomp(m1, m2, nm)

k = st.columns(4)
k[0].metric(f"{m1} 사용단가", eok_kg(sm["사용단가_m1"]))
k[1].metric(f"{m2} 사용단가", eok_kg(sm["사용단가_m2"]),
            f"{(sm['사용단가_m2']/sm['사용단가_m1']-1)*100:+.1f}%")
k[2].metric("단가효과", sgn(sm["단가효과"]))
k[3].metric("믹스효과", sgn(sm["믹스효과"]))

c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("사용단가 추이 (6개월)")
    fig = go.Figure()
    fig.add_scatter(x=acts["년월"], y=acts["사용단가"], mode="lines+markers",
                    name="실적", line=dict(color="#D85A30", width=3))
    fig.add_scatter(x=theos["년월"], y=theos["사용단가"], mode="lines+markers",
                    name="이론(BOM)", line=dict(color="#B4B2A9", width=2, dash="dot"))
    fig.update_layout(height=340, margin=dict(t=10, b=10), xaxis=dict(type="category"),
                      legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width='stretch')
    st.caption("실적(설비)과 이론(BOM)의 간격 = 수율·로스(보통 1~2%).")
with c2:
    st.subheader("변동 분해")
    steps = [("단가효과", sm["단가효과"]), ("믹스효과", sm["믹스효과"])]
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=["absolute"] + ["relative"]*3 + ["total"],
        x=["기준"] + [s[0] for s in steps] + ["비교"],
        y=[sm["사용단가_m1"]] + [s[1] for s in steps] + [sm["사용단가_m2"]],
        text=[f"{sm['사용단가_m1']:,.0f}"] + [sgn(s[1], "") for s in steps] + [f"{sm['사용단가_m2']:,.0f}"],
        textposition="outside", decreasing={"marker": {"color": "#378ADD"}},
        increasing={"marker": {"color": "#D85A30"}}, totals={"marker": {"color": "#888780"}}))
    fig.update_layout(height=340, margin=dict(t=20, b=10), showlegend=False, xaxis=dict(type="category"))
    st.plotly_chart(fig, width='stretch')
    st.caption("단가효과=원료 단가 변동 · 믹스효과=원료 구성 변화.")

st.divider()

# ================= 2) 원료 관점 (실적) =================
st.header("2. 왜? — 원료 관점 (실적)")
a, b = st.columns(2)
with a:
    st.subheader("단가효과 — 어느 원료 단가가 움직였나")
    hbar(mat, "단가효과", "원료명")
    st.caption("기여 = 그 원료의 단가변동 × 당월 사용비중. 많이 쓰는 원료의 단가 변동일수록 큼.")
with b:
    st.subheader("믹스효과 — 어느 원료 비중이 바뀌었나")
    hbar(mat, "믹스효과", "원료명")
    st.caption("기여 = 그 원료의 사용비중 변화 × 기준월 단가. 비싼 원료 비중↑ = 사용단가↑.")

st.divider()

# ================= 3) 제품 생산구성 뒷받침 (이론) =================
st.header("3. ⭐ 왜? — 제품 생산구성 (BOM×계획중량 뒷받침)")
sp, prod = up.product_decomp(cost, D["plan"], m1, m2)
st.info(f"제품 생산구성 관점(이론)으로 보면 사용단가 {sp['사용단가_m1']:,.0f}→{sp['사용단가_m2']:,.0f}원/kg, "
        f"**믹스효과 {sgn(sp['믹스효과'])}** · 단가효과 {sgn(sp['단가효과'])}. "
        "실적과 방향은 같고, 수준차는 수율입니다. "
        "아래는 ‘어떤 제품을 더/덜 만들어’ 사용단가를 움직였는지입니다.")
a, b = st.columns(2)
with a:
    st.subheader("믹스효과 — 생산구성 변화(제품)")
    hbar(prod, "믹스효과", "표준제품")
    st.caption("+ = 상대적으로 비싼 제품(예: GF) 비중↑로 사용단가를 끌어올림. − = 저가 제품 비중↑.")
with b:
    st.subheader("단가효과 — 제품 원가 변화")
    hbar(prod, "단가효과", "표준제품")
    st.caption("그 제품 1kg 원가(=배합원료 단가)가 올라 사용단가에 기여한 몫.")

st.divider()

# ================= 4) 원료군별 =================
st.header("4. 원료군별 사용단가·비중 (실적)")
gt = up.group_table(m1, m2)
show = gt.copy()
show["사용단가"] = show.apply(lambda r: f"{r[f'사용단가_{m1}']:,.0f} → {r[f'사용단가_{m2}']:,.0f}", axis=1)
show["단가증감"] = show["단가증감"].map(lambda v: sgn(v))
show["사용비중"] = show.apply(lambda r: f"{r['비중_m1%']:.1f}% → {r['비중_m2%']:.1f}%", axis=1)
st.dataframe(show[["원료군", "사용단가", "단가증감", "사용비중"]], width='stretch', hide_index=True)
st.caption("원료군별 kg당 단가와 사용 비중. 단가 높은 군(아미노산·유지·기능성)의 비중이 커지면 전체 사용단가↑.")

st.divider()

# ================= 5) 브랜드/제품별 =================
st.header("5. 브랜드·제품별 사용단가 (이론 단위원가)")
bt = up.brand_table(cost, D["plan"], m1, m2)
bt2 = bt[(bt[f"생산kg_{m1}"] > 0) | (bt[f"생산kg_{m2}"] > 0)]
fig = go.Figure()
fig.add_bar(name=m1, x=bt2["브랜드"], y=bt2[f"사용단가_{m1}"], marker_color="#B5D4F4")
fig.add_bar(name=m2, x=bt2["브랜드"], y=bt2[f"사용단가_{m2}"], marker_color="#378ADD")
fig.update_layout(barmode="group", height=360, margin=dict(t=10, b=10),
                  legend=dict(orientation="h", y=1.12))
st.plotly_chart(fig, width='stretch')
st.caption("브랜드별 kg당 원료원가. 더리얼(GF 등)이 밥이보약보다 비싼 배합 → 더리얼 생산 비중이 커지면 전체 사용단가↑.")

uc = up.product_unit_cost(cost, D["plan"])
uc = uc[uc["년월"].isin([m1, m2])].pivot_table(index="표준제품", columns="년월",
        values="단위원가", aggfunc="max").reset_index()
for mm in (m1, m2):
    if mm not in uc.columns: uc[mm] = float("nan")
uc["단가증감"] = uc[m2] - uc[m1]
uc = uc.dropna(subset=[m1, m2], how="all").sort_values(m2, ascending=False)
uc[m1] = uc[m1].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
uc[m2] = uc[m2].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "-")
uc["단가증감"] = uc["단가증감"].map(lambda v: sgn(v) if pd.notna(v) else "-")
st.dataframe(uc.rename(columns={m1: f"{m1}(원/kg)", m2: f"{m2}(원/kg)"}),
             width='stretch', hide_index=True, height=360)
st.caption("제품 1kg당 원료원가(단위원가) = BOM 배합 × 단가. 물량과 무관한 순수 원가 수준.")
