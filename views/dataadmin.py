# -*- coding: utf-8 -*-
"""⑤ 데이터 관리 — 통합파일 자동 월분리 업로드 + 표준 양식 다운로드."""
import streamlit as st
import pandas as pd
from core import db, ingest, templates

st.title("🗂️ 데이터 관리 — 월 마감")
st.caption("① 관리자 계획중량(작업일자로 월 자동분리) → ② 원료 단가·사용량(년월로 월 자동분리) → 분석")

tab1, tab2, tab3, tab4 = st.tabs(
    ["① 관리자 계획중량", "② 단가·사용량", "③ 업로드 양식", "DB 미리보기"])

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
