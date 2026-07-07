# -*- coding: utf-8 -*-
"""사용단가(원/kg) 분석.
전체/원료군 = DB 실적(금액÷사용량) 기준.  제품/브랜드 = BOM×계획중량 이론 단위원가.
Δ사용단가 = 단가효과 + 믹스효과 + 교호 (3요인 분해)."""
import pandas as pd
from . import db, model, dims


# ---------- 추이(월별 사용단가) ----------
def actual_up_series():
    """월별 실적 사용단가(원/kg) = 실적금액합 ÷ 실적사용kg합."""
    p = db.load_price().copy(); p["년월"] = p["년월"].astype(str)
    g = p.groupby("년월").agg(금액=("실적금액", "sum"), 사용kg=("실적사용kg", "sum"))
    g["사용단가"] = g["금액"] / g["사용kg"].replace(0, pd.NA)
    return g.reset_index()

def theo_up_series(cost):
    g = cost.copy(); g["년월"] = g["년월"].astype(str)
    g = g.groupby("년월").agg(금액=("이론금액", "sum"), 사용kg=("이론사용kg", "sum"))
    g["사용단가"] = g["금액"] / g["사용kg"].replace(0, pd.NA)
    return g.reset_index()


def _decomp(df, key, qcol, pcol, m1, m2):
    """공통 blended 분해. df[년월,key,qcol,pcol] → (총괄dict, 항목별df).
    사용단가 = Σ q·p / Σ q.  단가/믹스/교호 3요인."""
    d = df.copy(); d["년월"] = d["년월"].astype(str)
    a = d[d["년월"] == m1].set_index(key)
    b = d[d["년월"] == m2].set_index(key)
    keys = sorted(set(a.index) | set(b.index))
    q1 = a[qcol].reindex(keys).fillna(0.0); q2 = b[qcol].reindex(keys).fillna(0.0)
    p1 = a[pcol].reindex(keys); p2 = b[pcol].reindex(keys)
    p1 = p1.fillna(p2).fillna(0.0); p2 = p2.fillna(p1).fillna(0.0)  # 결측은 상대월 값
    Q1, Q2 = q1.sum(), q2.sum()
    w1 = q1 / Q1 if Q1 else q1 * 0
    w2 = q2 / Q2 if Q2 else q2 * 0
    P1 = float((w1 * p1).sum()); P2 = float((w2 * p2).sum())
    price_eff = w2 * (p2 - p1)             # 단가효과(당월 비중 가중)
    mix_eff = (w2 - w1) * (p1 - P1)        # 믹스효과(평균 대비 기여 → 저가 비중↑는 −)
    out = pd.DataFrame({key: keys, "단가_m1": p1.values, "단가_m2": p2.values,
                        "사용kg_m1": q1.values, "사용kg_m2": q2.values,
                        "비중_m1": w1.values, "비중_m2": w2.values,
                        "단가효과": price_eff.values, "믹스효과": mix_eff.values})
    summ = {"사용단가_m1": P1, "사용단가_m2": P2, "증감": P2 - P1,
            "단가효과": float(price_eff.sum()), "믹스효과": float(mix_eff.sum()),
            "교호효과": (P2 - P1) - float(price_eff.sum()) - float(mix_eff.sum())}  # ≈0
    return summ, out


def actual_material_decomp(m1, m2, name_map=None):
    """전체 사용단가 분해 (실적, 원료 단위)."""
    p = db.load_price().copy()
    p["원료코드"] = p["원료코드"].astype(str)
    df = p.rename(columns={"실적사용kg": "q", "단가": "p"})[["년월", "원료코드", "q", "p"]]
    summ, out = _decomp(df, "원료코드", "q", "p", m1, m2)
    if name_map:
        out["원료명"] = out["원료코드"].map(name_map)
    return summ, out


def group_table(m1, m2):
    """원료군별 사용단가·비중 (실적)."""
    p = db.load_price().copy(); p["년월"] = p["년월"].astype(str)
    p["원료군"] = p["원료코드"].astype(str).map(dims.material_group)
    rows = []
    for m in (m1, m2):
        s = p[p["년월"] == m].groupby("원료군").agg(
            금액=("실적금액", "sum"), 사용kg=("실적사용kg", "sum"))
        s["사용단가"] = s["금액"] / s["사용kg"].replace(0, pd.NA)
        s["월"] = m
        rows.append(s.reset_index())
    g = pd.concat(rows, ignore_index=True)
    piv = g.pivot(index="원료군", columns="월", values=["사용단가", "사용kg", "금액"]).fillna(0)
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv = piv.reset_index()
    tot1 = piv[f"사용kg_{m1}"].sum(); tot2 = piv[f"사용kg_{m2}"].sum()
    piv["비중_m1%"] = piv[f"사용kg_{m1}"] / tot1 * 100 if tot1 else 0
    piv["비중_m2%"] = piv[f"사용kg_{m2}"] / tot2 * 100 if tot2 else 0
    piv["단가증감"] = piv[f"사용단가_{m2}"] - piv[f"사용단가_{m1}"]
    return piv.sort_values(f"금액_{m2}", ascending=False)


# ---------- 제품/브랜드 (이론 단위원가) ----------
def product_unit_cost(cost, plan):
    """제품 단위원가 c_p(원/kg) = 제품 이론원료비 ÷ 생산kg (월별)."""
    c = cost.copy(); c["년월"] = c["년월"].astype(str)
    pc = c.groupby(["년월", "표준제품"])["이론금액"].sum().reset_index(name="원료비")
    pl = plan.copy(); pl["년월"] = pl["년월"].astype(str)
    m = pc.merge(pl, on=["년월", "표준제품"], how="left")
    m["단위원가"] = m["원료비"] / m["계획중량"].replace(0, pd.NA)
    return m


def product_decomp(cost, plan, m1, m2):
    """전체 사용단가(이론)를 제품 생산구성으로 분해.
    사용단가 = Σ(생산비중_p × 제품단위원가_p). 단가효과=제품원가변화, 믹스효과=생산구성변화."""
    uc = product_unit_cost(cost, plan)
    df = uc.rename(columns={"계획중량": "q", "단위원가": "p"})[["년월", "표준제품", "q", "p"]]
    return _decomp(df, "표준제품", "q", "p", m1, m2)


def brand_table(cost, plan, m1, m2):
    """브랜드별 사용단가(생산가중, 이론)."""
    uc = product_unit_cost(cost, plan)
    uc["브랜드"] = uc["표준제품"].map(dims.brand_of)
    rows = []
    for m in (m1, m2):
        s = uc[uc["년월"] == m].groupby("브랜드").agg(
            원료비=("원료비", "sum"), 생산kg=("계획중량", "sum"))
        s["사용단가"] = s["원료비"] / s["생산kg"].replace(0, pd.NA)
        s["월"] = m; rows.append(s.reset_index())
    g = pd.concat(rows, ignore_index=True)
    piv = g.pivot(index="브랜드", columns="월", values=["사용단가", "생산kg"]).fillna(0)
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv = piv.reset_index()
    piv["단가증감"] = piv[f"사용단가_{m2}"] - piv[f"사용단가_{m1}"]
    return piv.sort_values(f"생산kg_{m2}", ascending=False)
