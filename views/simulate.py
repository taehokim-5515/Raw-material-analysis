# -*- coding: utf-8 -*-
"""단가 시뮬레이션 — 원료 단가를 바꾸면 제품 kg당 원재료비가 얼마나 바뀌나."""
from io import BytesIO
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from app_common import load_all, won, signed_won
from core import simulate as sim, theme

st.title("단가 시뮬레이션")
st.caption("원료 단가를 바꾸면 그 원료를 쓰는 제품의 kg당 원재료비가 얼마나 바뀌는지 계산합니다. "
           "배합비는 기준월에 유효한 버전을 쓰고, 키블 반제품의 하위 원료는 자동으로 전개됩니다.")

D = load_all()
nm = D["name_map"]

# ---------- 기준 ----------
months = sim.base_months()
srcs = [s for s in (sim.SRC_ACTUAL, sim.SRC_FORECAST) if months[s]]
if not srcs:
    st.info("단가 데이터가 없습니다. 데이터 관리에서 원료 단가나 예상단가를 먼저 올려주세요.")
    st.stop()
b1, b2 = st.columns([1, 1])
src = b1.radio("단가 기준", srcs, horizontal=True, key="sim_src",
               help="실적 단가는 확정된 달, 예상단가는 앞으로의 달까지 고를 수 있습니다.")
mlist = months[src]
ym = b2.selectbox("기준월", mlist, index=len(mlist) - 1, key=f"sim_ym_{src}")

opts = sim.material_options(ym, src, nm)
info = opts.set_index("ERP코드")

tab_sim, tab_sens = st.tabs(["시뮬레이션", "원료 민감도 순위"])

# ================= 시뮬레이션 =================
def _sim_tab():
    picked = st.multiselect(
        "바꿀 원료", list(opts["ERP코드"]), key="sim_pick",
        format_func=lambda c: f"{info.at[c, '원료명']} ({c}), {int(info.at[c, '사용제품수'])}개 제품",
        placeholder="원료명이나 코드로 검색", help="기준월 배합비에 들어 있는 원료만 나옵니다. 여러 개를 함께 바꿀 수 있습니다.")

    if not picked:
        st.info("바꿀 원료를 고르면 그 원료를 쓰는 제품의 kg당 원재료비 변화가 여기에 나옵니다. "
                "여러 원료를 함께 고르면 동시에 움직였을 때의 영향과 원료별 기여를 같이 보여줍니다.")
        return

    new_prices, bad = {}, []
    h = st.columns([3, 2, 2, 2, 2])
    for col, t in zip(h, ["원료", "현재 단가", "입력 방식", "값", "새 단가"]):
        col.caption(t)
    for c in picked:
        p0 = float(info.at[c, "현재단가"])
        r = st.columns([3, 2, 2, 2, 2], vertical_alignment="center")
        r[0].markdown(f"**{info.at[c, '원료명']}**  \n{c}")
        r[1].markdown(f"{p0:,.0f}원/kg")
        mode = r[2].radio("입력 방식", ["변동률", "새 단가"], key=f"sim_mode_{c}",
                          horizontal=True, label_visibility="collapsed",
                          index=0 if p0 > 0 else 1)
        if mode == "변동률":
            v = r[3].number_input("변동률(%)", value=10.0, step=1.0, min_value=-99.9,
                                  format="%.1f", key=f"sim_pct_{c}", label_visibility="collapsed")
            if p0 <= 0:
                bad.append(f"{info.at[c, '원료명']}: 기준월 단가가 없어 변동률을 쓸 수 없습니다. 새 단가로 입력하세요.")
                r[4].markdown("계산 불가")
                continue
            p1 = p0 * (1 + v / 100.0)
        else:
            p1 = r[3].number_input("새 단가(원/kg)", value=round(p0), step=10, min_value=0,
                                   key=f"sim_abs_{src}_{ym}_{c}", label_visibility="collapsed")
            p1 = float(p1)
        d = p1 - p0
        r[4].markdown(f"**{p1:,.0f}원**  \n{'+' if d >= 0 else '−'}{abs(d):,.0f}원"
                      + (f", {d / p0 * 100:+.1f}%" if p0 > 0 else ""))
        new_prices[c] = p1

    for b in bad:
        st.warning(b)
    if not new_prices:
        return

    prod, mat, s = sim.simulate(ym, new_prices, src, nm)
    if prod.empty:
        st.info("고른 원료를 쓰는 제품이 기준월 배합비에 없습니다.")
        return

    st.divider()
    made = prod[prod["생산kg"] > 0]
    st.metric(f"월 원료비 영향 ({s['물량월']} 생산량 기준)", signed_won(s["월영향"]) + "원")
    line = (f"영향 받는 제품 {s['영향제품수']}종, 그중 {s['물량월']}에 생산한 제품 {len(made)}종. "
            f"전체 생산량 가중 평균 kg당 {s['가중평균']:+,.1f}원, "
            f"가장 크게 바뀌는 제품은 {s['최대제품']} ({s['최대변화']:+,.1f}원/kg).")
    if s["물량월"] != ym:
        line += f" {ym}은 생산계획이 없어 최신 계획월 {s['물량월']} 물량으로 환산했습니다."
    st.caption(line)
    if src == sim.SRC_ACTUAL:
        act = sim.actual_usage_impact(ym, new_prices)
        st.caption(f"같은 변동을 {ym} 실적 사용량에 적용하면 {signed_won(act)}원입니다. "
                   "BOM이 없는 라인(퀴진, 트릿 등)과 수율 차이 때문에 위 값과 다를 수 있습니다.")

    # ---- 차트: 제품별 kg당 변화 ----
    st.subheader("제품별 kg당 원재료비 변화")
    top = prod.head(15)
    fig = go.Figure(go.Bar(
        x=top["변화"], y=top["제품"], orientation="h",
        marker_color=theme.updown(top["변화"]),
        text=[f"{v:+,.1f}원" for v in top["변화"]], textposition="auto"))
    fig.update_layout(height=max(260, 30 * len(top) + 60), margin=dict(t=10, b=10),
                      yaxis=dict(autorange="reversed"), xaxis_title="원/kg")
    st.plotly_chart(fig, width='stretch')
    if len(prod) > 15:
        st.caption(f"변화가 큰 15개 제품입니다. 전체 {len(prod)}종은 아래 표에 있습니다.")

    # ---- 표: 제품별 ----
    show = prod[["제품", "브랜드", "경로", "대상배합률", "현재", "변경후", "변화", "변화율",
                 "생산kg", "월영향"]].copy()
    show["기준값"] = ["단가 빠진 원료 있음" if n else "" for n in prod["결측원료수"]]
    show = show.round({"현재": 0, "변경후": 0, "생산kg": 0, "월영향": 0})
    st.dataframe(
        show, width='stretch', hide_index=True, height=420,
        column_config={
            "경로": st.column_config.TextColumn("경로", help="키블 경유는 키블 반제품을 통해 들어가는 몫"),
            "대상배합률": st.column_config.NumberColumn("배합률(%)", format="%.3f",
                                                   help="바꾼 원료들이 이 제품에서 차지하는 배합률 합"),
            "현재": st.column_config.NumberColumn("현재(원/kg)", format="localized"),
            "변경후": st.column_config.NumberColumn("변경 후(원/kg)", format="localized"),
            "변화": st.column_config.NumberColumn("변화(원/kg)", format="%+.2f"),
            "변화율": st.column_config.NumberColumn("변화율", format="%+.2f%%"),
            "생산kg": st.column_config.NumberColumn(f"{s['물량월']} 생산(kg)", format="localized"),
            "월영향": st.column_config.NumberColumn("월 영향(원)", format="localized"),
            "기준값": st.column_config.TextColumn("확인", help="기준월에 단가가 없는 원료가 있으면 현재 원/kg이 낮게 잡힙니다. 변화량은 정확합니다."),
        })
    st.caption("변화(원/kg) = 배합률 × 단가 변동. 생산이 없는 제품은 월 영향이 0입니다.")

    if len(mat) > 1:
        with st.expander(f"원료별 기여 ({len(mat)}개 원료)"):
            mshow = mat[["원료명", "ERP코드", "현재단가", "새단가", "단가변동", "사용제품수", "최대변화", "월영향"]]                 .round({"현재단가": 0, "새단가": 0, "단가변동": 0, "월영향": 0})
            st.dataframe(mshow, width='stretch', hide_index=True, column_config={
                "현재단가": st.column_config.NumberColumn("현재 단가", format="localized"),
                "새단가": st.column_config.NumberColumn("새 단가", format="localized"),
                "단가변동": st.column_config.NumberColumn("변동", format="localized"),
                "최대변화": st.column_config.NumberColumn("제품 최대 변화(원/kg)", format="%.2f"),
                "월영향": st.column_config.NumberColumn("월 영향(원)", format="localized"),
            })
            st.caption("단가 영향은 원료끼리 더해지므로 원료별 월 영향의 합이 전체 월 영향과 같습니다.")

    with st.expander("브랜드별 요약"):
        bt = (prod.groupby("브랜드")
              .agg(제품수=("제품", "count"), 생산kg=("생산kg", "sum"), 월영향=("월영향", "sum"))
              .reset_index())
        bt["kg당"] = bt["월영향"] / bt["생산kg"].where(bt["생산kg"] > 0)
        bt = bt.round({"생산kg": 0, "월영향": 0})
        st.dataframe(bt.sort_values("월영향", key=lambda x: x.abs(), ascending=False),
                     width='stretch', hide_index=True, column_config={
                         "생산kg": st.column_config.NumberColumn("생산(kg)", format="localized"),
                         "월영향": st.column_config.NumberColumn("월 영향(원)", format="localized"),
                         "kg당": st.column_config.NumberColumn("생산 kg당(원)", format="%+.2f"),
                     })

    scen = pd.DataFrame([{"원료코드": c, "원료명": info.at[c, "원료명"],
                          "현재 단가": float(info.at[c, "현재단가"]), "새 단가": p}
                         for c, p in new_prices.items()])
    scen.insert(0, "기준", f"{src} {ym}")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        scen.to_excel(w, sheet_name="시나리오", index=False)
        show.to_excel(w, sheet_name="제품별", index=False)
        mat.to_excel(w, sheet_name="원료별", index=False)
    st.download_button("결과 엑셀로 받기", buf.getvalue(), file_name=f"단가시뮬레이션_{ym}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


with tab_sim:
    _sim_tab()

# ================= 민감도 =================
with tab_sens:
    st.markdown("모든 원료를 **하나씩** 같은 비율로 바꿨을 때 월 원료비가 얼마나 움직이는지 순서대로 보여줍니다. "
                "단가 협상이나 가격 고정을 어느 원료부터 할지 정할 때 씁니다.")
    pct = st.number_input("변동률(%)", value=10.0, step=1.0, min_value=-99.9, format="%.1f", key="sens_pct")
    g, gs = sim.sensitivity(ym, pct, src, nm)
    st.caption(f"{gs['물량월']} 생산량 기준 이론 원료비 {won(gs['기준원료비'])}원에서, "
               f"원료 하나가 {pct:+.1f}% 움직일 때의 영향입니다.")
    top = g.head(15)
    figs = go.Figure(go.Bar(
        x=top["월영향"], y=top["원료명"], orientation="h",
        marker_color=theme.updown(top["월영향"]),
        text=[signed_won(v) + "원" for v in top["월영향"]], textposition="auto"))
    figs.update_layout(height=max(260, 30 * len(top) + 60), margin=dict(t=10, b=10),
                       yaxis=dict(autorange="reversed"), xaxis_title="월 원료비 영향(원)")
    st.plotly_chart(figs, width='stretch')
    gv = g[["순위", "원료명", "ERP코드", "현재단가", "사용제품수", "월영향", "원료비대비",
            "최대변화", "최대제품"]].round({"현재단가": 0, "월영향": 0})
    st.dataframe(gv, width='stretch', hide_index=True, height=460, column_config={
        "현재단가": st.column_config.NumberColumn("현재 단가", format="localized"),
        "사용제품수": st.column_config.NumberColumn("사용 제품"),
        "월영향": st.column_config.NumberColumn("월 영향(원)", format="localized"),
        "원료비대비": st.column_config.NumberColumn("원료비 대비", format="%+.2f%%"),
        "최대변화": st.column_config.NumberColumn("제품 최대 변화(원/kg)", format="%+.2f"),
        "최대제품": st.column_config.TextColumn("가장 크게 바뀌는 제품"),
    })
    st.caption("단가가 비싸도 적게 쓰면 영향이 작고, 싸도 많은 제품에 많이 쓰면 큽니다. "
               "순위는 기준월 생산 구성에 따라 달라집니다.")
