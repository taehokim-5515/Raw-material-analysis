# -*- coding: utf-8 -*-
"""라우터 + 접속 코드 게이트.
접속 코드별 권한: full(전체) / material(원료 드릴다운만).
Streamlit Cloud에선 Settings→Secrets 로 코드 변경 가능(코드 수정 불필요):
[access]
harimpetfood = "full"
cham = "material"
"""
import streamlit as st

st.set_page_config(page_title="원료비 원인분석", page_icon="📊", layout="wide")

# ---- 접속 코드 → 권한 (Cloud Secrets 있으면 우선) ----
ACCESS = {"harimpetfood": "full", "cham": "material"}
try:
    ACCESS = dict(st.secrets["access"])
except Exception:
    pass

if "role" not in st.session_state:
    st.session_state.role = None

# ---- 로그인 화면 ----
if st.session_state.role is None:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("## 🔐 원료비 원인분석")
        st.caption("접속 코드를 입력하세요.")
        pw = st.text_input("접속 코드", type="password", label_visibility="collapsed",
                           placeholder="접속 코드")
        if st.button("입장", type="primary", use_container_width=True):
            role = ACCESS.get(pw.strip())
            if role:
                st.session_state.role = role
                st.rerun()
            else:
                st.error("접속 코드가 올바르지 않습니다.")
    st.stop()

# ---- 권한별 페이지 구성 ----
P = {
    "monthly": st.Page("views/monthly.py", title="월 비교", icon="📊"),
    "product": st.Page("views/product.py", title="제품 드릴다운", icon="📦"),
    "material": st.Page("views/material.py", title="원료 드릴다운", icon="🧪"),
    "watch": st.Page("views/watch.py", title="단가 감시", icon="🚨"),
    "usageprice": st.Page("views/usageprice.py", title="사용단가 분석", icon="⚖️"),
    "forecast": st.Page("views/forecast.py", title="단위원가 전망", icon="📈"),
    "detail": st.Page("views/detail.py", title="원료 상세 (실적)", icon="📋"),
    "report": st.Page("views/report_page.py", title="통합 리포트 (메일)", icon="📧"),
    "data": st.Page("views/dataadmin.py", title="데이터 관리", icon="🗂️"),
}

if st.session_state.role == "material":
    # 월 비교는 요약판(제품별·원료별 증감 TOP + 계획지시 총량만) — views/monthly.py의 LIMITED 분기
    pages = [P["monthly"], P["material"]]
else:  # full
    pages = [P["monthly"], P["product"], P["material"], P["watch"],
             P["usageprice"], P["forecast"], P["detail"], P["report"], P["data"]]

with st.sidebar:
    if st.button("🔓 로그아웃", use_container_width=True):
        st.session_state.role = None
        st.rerun()

pg = st.navigation(pages)
pg.run()
