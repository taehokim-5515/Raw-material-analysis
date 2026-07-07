# -*- coding: utf-8 -*-
"""변동 분해: 단가/물량/믹스, 원료 사용량의 제품 귀속, BOM 대비 실적 수율."""
import pandas as pd
from . import db, model


def _pivot_two_months(df, key, val, m1, m2):
    sub = df[df["년월"].astype(str).isin([m1, m2])]
    p = sub.pivot_table(index=key, columns="년월", values=val, aggfunc="sum").fillna(0)
    for m in (m1, m2):
        if m not in p.columns:
            p[m] = 0.0
    return p


def material_bridge(cost, m1, m2, name_map=None):
    """원료별 금액 변동을 단가효과·물량효과로 2분할 (교호 없음, 정확 분해).
    Δ금액 = 단가효과(Δp·당월사용량 q2) + 물량효과(Δq·전월단가 p1)
    단가 p 는 DB 단가(코드·월별 상수). 이론사용량 기준."""
    q = _pivot_two_months(cost, "ERP코드", "이론사용kg", m1, m2)
    amt = _pivot_two_months(cost, "ERP코드", "이론금액", m1, m2)
    price = db.load_price().copy(); price["년월"] = price["년월"].astype(str)
    pm = {m: dict(zip(price[price["년월"] == m]["원료코드"], price[price["년월"] == m]["단가"]))
          for m in (m1, m2)}
    r = pd.DataFrame(index=q.index)
    r["사용kg_m1"], r["사용kg_m2"] = q[m1], q[m2]
    r["금액_m1"], r["금액_m2"] = amt[m1], amt[m2]
    p1 = pd.Series({c: pm[m1].get(c, 0) for c in q.index})
    p2 = pd.Series({c: pm[m2].get(c, 0) for c in q.index})
    r["단가_m1"], r["단가_m2"] = p1, p2
    r["금액증감"] = r["금액_m2"] - r["금액_m1"]
    r["단가효과"] = q[m2] * (p2 - p1)              # 당월 사용량 가중
    r["물량효과"] = (q[m2] - q[m1]) * p1           # 전월 단가 가중
    r["교호효과"] = r["금액증감"] - r["단가효과"] - r["물량효과"]  # ≈0
    r = r.reset_index()
    if name_map:
        r["원료명"] = r["ERP코드"].map(name_map)
    return r.sort_values("금액_m2", ascending=False)


def total_bridge(cost, m1, m2):
    """총 원료비 변동 요약(단가/물량/교호 합)."""
    b = material_bridge(cost, m1, m2)
    return {
        "총_m1": b["금액_m1"].sum(), "총_m2": b["금액_m2"].sum(),
        "증감": b["금액증감"].sum(),
        "단가효과": b["단가효과"].sum(), "물량효과": b["물량효과"].sum(),
        "교호효과": b["교호효과"].sum(),
    }


def product_bridge(cost, m1, m2):
    """제품별 원료비 변동."""
    a = _pivot_two_months(cost, "표준제품", "이론금액", m1, m2).reset_index()
    a = a.rename(columns={m1: "금액_m1", m2: "금액_m2"})
    a["금액증감"] = a["금액_m2"] - a["금액_m1"]
    return a.sort_values("금액증감", ascending=False)


def volume_mix_split(plan, cost, m1, m2, bom_x=None):
    """물량효과(Δ사용량×전월단가)를 총생산량효과(scale) + 제품믹스효과(mix)로 분해.
    제품 1kg 원가 u_p = Σ(BOM배합률×전월단가)로 계산 → 신규 제품(당월만 생산)도 정상 반영.
    Σ(총생산량+믹스) = 물량효과 를 보장."""
    plan = plan.copy(); plan["년월"] = plan["년월"].astype(str)
    w1 = plan[plan["년월"] == m1].set_index("표준제품")["계획중량"]
    w2 = plan[plan["년월"] == m2].set_index("표준제품")["계획중량"]
    W1, W2 = w1.sum(), w2.sum()
    scale = W2 / W1 if W1 else 1.0
    if bom_x is None:
        bom_x = model.explode_bom()
    price = db.load_price().copy(); price["년월"] = price["년월"].astype(str)
    p1map = dict(zip(price[price["년월"] == m1]["원료코드"].astype(str),
                     price[price["년월"] == m1]["단가"]))
    bx = bom_x.copy(); bx["ERP코드"] = bx["ERP코드"].astype(str)
    bx["u"] = bx["배합률"] / 100.0 * bx["ERP코드"].map(p1map).fillna(0)
    u1 = bx.groupby("표준명칭")["u"].sum()   # 제품 1kg 원가(전월 단가)
    prods = sorted(set(w1.index) | set(w2.index) | set(u1.index))
    rows = []
    for p in prods:
        u = float(u1.get(p, 0.0))
        Wp1 = float(w1.get(p, 0.0)); Wp2 = float(w2.get(p, 0.0))
        scale_eff = Wp1 * u * (scale - 1)                  # 균등 성장분
        mix_eff = (Wp2 - Wp1 * scale) * u                  # 구성 변화분
        rows.append((p, scale_eff, mix_eff))
    df = pd.DataFrame(rows, columns=["표준제품", "총생산량효과", "믹스효과"])
    return df, {"총생산량효과": df["총생산량효과"].sum(), "믹스효과": df["믹스효과"].sum(),
                "생산kg_m1": W1, "생산kg_m2": W2, "성장률": scale - 1}


def material_product_attribution(usage, code, m1, m2):
    """⭐ 특정 원료의 사용량 변화를 '제품 생산변동'으로 귀속.
    Δ사용량(code) = Σ제품[ Δ생산중량 × 배합률(제품,code) ]
    반환: DataFrame[표준제품, 사용kg_m1, 사용kg_m2, 사용kg증감] 정렬"""
    u = usage[usage["ERP코드"] == code].copy(); u["년월"] = u["년월"].astype(str)
    p = u.pivot_table(index="표준제품", columns="년월", values="이론사용kg", aggfunc="sum").fillna(0)
    for m in (m1, m2):
        if m not in p.columns: p[m] = 0.0
    p = p.rename(columns={m1: "사용kg_m1", m2: "사용kg_m2"}).reset_index()
    p["사용kg증감"] = p["사용kg_m2"] - p["사용kg_m1"]
    return p.sort_values("사용kg증감", key=lambda s: s.abs(), ascending=False)


def price_watch(m1, m2, name_map=None):
    """단가 감시 — BOM이 아닌 DB 실적(단가·실적사용량) 기준.
    단가효과 = 단가변동 × 당월(비교월) 실적사용량. (실제 소비 기준 금액 파장)"""
    p = db.load_price().copy(); p["년월"] = p["년월"].astype(str)
    p["원료코드"] = p["원료코드"].astype(str)
    a = p[p["년월"] == m1].set_index("원료코드")
    b = p[p["년월"] == m2].set_index("원료코드")
    codes = sorted(set(a.index) | set(b.index))
    rows = []
    for c in codes:
        p1 = float(a["단가"].get(c, 0)); p2 = float(b["단가"].get(c, 0))
        q1 = float(a["실적사용kg"].get(c, 0)); q2 = float(b["실적사용kg"].get(c, 0))
        a1 = float(a["실적금액"].get(c, 0)); a2 = float(b["실적금액"].get(c, 0))
        nm = a["원료명"].get(c) if c in a.index else b["원료명"].get(c, c)
        chg = (p2 / p1 - 1) * 100 if p1 else (0 if p2 == 0 else float("inf"))
        rows.append({
            "원료코드": c, "원료명": nm,
            "단가_m1": p1, "단가_m2": p2, "단가변동%": chg,
            "실적사용kg_m1": q1, "실적사용kg_m2": q2,
            "실적금액_m1": a1, "실적금액_m2": a2, "금액증감": a2 - a1,
            "단가효과": q2 * (p2 - p1),  # 당월 사용량 가중(= 실제 소비 기준 파장)
        })
    df = pd.DataFrame(rows)
    df = df[(df["실적사용kg_m1"] > 0) | (df["실적사용kg_m2"] > 0)]  # 미사용 원료 제외
    return df.sort_values("단가효과", key=lambda s: s.abs(), ascending=False)


def actual_material_detail(m1, m2, name_map=None, bom_codes=None):
    """원료 상세 (실적·전사) — 기존 'Material cost impact analysis' 방식 그대로.
    금액변동 = 단가영향(단가변동×당월사용량) + 사용량영향(사용량변동×전월단가)  [교호 없음, 2분할]"""
    from . import dims
    p = db.load_price().copy(); p["년월"] = p["년월"].astype(str)
    p["원료코드"] = p["원료코드"].astype(str)
    a = p[p["년월"] == m1].set_index("원료코드")
    b = p[p["년월"] == m2].set_index("원료코드")
    codes = sorted(set(a.index) | set(b.index))
    if bom_codes is None:
        bom_codes = set()
    rows = []
    for c in codes:
        p1 = float(a["단가"].get(c, 0)); p2 = float(b["단가"].get(c, 0))
        q1 = float(a["실적사용kg"].get(c, 0)); q2 = float(b["실적사용kg"].get(c, 0))
        amt1 = float(a["실적금액"].get(c, 0)); amt2 = float(b["실적금액"].get(c, 0))
        nm = a["원료명"].get(c) if c in a.index else b["원료명"].get(c, c)
        rows.append({
            "원료코드": c, "원료명": nm, "원료군": dims.material_group(c),
            "BOM포함": "예" if c in bom_codes else "아니오",
            "전월단가": p1, "당월단가": p2, "단가변동": p2 - p1,
            "단가변동률%": (p2 / p1 - 1) * 100 if p1 else 0.0,
            "전월사용kg": q1, "당월사용kg": q2, "사용량변동kg": q2 - q1,
            "사용량변동률%": (q2 / q1 - 1) * 100 if q1 else (0.0 if q2 == 0 else float("inf")),
            "전월금액": amt1, "당월금액": amt2, "금액변동": amt2 - amt1,
            "단가영향": (p2 - p1) * q2,        # 당월 사용량 가중
            "사용량영향": (q2 - q1) * p1,       # 전월 단가 가중
        })
    df = pd.DataFrame(rows)
    if name_map:  # DB 원료명 없을 때 보완
        df["원료명"] = df.apply(lambda r: r["원료명"] if pd.notna(r["원료명"]) and r["원료명"] else name_map.get(r["원료코드"], r["원료코드"]), axis=1)
    return df.sort_values("금액변동", ascending=False)


def actual_vs_theo_recon(cost, m1, m2, bom_codes):
    """실적(전사) vs 이론(BOM 60제품) 총액 대사 + 범위밖(BOM없는) 실적 소비."""
    p = db.load_price().copy(); p["년월"] = p["년월"].astype(str)
    p["원료코드"] = p["원료코드"].astype(str)
    act = p.groupby("년월")["실적금액"].sum()
    c = cost.copy(); c["년월"] = c["년월"].astype(str)
    theo = c.groupby("년월")["이론금액"].sum()
    out = p[~p["원료코드"].isin(bom_codes)]
    out_amt = out.groupby("년월")["실적금액"].sum()
    return {
        "실적_m1": float(act.get(m1, 0)), "실적_m2": float(act.get(m2, 0)),
        "이론_m1": float(theo.get(m1, 0)), "이론_m2": float(theo.get(m2, 0)),
        "범위밖_m1": float(out_amt.get(m1, 0)), "범위밖_m2": float(out_amt.get(m2, 0)),
        "범위밖_종수": int(out[(out["년월"].isin([m1, m2])) & (out["실적금액"] > 0)]["원료코드"].nunique()),
    }


def yield_gap(cost, m1, m2):
    """BOM 이론 vs DB 실적 대사(원료 사용량·금액). 수율/로스 gap."""
    theo = model.by_material(cost)
    theo["년월"] = theo["년월"].astype(str)
    act = db.load_price(); act["년월"] = act["년월"].astype(str)
    act = act.rename(columns={"원료코드": "ERP코드"})
    rows = []
    for m in (m1, m2):
        t = theo[theo["년월"] == m]
        a = act[act["년월"] == m]
        rows.append({
            "년월": m,
            "이론사용kg": t["이론사용kg"].sum(), "실적사용kg": a["실적사용kg"].sum(),
            "이론금액": t["이론금액"].sum(), "실적금액": a["실적금액"].sum(),
        })
    r = pd.DataFrame(rows)
    r["사용량gap%"] = (r["이론사용kg"] / r["실적사용kg"] - 1) * 100
    r["금액gap%"] = (r["이론금액"] / r["실적금액"] - 1) * 100
    return r
