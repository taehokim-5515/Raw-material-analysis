# -*- coding: utf-8 -*-
"""사용단가(원/kg) 분석.
전체/원료군 = DB 실적(금액÷사용량) 기준.  제품/브랜드 = BOM×계획중량 이론 단위원가.
Δ사용단가 = 단가효과 + 믹스효과 + 교호 (3요인 분해)."""
import numpy as np
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


# ---------- 예상단가 기반 단위원가 전망 (BOM 고정 → 순수 단가 효과) ----------
def forecast_uc_series(product, bom_x=None, fp=None):
    """제품 단위원가(원/kg) 월별 전망 = Σ(배합률/100 × 예상단가).
    반환: (DataFrame[년월, 단위원가, 단가커버율%], 제품 BOM DataFrame)"""
    from . import model as _model, db as _db
    if bom_x is None:
        bom_x = _model.explode_bom()
    if fp is None:
        fp = _db.load_forecast()
    fp = fp.copy(); fp["년월"] = fp["년월"].astype(str)
    fp["원료코드"] = fp["원료코드"].astype(str)
    sub = bom_x[bom_x["표준명칭"] == product][["ERP코드", "배합률"]].copy()
    sub["ERP코드"] = sub["ERP코드"].astype(str)
    rows = []
    for ym, g in fp.groupby("년월"):
        pm = dict(zip(g["원료코드"], g["단가"]))
        m = sub.copy(); m["p"] = m["ERP코드"].map(pm)
        cov = m.loc[m["p"].notna() & (m["p"] > 0), "배합률"].sum()
        uc = float((m["배합률"] / 100.0 * m["p"].fillna(0)).sum())
        rows.append((ym, uc, cov))
    out = pd.DataFrame(rows, columns=["년월", "단위원가", "단가커버율%"]).sort_values("년월")
    return out.reset_index(drop=True), sub


def forecast_uc_bridge(product, m1, m2, bom_x=None, fp=None, name_map=None):
    """두 달 사이 단위원가 변화의 원료별 기여 (정확 분해, BOM 고정).
    기여(원/kg) = 배합률/100 × (단가m2 − 단가m1).  Σ기여 = Δ단위원가."""
    from . import model as _model, db as _db
    if bom_x is None:
        bom_x = _model.explode_bom()
    if fp is None:
        fp = _db.load_forecast()
    fp = fp.copy(); fp["년월"] = fp["년월"].astype(str)
    fp["원료코드"] = fp["원료코드"].astype(str)
    p1 = dict(zip(fp[fp["년월"] == m1]["원료코드"], fp[fp["년월"] == m1]["단가"]))
    p2 = dict(zip(fp[fp["년월"] == m2]["원료코드"], fp[fp["년월"] == m2]["단가"]))
    nm = dict(zip(fp["원료코드"], fp["원료명"]))
    sub = bom_x[bom_x["표준명칭"] == product][["ERP코드", "배합률"]].copy()
    sub["ERP코드"] = sub["ERP코드"].astype(str)
    rows = []
    for _, r in sub.iterrows():
        c = r["ERP코드"]; w = r["배합률"]
        a, b = float(p1.get(c, 0)), float(p2.get(c, 0))
        rows.append({
            "원료코드": c,
            "원료명": nm.get(c) or (name_map.get(c, c) if name_map else c),
            "배합률%": w, "단가_m1": a, "단가_m2": b, "단가변동": b - a,
            "기여(원/kg)": w / 100.0 * (b - a),
        })
    df = pd.DataFrame(rows)
    return df.sort_values("기여(원/kg)", key=lambda s: s.abs(), ascending=False)


# ---------- 단위원가 통계 (수준·추세·변동 분리) ----------
def forecast_split_month():
    """실적 단가가 있는 마지막 월 = 실적구간/전망구간 경계."""
    p = db.load_price()
    if p.empty:
        return None
    return sorted(p["년월"].astype(str).unique())[-1]


def uc_stats(ucf):
    """단위원가 시계열 요약. ucf: DataFrame[년월, 단위원가]
    CV는 추세를 함께 재므로 '추세제거CV'를 순수 변동성 지표로 사용."""
    v = np.asarray(ucf["단위원가"], dtype=float)
    n = len(v)
    out = {"n": n, "평균": float(v.mean()) if n else 0.0,
           "최소": float(v.min()) if n else 0.0, "최대": float(v.max()) if n else 0.0,
           "표준편차": 0.0, "CV": 0.0, "추세제거CV": 0.0,
           "월평균추세": 0.0, "월평균추세%": 0.0, "기간변화율": 0.0}
    if n >= 2:
        sd = float(v.std(ddof=1)); mu = out["평균"]
        out["표준편차"] = sd
        out["CV"] = sd / mu * 100 if mu else 0.0
        out["기간변화율"] = (v[-1] / v[0] - 1) * 100 if v[0] else 0.0
        t = np.arange(n)
        b, a = np.polyfit(t, v, 1)
        out["월평균추세"] = float(b)
        out["월평균추세%"] = float(b) / mu * 100 if mu else 0.0
        if n >= 3:
            resid = v - (a + b * t)
            out["추세제거CV"] = float(resid.std(ddof=1)) / mu * 100 if mu else 0.0
    out["레인지%"] = (out["최대"] - out["최소"]) / out["평균"] * 100 if out["평균"] else 0.0
    return out


def uc_risk_contribution(product, months=None, bom_x=None, fp=None, name_map=None):
    """원료별 '단위원가 변동' 기여도 분해.
    RC_i = (배합률/100) × Cov(단가_i, 단위원가) / σ(단위원가);  Σ RC_i = σ(단위원가) 정확.
    배합률이 커도 단가가 안 움직이면 기여 0, 배합률이 작아도 단가가 요동치면 기여가 큼."""
    if bom_x is None:
        bom_x = model.explode_bom()
    if fp is None:
        fp = db.load_forecast()
    f = fp.copy()
    f["년월"] = f["년월"].astype(str); f["원료코드"] = f["원료코드"].astype(str)
    if months:
        f = f[f["년월"].isin(list(months))]
    sub = bom_x[bom_x["표준명칭"] == product][["ERP코드", "배합률"]].copy()
    sub["ERP코드"] = sub["ERP코드"].astype(str)
    piv = f.pivot_table(index="년월", columns="원료코드", values="단가", aggfunc="max").sort_index()
    codes = [c for c in sub["ERP코드"] if c in piv.columns]
    if len(piv) < 3 or not codes:
        return pd.DataFrame(columns=["원료코드", "원료명", "배합률%", "단가σ", "기여", "기여비중%"]), 0.0
    W = dict(zip(sub["ERP코드"], sub["배합률"]))
    M = piv[codes].astype(float).fillna(0.0)
    uc = sum(M[c] * W[c] / 100.0 for c in codes)
    sigma = float(uc.std(ddof=1))
    nm = dict(zip(f["원료코드"], f["원료명"]))
    rows = []
    for c in codes:
        cov = float(np.cov(M[c].values, uc.values, ddof=1)[0, 1])
        rc = (W[c] / 100.0) * cov / sigma if sigma else 0.0
        rows.append({"원료코드": c,
                     "원료명": nm.get(c) or (name_map.get(c, c) if name_map else c),
                     "배합률%": W[c], "단가σ": float(M[c].std(ddof=1)),
                     "단가평균": float(M[c].mean()), "기여": rc,
                     "기여비중%": rc / sigma * 100 if sigma else 0.0})
    df = pd.DataFrame(rows).sort_values("기여", key=lambda s: s.abs(), ascending=False)
    return df.reset_index(drop=True), sigma


def forecast_uc_matrix(bom_x=None, fp=None, products=None):
    """전 제품 × 전 월 단위원가 행렬 (일괄 출력용, 행렬곱으로 일괄 계산).
    반환: (uc, cov) — index=표준제품, columns=년월.
      uc  = Σ(배합률/100 × 단가)  원/kg
      cov = 단가가 존재하는 원료의 배합률 합 (%) — 100 미만이면 과소계산"""
    if bom_x is None:
        bom_x = model.explode_bom()
    if fp is None:
        fp = db.load_forecast()
    f = fp.copy()
    f["년월"] = f["년월"].astype(str); f["원료코드"] = f["원료코드"].astype(str)
    P = f.pivot_table(index="년월", columns="원료코드", values="단가", aggfunc="max").sort_index()
    b = bom_x.copy(); b["ERP코드"] = b["ERP코드"].astype(str)
    if products:
        b = b[b["표준명칭"].isin(list(products))]
    B = b.pivot_table(index="표준명칭", columns="ERP코드", values="배합률", aggfunc="sum").fillna(0.0)
    codes = [c for c in B.columns if c in P.columns]
    if not codes or B.empty:
        return pd.DataFrame(), pd.DataFrame()
    B2 = B[codes]
    P2 = P[codes].fillna(0.0)
    uc = pd.DataFrame(B2.values / 100.0 @ P2.values.T, index=B2.index, columns=P2.index)
    cov = pd.DataFrame(B2.values @ (P2.values > 0).astype(float).T,
                       index=B2.index, columns=P2.index)
    return uc, cov
