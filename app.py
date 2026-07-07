# -*- coding: utf-8 -*-
"""라우터 — 페이지 이름·순서 정의 (데이터 관리는 맨 아래)."""
import streamlit as st

st.set_page_config(page_title="원료비 원인분석", page_icon="📊", layout="wide")

pg = st.navigation([
    st.Page("views/monthly.py", title="월 비교", icon="📊", default=True),
    st.Page("views/product.py", title="제품 드릴다운", icon="📦"),
    st.Page("views/material.py", title="원료 드릴다운", icon="🧪"),
    st.Page("views/watch.py", title="단가 감시", icon="🚨"),
    st.Page("views/usageprice.py", title="사용단가 분석", icon="⚖️"),
    st.Page("views/detail.py", title="원료 상세 (실적)", icon="📋"),
    st.Page("views/report_page.py", title="통합 리포트 (메일)", icon="📧"),
    st.Page("views/dataadmin.py", title="데이터 관리", icon="🗂️"),
])
pg.run()
