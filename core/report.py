# -*- coding: utf-8 -*-
"""통합 리포트 — 메일용 정적 HTML 생성 + SMTP 발송.
메일 클라이언트는 JS 차단 → 인라인 CSS·테이블만 사용(아웃룩 호환)."""
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from . import db, model, decompose as dc, dims, config as C

RED, BLUE, GRAY, BG = "#D85A30", "#378ADD", "#5F5E5A", "#F7F6F3"
MAIL_CFG = C.DATA / "mail_config.json"


def _w(v):  # 정확 금액
    return f"{v:,.0f}"

def _sw(v):
    return ("+" if v >= 0 else "−") + f"{abs(v):,.0f}"

def _color(v):
    return RED if v >= 0 else BLUE

TD = 'padding:6px 10px;border-bottom:1px solid #E8E6E0;font-size:13px;'
TH = ('padding:7px 10px;background:#EFEDE7;font-size:12px;color:#5F5E5A;'
      'text-align:left;border-bottom:2px solid #D3D1C7;')

def _table(headers, rows, aligns=None):
    aligns = aligns or ["left"] * len(headers)
    h = "".join(f'<th style="{TH}text-align:{a};">{x}</th>' for x, a in zip(headers, aligns))
    body = ""
    for r in rows:
        tds = "".join(f'<td style="{TD}text-align:{a};">{x}</td>' for x, a in zip(r, aligns))
        body += f"<tr>{tds}</tr>"
    return (f'<table style="border-collapse:collapse;width:100%;margin:6px 0 18px 0;">'
            f"<tr>{h}</tr>{body}</table>")

def _h2(t):
    return (f'<h2 style="font-size:16px;margin:26px 0 4px 0;color:#2C2C2A;'
            f'border-left:4px solid {RED};padding-left:8px;">{t}</h2>')

def _note(t):
    return f'<p style="font-size:12px;color:#888780;margin:0 0 6px 0;">{t}</p>'

def _bar_row(label, value, vmax, color, label2=""):
    wpct = 0 if vmax == 0 else min(abs(value) / vmax * 100, 100)
    return (
        f'<tr><td style="padding:4px 8px;font-size:13px;white-space:nowrap;">{label}</td>'
        f'<td style="padding:4px 8px;width:55%;"><div style="background:{color};height:16px;'
        f'width:{max(wpct,1):.0f}%;border-radius:3px;"></div></td>'
        f'<td style="padding:4px 8px;font-size:13px;text-align:right;white-space:nowrap;">{label2}</td></tr>')


def build_report_html(m1, m2, sel_products=None, sel_materials=None, app_url=""):
    sel_products = sel_products or []
    sel_materials = sel_materials or []
    bom_codes = model.bom_material_codes()
    det = dc.actual_material_detail(m1, m2, None, bom_codes)
    tot1, tot2 = det["전월금액"].sum(), det["당월금액"].sum()
    chg = tot2 - tot1
    u1, u2 = det["전월사용kg"].sum(), det["당월사용kg"].sum()
    price_imp, vol_imp = det["단가영향"].sum(), det["사용량영향"].sum()

    # ---------- 요약 KPI ----------
    kpi = f"""
    <table style="border-collapse:collapse;width:100%;margin:10px 0 6px 0;">
      <tr>
        <td style="background:{BG};border-radius:8px;padding:12px 14px;width:25%;">
          <div style="font-size:12px;color:{GRAY};">{m1} 실적 원료비</div>
          <div style="font-size:19px;font-weight:bold;color:#2C2C2A;">{_w(tot1)}원</div></td>
        <td style="width:8px;"></td>
        <td style="background:{BG};border-radius:8px;padding:12px 14px;width:25%;">
          <div style="font-size:12px;color:{GRAY};">{m2} 실적 원료비</div>
          <div style="font-size:19px;font-weight:bold;color:#2C2C2A;">{_w(tot2)}원</div></td>
        <td style="width:8px;"></td>
        <td style="background:{BG};border-radius:8px;padding:12px 14px;width:25%;">
          <div style="font-size:12px;color:{GRAY};">증감액</div>
          <div style="font-size:19px;font-weight:bold;color:{_color(chg)};">{_sw(chg)}원
          <span style="font-size:12px;">({(tot2/tot1-1)*100:+.1f}%)</span></div></td>
        <td style="width:8px;"></td>
        <td style="background:{BG};border-radius:8px;padding:12px 14px;">
          <div style="font-size:12px;color:{GRAY};">원료 사용량</div>
          <div style="font-size:19px;font-weight:bold;color:#2C2C2A;">{_w(u1)} → {_w(u2)}kg
          <span style="font-size:12px;color:{_color(u2-u1)};">({(u2/u1-1)*100:+.1f}%)</span></div></td>
      </tr></table>
    {_note("설비 실적(DB) 전 원료 기준 — ERP 실제 지출과 동일.")}"""

    # ---------- 워터폴 ----------
    vmax = max(abs(tot1), abs(tot2))
    wf = ('<table style="border-collapse:collapse;width:100%;margin:4px 0 8px 0;">'
          + _bar_row(f"{m1} 원료비", tot1, vmax, "#B4B2A9", _w(tot1) + "원")
          + _bar_row("단가영향", price_imp, vmax, _color(price_imp), _sw(price_imp) + "원")
          + _bar_row("사용량영향", vol_imp, vmax, _color(vol_imp), _sw(vol_imp) + "원")
          + _bar_row(f"{m2} 원료비", tot2, vmax, "#B4B2A9", _w(tot2) + "원")
          + "</table>"
          + _note("단가영향 = Σ(단가변동 × 당월사용량) · 사용량영향 = Σ(사용량변동 × 전월단가). 두 항목 합 = 증감액."))
    # 세부 기여 TOP5
    p5 = det.reindex(det["단가영향"].abs().sort_values(ascending=False).index).head(5)
    v5 = det.reindex(det["사용량영향"].abs().sort_values(ascending=False).index).head(5)
    wf += '<div style="font-size:13px;font-weight:bold;margin-top:8px;">단가영향 세부 TOP5</div>'
    wf += _table(["원료", "단가(원/kg)", "단가영향(원)"],
                 [[r["원료명"], f"{r['전월단가']:,.0f} → {r['당월단가']:,.0f}",
                   f'<span style="color:{_color(r["단가영향"])};">{_sw(r["단가영향"])}</span>'] for _, r in p5.iterrows()],
                 ["left", "right", "right"])
    wf += '<div style="font-size:13px;font-weight:bold;">사용량영향 세부 TOP5</div>'
    wf += _table(["원료", "사용량(kg)", "사용량영향(원)"],
                 [[r["원료명"], f"{r['전월사용kg']:,.0f} → {r['당월사용kg']:,.0f}",
                   f'<span style="color:{_color(r["사용량영향"])};">{_sw(r["사용량영향"])}</span>'] for _, r in v5.iterrows()],
                 ["left", "right", "right"])

    # ---------- 계획중량 그룹 (비중차 포함) ----------
    plan = db.load_plan().copy(); plan["년월"] = plan["년월"].astype(str)
    pw = plan[plan["년월"].isin([m1, m2])].copy()
    pw["그룹"] = pw["표준제품"].map(dims.plan_group)
    order = ["더리얼 도그", "더리얼 캣", "밥이보약 도그", "밥이보약 캣", "OEM"]
    gp = pw.pivot_table(index="그룹", columns="년월", values="계획중량",
                        aggfunc="sum", fill_value=0).reindex(order).fillna(0)
    for mm in (m1, m2):
        if mm not in gp.columns:
            gp[mm] = 0
    t1s, t2s = gp[m1].sum(), gp[m2].sum()
    grows = []
    for g in order:
        a = gp.loc[g, m1] / t1s * 100 if t1s else 0
        b = gp.loc[g, m2] / t2s * 100 if t2s else 0
        grows.append([g, f"{gp.loc[g, m1]/1000:,.1f}", f"{gp.loc[g, m2]/1000:,.1f}",
                      f"{a:.1f}%", f"{b:.1f}%",
                      f'<span style="color:{_color(b-a)};">{b-a:+.1f}</span>'])
    grows.append([f"<b>합계</b>", f"<b>{t1s/1000:,.1f}</b>", f"<b>{t2s/1000:,.1f}</b>",
                  "100%", "100%", ""])
    grp = _table(["그룹", f"{m1}(톤)", f"{m2}(톤)", f"{m1} 비중", f"{m2} 비중", "비중차(pp)"],
                 grows, ["left", "right", "right", "right", "right", "right"])
    grp += _note("비중차(pp) = 당월 비중 − 전월 비중. +면 그 그룹으로 생산이 쏠린 것 → 사용단가·원료 구성 변화의 배경.")

    # ---------- 생산 TOP10 변화율 ----------
    w = pw.pivot_table(index="표준제품", columns="년월", values="계획중량",
                       aggfunc="sum", fill_value=0)
    for mm in (m1, m2):
        if mm not in w.columns:
            w[mm] = 0
    w = w.sort_values(m2, ascending=False).head(10)
    trows = []
    for pname, r in w.iterrows():
        rate = ("신규" if r[m1] == 0 else
                f'<span style="color:{_color(r[m2]-r[m1])};">{(r[m2]/r[m1]-1)*100:+.1f}%</span>')
        trows.append([pname, f"{r[m1]:,.0f}", f"{r[m2]:,.0f}", rate])
    top10 = _table(["제품", f"{m1}(kg)", f"{m2}(kg)", "변화율"],
                   trows, ["left", "right", "right", "right"])

    # ---------- 단가 감시 주요 ----------
    watch = dc.price_watch(m1, m2)
    flag = watch[(watch["단가변동%"].abs() >= 1) & (watch["단가변동%"] != float("inf"))]
    flag = flag.reindex(flag["단가효과"].abs().sort_values(ascending=False).index).head(8)
    wrows = [[r["원료명"], f"{r['단가_m1']:,.0f} → {r['단가_m2']:,.0f}",
              f'{r["단가변동%"]:+.1f}%', f"{r['실적사용kg_m2']:,.0f}",
              f'<span style="color:{_color(r["단가효과"])};">{_sw(r["단가효과"])}</span>']
             for _, r in flag.iterrows()]
    watch_html = _table(["원료", "단가(원/kg)", "변동률", "당월사용(kg)", "단가효과(원)"],
                        wrows, ["left", "right", "right", "right", "right"]) if wrows else \
        _note("±1% 이상 단가 변동 원료가 없습니다.")

    # ---------- 원료 상세 TOP10 + 합계 대사 ----------
    dtop = det.reindex(det["금액변동"].abs().sort_values(ascending=False).index).head(10)
    drows = [[r["원료명"], f"{r['전월금액']:,.0f}", f"{r['당월금액']:,.0f}",
              f'<span style="color:{_color(r["금액변동"])};">{_sw(r["금액변동"])}</span>',
              _sw(r["단가영향"]), _sw(r["사용량영향"])] for _, r in dtop.iterrows()]
    drows.append(["<b>전체 합계 (전 원료)</b>", f"<b>{_w(tot1)}</b>", f"<b>{_w(tot2)}</b>",
                  f"<b>{_sw(chg)}</b>", f"<b>{_sw(price_imp)}</b>", f"<b>{_sw(vol_imp)}</b>"])
    detail_html = _table(["원료", f"{m1} 금액", f"{m2} 금액", "금액변동", "단가영향", "사용량영향"],
                         drows, ["left", "right", "right", "right", "right", "right"])
    detail_html += _note("합계 행: 금액변동 = 단가영향 + 사용량영향 이 정확히 일치(전 원료 기준 대사 완료).")

    # ---------- 선택 스냅샷 (제품/원료) ----------
    snap = ""
    if sel_products:
        cost = model.cost_table(); cost["년월"] = cost["년월"].astype(str)
        pc = cost.groupby(["년월", "표준제품"])["이론금액"].sum().reset_index()
        rows = []
        for pname in sel_products:
            a = pc[(pc["년월"] == m1) & (pc["표준제품"] == pname)]["이론금액"].sum()
            b = pc[(pc["년월"] == m2) & (pc["표준제품"] == pname)]["이론금액"].sum()
            wa = plan[(plan["년월"] == m1) & (plan["표준제품"] == pname)]["계획중량"].sum()
            wb = plan[(plan["년월"] == m2) & (plan["표준제품"] == pname)]["계획중량"].sum()
            ua = a / wa if wa else 0; ub = b / wb if wb else 0
            rows.append([pname, f"{wa:,.0f} → {wb:,.0f}", f"{_w(a)} → {_w(b)}",
                         f"{ua:,.0f} → {ub:,.0f}"])
        snap += _h2("선택 제품 스냅샷 (이론: 계획중량×BOM×단가)")
        snap += _table(["제품", "생산(kg)", "원료비(원)", "단위원가(원/kg)"],
                       rows, ["left", "right", "right", "right"])
    if sel_materials:
        sub = det[det["원료코드"].isin(sel_materials)]
        rows = [[r["원료명"], f"{r['전월단가']:,.0f} → {r['당월단가']:,.0f}",
                 f"{r['전월사용kg']:,.0f} → {r['당월사용kg']:,.0f}",
                 f'<span style="color:{_color(r["금액변동"])};">{_sw(r["금액변동"])}</span>',
                 _sw(r["단가영향"]), _sw(r["사용량영향"])] for _, r in sub.iterrows()]
        snap += _h2("선택 원료 스냅샷 (실적)")
        snap += _table(["원료", "단가(원/kg)", "사용량(kg)", "금액변동", "단가영향", "사용량영향"],
                       rows, ["left", "right", "right", "right", "right", "right"])

    link = (f'<p style="font-size:12px;color:{GRAY};">제품 및 원료별 세부 내역은 '
            f'<a href="{app_url}" style="color:{BLUE};">원료비 원인분석 앱</a>의 '
            f'드릴다운 페이지에서 확인하실 수 있습니다. (사내망, 앱 실행 중일 때 접속 가능)</p>') if app_url else \
        _note("제품 및 원료별 세부 내역은 ‘원료비 원인분석’ 앱의 드릴다운 페이지에서 확인하실 수 있습니다.")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#FFFFFF;">
<div style="max-width:820px;margin:0 auto;padding:24px 20px;
     font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#2C2C2A;">
  <div style="border-bottom:3px solid {RED};padding-bottom:10px;">
    <div style="font-size:20px;font-weight:bold;">원료비 통합 리포트</div>
    <div style="font-size:13px;color:{GRAY};margin-top:2px;">
      기준월 <b>{m1}</b> → 비교월 <b>{m2}</b> · 실적(설비 DB) 기준</div>
  </div>
  {kpi}
  {_h2("1. 원료비 증감 분해 (워터폴)")}{wf}
  {_h2("2. 제품별 계획지시 총량 — 그룹 비중")}{grp}
  {_h2("3. 생산 상위 10개 제품 — 계획중량 변화율")}{top10}
  {_h2("4. 단가 감시 — 주요 변동 (±1% 이상, 영향도순)")}{watch_html}
  {_h2("5. 원료 상세 — 금액변동 TOP10 + 전체 대사")}{detail_html}
  {snap}
  <div style="border-top:1px solid #D3D1C7;margin-top:24px;padding-top:10px;">{link}</div>
</div></body></html>"""


# ---------- 메일 ----------
def load_mail_cfg():
    if MAIL_CFG.exists():
        return json.loads(MAIL_CFG.read_text(encoding="utf-8"))
    return {"host": "", "port": 587, "tls": True, "sender": "", "recipients": ""}

def save_mail_cfg(cfg):
    safe = {k: v for k, v in cfg.items() if k != "password"}
    MAIL_CFG.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")

def send_mail(cfg, subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    recips = [r.strip() for r in str(cfg["recipients"]).replace(";", ",").split(",") if r.strip()]
    msg["To"] = ", ".join(recips)
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=30) as s:
        if cfg.get("tls", True):
            s.starttls()
        if cfg.get("password"):
            s.login(cfg["sender"], cfg["password"])
        s.sendmail(cfg["sender"], recips, msg.as_string())
    return recips
