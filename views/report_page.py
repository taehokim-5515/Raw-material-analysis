# -*- coding: utf-8 -*-
"""⑧ 통합 리포트 — HTML 미리보기·다운로드·메일 발송."""
import streamlit as st
import streamlit.components.v1 as components
from app_common import load_all, month_pickers
from core import report, db

st.title("📧 통합 리포트 (메일)")
st.caption("기준월↔비교월 실적 리뷰를 **메일용 HTML**로 만듭니다. "
           "메일은 정적 문서라 드릴다운(클릭 선택)은 불가 — 대신 아래에서 제품·원료를 "
           "미리 골라 스냅샷으로 넣고, 상세 탐색은 앱 링크로 안내합니다.")

D = load_all()
m1, m2 = month_pickers(D["months"], key="rep")

# ---- 스냅샷 선택 ----
c1, c2 = st.columns(2)
with c1:
    prods = sorted(D["plan"]["표준제품"].unique())
    sel_p = st.multiselect("리포트에 넣을 제품 스냅샷 (선택)", prods, max_selections=6)
with c2:
    codes = sorted(D["bom_codes"] | set(db.load_price()["원료코드"].astype(str)))
    label = {c: f"{D['name_map'].get(c, c)} ({c})" for c in codes}
    sel_m = st.multiselect("리포트에 넣을 원료 스냅샷 (선택)", codes,
                           format_func=lambda c: label[c], max_selections=6)
app_url = st.text_input("앱 링크 (선택 — 비우면 링크 없이 안내 문구만 표기)", "",
                        placeholder="예: http://170.170.123.131:8501 (앱을 상시 실행 중인 PC/서버 주소)",
                        help="앱이 켜져 있는 PC의 사내망 주소를 넣으면 리포트 하단에 클릭 가능한 링크로 들어갑니다. "
                             "상시 접속이 필요하면 사내 서버에 streamlit을 올려두는 걸 권장합니다.")

html = report.build_report_html(m1, m2, sel_p, sel_m, app_url)

# ---- 미리보기 / 다운로드 ----
st.subheader("미리보기")
components.html(html, height=1000, scrolling=True)
st.download_button("📥 HTML 파일 다운로드", html.encode("utf-8"),
                   file_name=f"원료비리포트_{m1}_vs_{m2}.html", mime="text/html")

# ---- 메일 발송 ----
st.divider()
st.subheader("메일 발송")
cfg = report.load_mail_cfg()
a, b, c = st.columns([2, 1, 1])
host = a.text_input("SMTP 서버", cfg.get("host", ""), placeholder="예: smtp.office365.com")
port = b.number_input("포트", 1, 65535, int(cfg.get("port", 587)))
tls = c.checkbox("STARTTLS", value=bool(cfg.get("tls", True)))
d, e = st.columns(2)
sender = d.text_input("보내는 주소", cfg.get("sender", "taehokim@harimpetfood.com"))
password = e.text_input("비밀번호(앱 비밀번호)", type="password",
                        help="저장되지 않습니다. 발송 시에만 사용.")
recipients = st.text_input("받는 주소 (콤마로 여러 명)", cfg.get("recipients", ""))
subject = st.text_input("제목", f"[원료비 리포트] {m1} → {m2} 실적 리뷰")

col1, col2 = st.columns([1, 3])
if col1.button("📨 발송", type="primary", disabled=not (host and sender and recipients)):
    try:
        sent = report.send_mail(dict(host=host, port=port, tls=tls, sender=sender,
                                     password=password, recipients=recipients),
                                subject, html)
        report.save_mail_cfg(dict(host=host, port=port, tls=tls, sender=sender,
                                  recipients=recipients))
        st.success(f"발송 완료: {', '.join(sent)} (서버·수신자 설정은 저장됨, 비밀번호는 저장 안 함)")
    except Exception as ex:
        st.error(f"발송 실패: {ex}")
col2.caption("사내 SMTP 정보(서버·포트)는 IT팀 안내 기준으로 입력하세요. "
             "Office365는 smtp.office365.com:587(STARTTLS)+앱 비밀번호가 일반적입니다.")
