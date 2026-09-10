# -*- coding: utf-8 -*-
"""⑤ 데이터 관리 — 통합파일 자동 월분리 업로드 + 표준 양식 다운로드."""
import streamlit as st
import pandas as pd
from io import BytesIO
from core import db, ingest, templates, model, dims, config as C
from core import unitprice as upx

st.title("🗂️ 데이터 관리 — 월 마감")
st.caption("① 관리자 계획중량(작업일자로 월 자동분리) → ② 원료 단가·사용량(년월로 월 자동분리) → 분석")

tab1, tab2, tab_f, tab3, tab_uc, tab_bom, tab4 = st.tabs(
    ["① 관리자 계획중량", "② 단가·사용량", "③ 예상단가", "④ 업로드 양식",
     "⑤ 단위원가 일괄 출력", "⑥ 배합비(BOM) 버전", "DB 미리보기"])

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
                "`단위원가 = Σ(배합률 × 예상단가)` — 단가는 물론 **배합비도 그 달에 유효한 버전**이 적용됩니다. "
                "배합을 바꾼 달 전후가 서로 다른 배합으로 환산됩니다.")
    fp_uc = db.load_forecast()
    if fp_uc.empty:
        st.info("예상단가 DB가 비어 있습니다. ‘③ 예상단가’ 탭에서 먼저 업로드하세요.")
    else:
        bom_all_uc = db.load_bom_all()
        uc, cov, miss = upx.forecast_uc_matrix(None, fp_uc, bom_all=bom_all_uc)
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

                detail = upx.forecast_missing_detail(None, fp_uc, bom_all=bom_all_uc)
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

with tab_bom:
    st.markdown("배합비가 바뀌면 **바뀐 제품만** 새 파일로 올리고 "
                "**적용 시작월**을 고릅니다. 종료월은 입력하지 않습니다 — "
                "다음 버전이 나오기 전까지 자동으로 유효하고, "
                "그 이전 달은 예전 배합으로 계산됩니다.")

    bom_all = db.load_bom_all()
    vers = db.bom_versions()
    c = st.columns(4)
    c[0].metric("등록 버전", f"{len(vers)}개")
    c[1].metric("제품 수", f"{bom_all['표준명칭'].nunique()}종")
    c[2].metric("총 원료행", f"{len(bom_all):,}행")
    c[3].metric("저장 위치", "Supabase" if db.backend() == "supabase" else "엑셀 파일")

    _seed_needed = (db.backend() == "supabase" and len(vers) == 1
                    and str(vers["적용시작"].iloc[0]) == C.BOM_BASE_YM)
    if _seed_needed and "_bom_seeded" not in st.session_state:
        with st.expander("⚙️ 처음이라면 — 현재 배합비를 DB에 기준버전으로 올리기"):
            st.caption("Supabase에 `bom` 테이블을 만든 뒤 한 번만 누르세요. "
                       "`data/bom_table.sql`을 Supabase → SQL Editor에 붙여넣어 실행하면 테이블이 생깁니다. "
                       "테이블이 없거나 비어 있는 동안에는 기존 `bom_master.xlsx`를 그대로 읽으므로 "
                       "앱은 정상 동작합니다.")
            if st.button("현재 배합비를 기준버전으로 DB 적재", key="bom_seed"):
                db.seed_bom_from_file()
                st.session_state["_bom_seeded"] = True
                st.cache_data.clear()
                st.success(f"기준버전({C.BOM_BASE_YM}) 적재 완료.")
                st.rerun()

    st.divider()
    st.subheader("새 배합비 올리기")

    _pm = sorted(db.load_plan()["년월"].astype(str).unique())
    _base = _pm[-1] if _pm else "2026-01"
    _y, _m = int(_base[:4]), int(_base[5:7])
    cand = []
    for _k in range(-24, 13):
        _yy, _mm = _y + (_m - 1 + _k) // 12, (_m - 1 + _k) % 12 + 1
        cand.append(f"{_yy:04d}-{_mm:02d}")
    cand = sorted(set(cand) | (set(vers["적용시작"].astype(str)) - {C.BOM_BASE_YM}))

    ub = st.file_uploader("배합비 파일 (표준명칭·ERP코드·배합률)", type=["xls", "xlsx"], key="bom_up")
    if ub:
        try:
            bdf, brep = ingest.parse_bom(ub)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        k = st.columns(4)
        k[0].metric("제품 수", f"{brep['제품수']}종")
        k[1].metric("원료행", f"{brep['행수']:,}행")
        k[2].metric("무효 행", brep["무효행"])
        k[3].metric("합계 100% 아님", f"{len(brep['합계이상'])}종")
        if brep["합계이상"]:
            st.error("배합률 합계가 100±0.5%를 벗어난 제품 — 확인 후 다시 올리세요. (저장 차단)")
            st.dataframe(pd.DataFrame(brep["합계이상"], columns=["표준명칭", "배합합%"]),
                         width='stretch', hide_index=True)
        if brep["신규제품"]:
            st.warning("기존 배합비에 없던 제품입니다. 제품명 오타가 아닌지 확인하세요 — "
                       + ", ".join(brep["신규제품"]))

        eff = st.selectbox("적용 시작월 — 이 달부터 새 배합이 적용됩니다",
                           cand, index=max(0, len(cand) - 13), key="bom_eff")

        prods = sorted(bdf["표준명칭"].unique())
        prev = db.pick_bom_version(bom_all, eff)
        prev = prev[prev["표준명칭"].isin(prods)]

        e1, e2 = st.columns([1, 2])
        limited = e1.checkbox("기간 한정", key="bom_limited",
                              help="원료 수급 문제로 몇 달만 대체 배합을 쓰는 경우처럼, "
                                   "정해진 달까지만 적용하고 원래 배합으로 되돌릴 때 사용합니다.")
        endm = revert = None
        if limited:
            ends = [m for m in cand if m >= eff]
            endm = e2.selectbox("적용 종료월 — 이 달까지만 적용", ends, key="bom_end")
            _ey, _em = int(endm[:4]), int(endm[5:7])
            revert = f"{_ey + _em // 12:04d}-{_em % 12 + 1:02d}"
            if prev.empty:
                st.error("되돌릴 이전 배합이 없습니다(전부 신규 제품). 기간 한정을 쓸 수 없습니다.")
                revert = None
            else:
                _clash = bom_all[(bom_all["적용시작"].astype(str) == revert)
                                 & (bom_all["표준명칭"].isin(prods))]
                if len(_clash):
                    st.warning(f"{revert}에 이미 등록된 버전이 있습니다 "
                               f"({_clash['표준명칭'].nunique()}개 제품). 저장하면 덮어씁니다.")
                st.info(f"**{eff} ~ {endm}** 새 배합 적용 → **{revert}부터 지금 배합으로 자동 복귀**. "
                        "버전 2개가 만들어지며, 목록에서 각각 따로 지울 수 있습니다.")

        note = st.text_input("변경 사유 (선택)", placeholder="예: 원가절감 — 관절 라인 콜라겐 대체")
        cmp = (bdf.set_index(["표준명칭", "ERP코드"])["배합률"].rename("신규").to_frame()
               .join(prev.set_index(["표준명칭", "ERP코드"])["배합률"].rename("기존"),
                     how="outer").fillna(0.0).reset_index())
        cmp["변동"] = cmp["신규"] - cmp["기존"]
        chg = cmp[cmp["변동"].abs() > 1e-9].copy()

        st.markdown(f"**변경 미리보기 — {eff} 시점 현재 배합 대비**")
        if len(chg) == 0:
            st.info("현재 적용 중인 배합과 동일합니다. 저장해도 계산 결과는 달라지지 않습니다.")
        else:
            mm0 = db.load_material_master()
            nm0 = dict(zip(mm0["ERP코드"].astype(str), mm0["대표원료명"]))
            show = chg.copy()
            show["원료명"] = show["ERP코드"].map(nm0)
            show["구분"] = ["신규 투입" if a == 0 else ("제외" if b == 0 else "비율 변경")
                          for a, b in zip(show["기존"], show["신규"])]
            show["기존"] = show["기존"].map(lambda v: f"{v:.4f}")
            show["신규"] = show["신규"].map(lambda v: f"{v:.4f}")
            show["변동"] = show["변동"].map(lambda v: f"{v:+.4f}")
            st.dataframe(show[["표준명칭", "ERP코드", "원료명", "구분", "기존", "신규", "변동"]],
                         width='stretch', hide_index=True, height=280)
            st.caption(f"{chg['표준명칭'].nunique()}개 제품 · {len(chg)}개 원료 변경. "
                       "저장하면 이 달부터의 이론 원료비·단위원가가 새 배합으로 다시 계산되고, "
                       "‘사용단가 분석’ 페이지에 **배합효과**로 분리되어 나타납니다.")

        _label = (f"{eff} ~ {endm} 한정 적용 — 버전 저장" if revert
                  else f"{eff}부터 적용 — 배합비 버전 저장")
        if st.button(_label, type="primary",
                     disabled=bool(brep["합계이상"]), key="bom_save"):
            snap = prev[["표준명칭", "ERP코드", "원료한글명", "배합률"]].copy()
            db.upsert_bom_version(eff, bdf, note or None)
            if revert:
                db.upsert_bom_version(revert, snap,
                                      f"{eff}~{endm} 한정 적용 종료 — 이전 배합 자동 복귀")
            st.cache_data.clear()
            if revert:
                st.success(f"{eff} ~ {endm} 한정 적용 저장 완료 — {len(prods)}개 제품. "
                           f"{revert}부터는 이전 배합으로 자동 복귀합니다.")
            else:
                st.success(f"{eff} 버전 저장 완료 — {len(prods)}개 제품. "
                           "파일에 없던 제품은 기존 배합 그대로 유지됩니다.")
            st.rerun()

    st.divider()
    st.subheader("등록된 버전")
    if len(vers):
        vshow = vers.copy()
        vshow["적용시작"] = vshow["적용시작"].map(
            lambda v: f"{v}  (기준버전)" if str(v) == C.BOM_BASE_YM else str(v))
        st.dataframe(vshow, width='stretch', hide_index=True)
        st.caption("기준버전은 그 이전 모든 달에 적용됩니다. "
                   "각 버전은 같은 제품의 다음 버전 직전까지 유효합니다.")

        vp = db.bom_version_products()
        with st.expander("제품별 버전 이력 · 배합률 합계 점검"):
            bad = vp[(vp["배합합%"] < 100 - C.BOM_SUM_TOL) | (vp["배합합%"] > 100 + C.BOM_SUM_TOL)]
            if len(bad):
                st.error(f"배합률 합계가 100%를 벗어난 버전 {len(bad)}건")
                st.dataframe(bad, width='stretch', hide_index=True)
            nver = vp.groupby("표준명칭")["적용시작"].nunique()
            multi = sorted(nver[nver > 1].index)
            if multi:
                st.markdown("**버전이 2개 이상인 제품**")
                st.dataframe(vp[vp["표준명칭"].isin(multi)], width='stretch', hide_index=True)
            else:
                st.caption("아직 버전이 나뉜 제품이 없습니다(전부 기준버전).")

        delv = [v for v in vers["적용시작"].astype(str) if v != C.BOM_BASE_YM]
        if delv:
            with st.expander("🗑️ 버전 삭제"):
                dv = st.selectbox("삭제할 버전", delv, key="bom_del_v")
                dp = st.multiselect("일부 제품만 삭제 (비우면 해당 버전 전체)",
                                    sorted(bom_all[bom_all["적용시작"].astype(str) == dv]["표준명칭"].unique()),
                                    key="bom_del_p")
                st.caption("삭제하면 그 달부터 다시 **이전 버전**이 적용됩니다. 기준버전은 지울 수 없습니다.")
                if st.button("삭제", key="bom_del_btn"):
                    db.delete_bom_version(dv, dp or None)
                    st.cache_data.clear()
                    st.success(f"{dv} 버전 삭제 완료.")
                    st.rerun()

    st.divider()
    st.subheader("두 달 배합 비교")
    allm = sorted(set(_pm) | (set(vers["적용시작"].astype(str)) - {C.BOM_BASE_YM}))
    if len(allm) >= 2:
        d1, d2 = st.columns(2)
        b1 = d1.selectbox("기준월", allm, index=max(0, len(allm) - 2), key="bomdiff_1")
        b2 = d2.selectbox("비교월", allm, index=len(allm) - 1, key="bomdiff_2")
        mm_ = db.load_material_master()
        nmap = dict(zip(mm_["ERP코드"].astype(str), mm_["대표원료명"]))
        ml_ = model.bom_long([b1, b2], bom_all)
        diff = upx.bom_diff(b1, b2, ml_, nmap)
        if len(diff) == 0:
            st.info(f"{b1} → {b2} 사이 배합비 변경이 없습니다.")
        else:
            st.dataframe(diff, width='stretch', hide_index=True, height=300)
            st.caption(f"{diff['표준명칭'].nunique()}개 제품 · {len(diff)}개 원료 변경. "
                       "금액 영향은 ‘사용단가 분석’ 페이지의 **배합효과**에서 확인하세요.")

    st.divider()
    st.download_button("📥 배합비 업로드 양식 (현재 배합 포함)", templates.bom_template(),
                       file_name="업로드양식_배합비.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("현재 배합이 채워진 채로 내려받아집니다. 바뀐 제품만 남기고 숫자를 고쳐 올리세요.")
