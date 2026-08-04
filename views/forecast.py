# -*- coding: utf-8 -*-
"""단위원가 전망 — BOM(고정) × 예상단가. 수준·추세·변동 요약 + 변동 원인(원료별 기여)."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all
from core import db, unitprice as up

st.title("📈 단위원가 전망 (BOM × 예상단가)")
st.caption("배합(BOM)은 고정하고 **원료 단가 변화만** 반영한 제품 1kg당 원가입니다. "
           "데이터는 ‘데이터 관리 → ③ 예상단가’에서 업로드합니다.")

D = load_all()
fp = db.load_forecast()
if fp.empty:
    st.info("예상단가 DB가 비어 있습니다. ‘데이터 관리 → ③ 예상단가’ 탭에서 업로드하세요.")
    st.stop()

prods = sorted(set(D["bom_x"]["표준명칭"].unique()))
c_top1, c_top2 = st.columns([2, 3])
prod = c_top1.selectbox("제품 선택", prods,
                        index=prods.index("더리얼 GF 닭고기 어덜트") if "더리얼 GF 닭고기 어덜트" in prods else 0)

ucf_all, _sub = up.forecast_uc_series(prod, D["bom_x"], fp)
ucf_all = ucf_all[ucf_all["단위원가"] > 0].reset_index(drop=True)
if len(ucf_all) == 0:
    st.warning("이 제품의 BOM 원료에 대한 예상단가가 없습니다.")
    st.stop()

# ---- 기간 선택 (실적/전망 경계 = 실적 단가가 있는 마지막 월) ----
cut = up.forecast_split_month()
months_all = list(ucf_all["년월"])
past_m = [m for m in months_all if cut and m <= cut]
fut_m = [m for m in months_all if cut and m > cut]
opts = ["전체"] + ([f"실적 구간 (~{cut})"] if past_m else []) + ([f"전망 구간 ({fut_m[0]}~)"] if fut_m else [])
period = c_top2.radio("기간", opts, horizontal=True)
sel_m = past_m if period.startswith("실적") else fut_m if period.startswith("전망") else months_all
ucf = ucf_all[ucf_all["년월"].isin(sel_m)].reset_index(drop=True)

st.caption(f"‘실적 구간’은 실제 단가가 확정된 {cut}까지, ‘전망 구간’은 그 이후 예상단가입니다. "
           "두 구간은 성격이 달라 섞어서 통계를 내면 전망의 가정이 과거 변동성처럼 보일 수 있습니다.")

# ---- 요약 KPI (수준 · 추세 · 변동 · 폭) ----
stt = up.uc_stats(ucf)
k = st.columns(4)
k[0].metric("평균 단위원가", f"{stt['평균']:,.0f}원/kg", help="선택 기간의 평균 수준")
k[1].metric("기간 변화율", f"{stt['기간변화율']:+.1f}%",
            f"추세 {stt['월평균추세%']:+.2f}%/월", delta_color="inverse",
            help="기간 변화율 = 첫 달 대비 마지막 달. 추세 = 전 구간 선형 기울기(월평균). "
                 "중간에 올랐다 내려오면 둘의 부호가 다를 수 있습니다.")
k[2].metric("변동성 (추세제거 CV)", f"{stt['추세제거CV']:.1f}%",
            f"단순 CV {stt['CV']:.1f}%", delta_color="off",
            help="추세를 걷어낸 순수 출렁임. 단순 CV는 '꾸준한 상승'도 변동으로 잡히므로 이 값이 안정성 지표")
k[3].metric("레인지", f"{stt['최소']:,.0f} ~ {stt['최대']:,.0f}",
            f"평균 대비 {stt['레인지%']:.1f}%", delta_color="off",
            help="선택 기간의 최저~최고 단위원가")
st.caption(f"기간 {stt['n']}개월. **변동성은 ‘추세제거 CV’로 보세요** — 단순 CV는 계속 오르기만 해도 커져서 "
           "‘불안정’으로 오독됩니다(실제로 두 값이 크게 다르면 그 제품은 흔들린 게 아니라 ‘꾸준히 오른’ 것).")

# ---- 추이 차트 ----
st.subheader("단위원가 월별 추이·전망 (원/kg)")
view = st.radio("보기 방식", ["연속 보기", "연도별 겹치기"], horizontal=True,
                label_visibility="collapsed")
show_label = len(ucf) <= 14

if view == "연속 보기":
    fig = go.Figure()
    p_in = [m for m in sel_m if m in past_m]
    f_in = [m for m in sel_m if m in fut_m]
    if p_in:
        g = ucf[ucf["년월"].isin(p_in)]
        fig.add_scatter(x=g["년월"], y=g["단위원가"], name="실적 구간",
                        mode="lines+markers+text" if show_label else "lines+markers",
                        line=dict(color="#0F6E56", width=3),
                        text=[f"{v:,.0f}" for v in g["단위원가"]] if show_label else None,
                        textposition="top center", textfont=dict(size=10))
    if f_in:
        # 경계월을 포함해 선이 끊기지 않게
        link = ([p_in[-1]] if p_in else []) + f_in
        g = ucf[ucf["년월"].isin(link)]
        fig.add_scatter(x=g["년월"], y=g["단위원가"], name="전망 구간",
                        mode="lines+markers+text" if show_label else "lines+markers",
                        line=dict(color="#BA7517", width=3, dash="dot"),
                        text=[f"{v:,.0f}" for v in g["단위원가"]] if show_label else None,
                        textposition="bottom center", textfont=dict(size=10, color="#854F0B"))
    fig.update_layout(height=380, margin=dict(t=30, b=10), xaxis=dict(type="category"),
                      legend=dict(orientation="h", y=1.12))
else:
    u2 = ucf.copy()
    u2["연도"] = u2["년월"].str[:4]; u2["월"] = u2["년월"].str[5:7].astype(int)
    years = sorted(u2["연도"].unique())
    sel_years = st.multiselect("연도 선택", years, default=years)
    palette = ["#378ADD", "#D85A30", "#1D9E75", "#534AB7", "#BA7517", "#993556"]
    fig = go.Figure()
    for i, y in enumerate(sel_years):
        g = u2[u2["연도"] == y].sort_values("월")
        fig.add_scatter(x=[f"{m}월" for m in g["월"]], y=g["단위원가"],
                        mode="lines+markers+text", name=y,
                        line=dict(color=palette[i % len(palette)], width=3),
                        text=[f"{v:,.0f}" for v in g["단위원가"]],
                        textposition="top center" if i % 2 == 0 else "bottom center",
                        textfont=dict(size=10, color=palette[i % len(palette)]))
    fig.update_layout(height=380, margin=dict(t=30, b=10),
                      xaxis=dict(type="category", categoryorder="array",
                                 categoryarray=[f"{m}월" for m in range(1, 13)]),
                      legend=dict(orientation="h", y=1.12))
    st.caption("같은 달끼리 세로로 비교됩니다 — 연도별 단가 수준 차이와 계절성이 한눈에 보입니다.")
st.plotly_chart(fig, width='stretch')
low_cov = ucf[ucf["단가커버율%"] < 99.5]
if len(low_cov):
    st.warning("일부 월은 단가 없는 원료가 있어 과소계산됨: " +
               ", ".join(f"{r['년월']}({r['단가커버율%']:.0f}%)" for _, r in low_cov.iterrows()))

st.divider()

# ---- 🌊 무엇이 원가를 흔드는가 (원료별 변동 기여도) ----
st.subheader("🌊 무엇이 원가를 흔드는가 — 원료별 변동 기여도")
rc, sigma = up.uc_risk_contribution(prod, sel_m, D["bom_x"], fp, D["name_map"])
if len(rc) == 0:
    st.info("기간이 3개월 미만이라 변동 기여도를 계산할 수 없습니다.")
else:
    st.markdown(f"이 기간 단위원가의 표준편차는 **{sigma:,.1f}원/kg**이고, 아래 기여도의 합과 정확히 일치합니다. "
                "배합률이 커도 단가가 안 움직이면 기여가 0이고, 배합률이 작아도 단가가 요동치면 기여가 큽니다.")
    moved = rc[rc["기여"].abs() > 0.05]
    top = moved.head(12) if len(moved) else rc.head(12)
    figr = go.Figure(go.Bar(
        x=top["기여"], y=top["원료명"], orientation="h",
        marker_color=["#D85A30" if v >= 0 else "#378ADD" for v in top["기여"]],
        text=[f"{v:,.1f} ({p:.1f}%)" for v, p in zip(top["기여"], top["기여비중%"])],
        textposition="auto"))
    figr.update_layout(height=max(240, 34 * len(top) + 60), margin=dict(t=10, b=10),
                       yaxis=dict(autorange="reversed"), xaxis_title="변동 기여 (원/kg)")
    st.plotly_chart(figr, width='stretch')
    if len(rc):
        t1 = rc.iloc[0]
        st.success(f"**관리 포인트: {t1['원료명']}** — 이 원료 하나가 단위원가 변동의 "
                   f"**{abs(t1['기여비중%']):.1f}%**를 차지합니다 "
                   f"(배합 {t1['배합률%']:.2f}%, 단가 평균 {t1['단가평균']:,.0f} ± {t1['단가σ']:,.0f}원/kg). "
                   "이 원료 단가를 고정하면 원가 변동이 그만큼 줄어듭니다.")
    tv = rc.copy()
    tv["배합률"] = tv["배합률%"].map(lambda v: f"{v:.2f}%")
    tv["단가 (평균±σ)"] = tv.apply(lambda r: f"{r['단가평균']:,.0f} ± {r['단가σ']:,.0f}", axis=1)
    tv["변동 기여"] = tv["기여"].map(lambda v: f"{v:+,.1f}원/kg")
    tv["기여 비중"] = tv["기여비중%"].map(lambda v: f"{v:.1f}%")
    st.dataframe(tv[["원료코드", "원료명", "배합률", "단가 (평균±σ)", "변동 기여", "기여 비중"]],
                 width='stretch', hide_index=True, height=360)

st.divider()

# ---- 🔎 두 달 비교 원인 분해 ----
st.subheader("🔎 두 달 비교 — 단위원가 변화 원인")
c1, c2 = st.columns(2)
fm2 = c2.selectbox("비교월", sel_m, index=len(sel_m) - 1, key="fc_m2")
prev = [m for m in sel_m if m < fm2] or sel_m[:1]
fm1 = c1.selectbox("기준월", sel_m, index=sel_m.index(prev[-1]), key="fc_m1")

br = up.forecast_uc_bridge(prod, fm1, fm2, D["bom_x"], fp, D["name_map"])
u1v = float(ucf[ucf["년월"] == fm1]["단위원가"].iloc[0])
u2v = float(ucf[ucf["년월"] == fm2]["단위원가"].iloc[0])
k2 = st.columns(3)
k2[0].metric(f"{fm1} 단위원가", f"{u1v:,.0f}원/kg")
k2[1].metric(f"{fm2} 단위원가", f"{u2v:,.0f}원/kg",
             f"{(u2v/u1v-1)*100:+.1f}%" if u1v else None)
k2[2].metric("변화", f"{u2v-u1v:+,.1f}원/kg")

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
    tt["기여"] = tt["기여(원/kg)"].map(lambda v: f"{v:+,.1f}원/kg")
    st.dataframe(tt[["원료코드", "원료명", "배합률", "단가(원/kg)", "기여"]],
                 width='stretch', hide_index=True)
