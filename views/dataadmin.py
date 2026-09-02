# -*- coding: utf-8 -*-
"""⑤ 데이터 관리 — 통합파일 자동 월분리 업로드 + 표준 양식 다운로드."""
import streamlit as st
import pandas as pd
from io import BytesIO
from core import db, ingest, templates, model, dims
from core import unitprice as upx

st.title("🗂️ 데이터 관리 — 월 마감")
st.caption("① 관리자 계획중량(작업일자로 월 자동분리) → ② 원료 단가·사용량(년월로 월 자동분리) → 분석")

tab1, tab2, tab_f, tab3, tab_uc, tab4 = st.tabs(
    ["① 관리자 계획중량", "② 단가·사용량", "③ 예상단가", "④ 업로드 양식",
     "⑤ 단위원가 일괄 출력", "DB 미리보기"])

with tab_f:
    st.markdown("**예상단가**(년월·원료코드·단가) 파일을 올리면 `년월`으로 자동 분리합니다. "
                "미래 월 단가를 넣으면 **제품 드릴다운 → 단위원가 월별 전망**에 반영됩니다. "
                "같은 년월은 덮어씁니다.")
    upf = st.file_uploader("예상단가 파일 (여러 달 통합)", type=["xls", "xlsx"], key="fc_up")
    if upf:
        try:
            fmonths, frep = ingest.parse_forecast_multi(upf)
        except ValueError as e:
            st.error(str(e)); st.stop()
        summf = pd.DataFrame([
            {"년월": ym, "원료 코드수": frep["월별"][ym]["코드수"],
             "단가 0원": frep["월별"][ym]["단가0"]} for ym in sorted(fmonths)])
        c = st.columns(3)
        c[0].metric("분리된 월수", f"{len(fmonths)}개월")
        c[1].metric("무효 행", frep["무효행"])
        c[2].metric("단가 0원 총", int(summf["단가 0원"].sum()))
        st.dataframe(summf, width='stretch', hide_index=True)
        if st.button("전체 월 예상단가 DB 반영", type="primary", key="fc_apply"):
            db.upsert_forecast_multi(fmonths); st.cache_data.clear()
            st.success(f"{len(fmonths)}개월 반영 완료: {', '.join(sorted(fmonths))}")
    cur = db.load_forecast()
    if len(cur):
        st.caption(f"현재 예상단가 DB: {cur['년월'].nunique()}개월 "
                   f"({sorted(cur['년월'].astype(str).unique())[0]} ~ "
                   f"{sorted(cur['년월'].astype(str).unique())[-1]}) · {len(cur):,}행")

with tab1:
    st.markdown("여러 달이 섞인 **관리자 계획중량** 파일을 올리면 `작업일자`로 월을 자동 분리, "
                "품목명을 표준제품으로 매핑·집계합니다.")
    up = st.file_uploader("관리자 계획중량 파일 (여러 달 통합)", type=["xls", "xlsx"], key="plan_up")
    if up:
        months, rep = ingest.parse_plan_multi(up)
        summ = pd.DataFrame([
            {"년월": ym, "행수": rep["월별"][ym]["행수"], "제품수": rep["월별"][ym]["제품수"],
             "생산중량(kg)": round(rep["월별"][ym]["생산kg"])} for ym in sorted(months)])
        c = st.columns(4)
        c[0].metric("분리된 월수", f"{len(months)}개월")
        c[1].metric("총 행수", int(summ["행수"].sum()))
        c[2].metric("미매칭 품목", len(rep["미매칭"]))
        c[3].metric("무효 작업일자행", rep["무효작업일자행"])
        st.dataframe(summ, width='stretch', hide_index=True)
        if rep["미매칭"]:
            st.error("미매칭 품목 — 매핑표 보완 필요(반영 차단):"); st.write(rep["미매칭"])
        if rep["복수제품행"]:
            st.warning(f"한 행에 여러 제품 {rep['복수제품행']}건 (중량 균등배분)")
        if st.button("전체 월 생산계획 DB 반영", type="primary", disabled=bool(rep["미매칭"])):
            db.upsert_plan_multi(months); st.cache_data.clear()
            st.success(f"{len(months)}개월 반영 완료: {', '.join(sorted(months))}")

with tab2:
    st.markdown("여러 달이 섞인 **단가·사용량** 파일을 올리면 `년월`으로 월을 자동 분리합니다. "
                "양식은 '③ 업로드 양식' 탭에서 받으세요.")
    up2 = st.file_uploader("단가·사용량 파일 (여러 달 통합)", type=["xls", "xlsx"], key="price_up")
    if up2:
        try:
            months, rep = ingest.parse_price_multi(up2)
        except ValueError as e:
            st.error(str(e)); st.stop()
        summ = pd.DataFrame([
            {"년월": ym, "원료 코드수": rep["월별"][ym]["코드수"],
             "단가 0원": rep["월별"][ym]["단가0"]} for ym in sorted(months)])
        c = st.columns(3)
        c[0].metric("분리된 월수", f"{len(months)}개월")
        c[1].metric("무효 행", rep["무효행"])
        c[2].metric("단가 0원 총", int(summ["단가 0원"].sum()))
        st.dataframe(summ, width='stretch', hide_index=True)
        if st.button("전체 월 단가·사용량 DB 반영", type="primary"):
            db.upsert_price_multi(months); st.cache_data.clear()
            st.success(f"{len(months)}개월 반영 완료: {', '.join(sorted(months))}")

with tab3:
    st.markdown("매달 채워서 올릴 **표준 양식**입니다. 원료마스터가 채워져 있어 코드를 그대로 쓰면 됩니다.")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("② 단가·사용량 양식")
        st.caption("년월·원료코드·단가·사용량·금액 (매달 아래에 이어붙여 통합 업로드)")
        st.download_button("📥 단가·사용량 양식 다운로드", templates.price_template(),
                           file_name="업로드양식_원료단가사용.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c2:
        st.subheader("① 관리자 계획중량 양식")
        st.caption("ERP 내보내기 형식(작업일자·품목명·관리자 계획중량). 원본 그대로 업로드 가능")
        st.download_button("📥 계획중량 양식 다운로드", templates.plan_template(),
                           file_name="업로드양식_관리자계획중량.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab4:
    p = db.load_plan()
    st.subheader(f"생산계획 — {p['년월'].nunique()}개월")
    st.dataframe(p.pivot_table(index="표준제품", columns="년월", values="계획중량",
                               aggfunc="sum", fill_value=0), width='stretch', height=300)
    st.subheader("원료 단가·사용량")
    pr = db.load_price()
    st.dataframe(pr.pivot_table(index="원료코드", columns="년월", values="단가",
                                aggfunc="max", fill_value=0), width='stretch', height=260)
    if st.button("캐시 새로고침"):
        st.cache_data.clear(); st.success("캐시를 비웠습니다.")

with tab_uc:
    st.markdown("**전 제품 × 전 월 단위원가(원/kg)** 를 한 번에 계산해 표로 보고 파일로 내려받습니다. "
                "`단위원가 = Σ(BOM 배합률 × 예상단가)` — 배합은 고정, 단가만 월별로 반영됩니다.")
    fp_uc = db.load_forecast()
    if fp_uc.empty:
        st.info("예상단가 DB가 비어 있습니다. ‘③ 예상단가’ 탭에서 먼저 업로드하세요.")
    else:
        bom_uc = model.explode_bom()
        uc, cov, miss = upx.forecast_uc_matrix(bom_uc, fp_uc)
        if uc.empty:
            st.warning("BOM과 예상단가가 겹치는 원료가 없습니다.")
        else:
            months_uc = list(uc.columns)
            plan_uc = db.load_plan().copy()
            plan_uc["년월"] = plan_uc["년월"].astype(str)
            pm = (plan_uc.pivot_table(index="표준제품", columns="년월", values="계획중량",
                                      aggfunc="sum")
                  .reindex(index=uc.index, columns=months_uc).fillna(0))
            produced = pm > 0
            n_bad = int((miss > 0).sum().sum())

            c = st.columns(4)
            c[0].metric("제품 수", f"{len(uc)}종")
            c[1].metric("기간", f"{len(months_uc)}개월")
            c[2].metric("범위", f"{months_uc[0]} ~ {months_uc[-1]}")
            c[3].metric("단가 결측 칸", f"{n_bad}칸",
                        help="BOM 원료 중 그 달 단가가 0원인 원료가 있어 단위원가가 과소계산되는 칸. "
                             "배합률이 작아도 고가 원료면 원가가 크게 튀므로 커버율%가 아닌 이 값을 기준으로 봅니다.")

            o1, o2 = st.columns(2)
            hide_bad = o1.checkbox("단가 결측 칸 비우기", value=True,
                                   help="단가 없는 원료가 섞인 달은 값을 비웁니다. 끄면 과소계산된 값이 그대로 보여, "
                                        "나중에 그 원료 단가가 생기는 달에 급등한 것처럼 나타납니다.")
            only_prod = o2.checkbox("생산 있는 달만 보기", value=False,
                                    help="생산계획이 있는 달·제품만 남깁니다. 미래 전망 구간은 생산계획이 없어 사라지므로 기본은 꺼둡니다.")

            sel = st.multiselect("기간 선택 (비우면 전체)", months_uc, default=[])
            cols = sel or months_uc
            if only_prod:
                cols = [m for m in cols if bool(produced[m].any())]

            if not cols:
                st.warning("선택 조건에 해당하는 달이 없습니다. ‘생산 있는 달만 보기’를 해제하거나 기간을 다시 선택하세요.")
            else:
                val = uc[cols].copy()
                if hide_bad:
                    val = val.mask(miss[cols] > 0)
                if only_prod:
                    val = val.mask(~produced[cols])
                val = val.round(0)

                out = val.reset_index().rename(columns={"표준명칭": "표준제품"})
                out.insert(1, "브랜드", out["표준제품"].map(dims.brand_of))
                out.insert(2, "생산월수", produced[cols].sum(axis=1).values)
                if len(cols) >= 2:
                    out.insert(3, "평균", val.mean(axis=1).round(0).values)
                    out.insert(4, "최소", val.min(axis=1).round(0).values)
                    out.insert(5, "최대", val.max(axis=1).round(0).values)
                    def _chg(r):
                        v = r.dropna()
                        return round((v.iloc[-1] / v.iloc[0] - 1) * 100, 1) if len(v) >= 2 and v.iloc[0] else None
                    out.insert(6, "기간변화율%", val.apply(_chg, axis=1).values)

                brands = ["전체"] + sorted(out["브랜드"].unique())
                bsel = st.selectbox("브랜드 필터", brands, key="uc_brand")
                view = out if bsel == "전체" else out[out["브랜드"] == bsel]
                if only_prod:
                    view = view[view["생산월수"] > 0]

                cfg = {m: st.column_config.NumberColumn(m, format="%d") for m in cols}
                for kk in ["평균", "최소", "최대"]:
                    if kk in view.columns:
                        cfg[kk] = st.column_config.NumberColumn(kk, format="%d")
                if "기간변화율%" in view.columns:
                    cfg["기간변화율%"] = st.column_config.NumberColumn("기간변화율%", format="%.1f%%")
                st.dataframe(view, width='stretch', hide_index=True, height=460, column_config=cfg)
                st.caption(f"표시 {len(view)}종 × {len(cols)}개월. "
                           + ("빈칸 = 단가 결측(과소계산 방지). " if hide_bad else "⚠️ 결측 칸 포함 — 신규 원료 단가가 생기는 달에 급등처럼 보일 수 있습니다. ")
                           + "‘생산월수’는 선택 기간 중 실제 생산계획이 있던 달 수입니다.")

                detail = upx.forecast_missing_detail(bom_uc, fp_uc)
                f1, f2 = st.columns(2)
                f1.download_button("📥 CSV 다운로드", view.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"단위원가_일괄_{cols[0]}_{cols[-1]}.csv",
                                   mime="text/csv", width='stretch')
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    view.to_excel(w, sheet_name="단위원가", index=False)
                    if len(detail):
                        detail.to_excel(w, sheet_name="단가결측", index=False)
                    (produced[cols].astype(int).reset_index()
                     .rename(columns={"표준명칭": "표준제품"})).to_excel(w, sheet_name="생산여부", index=False)
                f2.download_button("📥 Excel (결측·생산여부 시트 포함)", buf.getvalue(),
                                   file_name=f"단위원가_일괄_{cols[0]}_{cols[-1]}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   width='stretch')

                if n_bad:
                    with st.expander(f"⚠️ 단가 결측 {n_bad}칸 — 어떤 원료 단가를 채워야 하나"):
                        st.dataframe(detail, width='stretch', hide_index=True)
                        st.caption("배합률이 작아도 고가 원료(예: 난각막 분말 45만원/kg, 배합 0.07%)가 빠지면 "
                                   "단위원가가 300원/kg 이상 낮게 잡힙니다. ‘③ 예상단가’에서 해당 월 단가를 채우면 해소됩니다.")
