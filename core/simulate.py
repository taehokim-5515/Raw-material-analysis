# -*- coding: utf-8 -*-
"""단가 시뮬레이션 — 원료 단가를 바꾸면 제품 kg당 원재료비가 얼마나 바뀌나.

제품 단위원가  c_p = Σ_c 배합률_pc/100 × 단가_c
단가가 Δp_c 바뀌면  Δc_p = Σ_c 배합률_pc/100 × Δp_c   (선형, 정확)
월 원료비 영향      ΔA  = Σ_p 계획중량_p × Δc_p

배합비는 기준월에 유효한 버전, 키블 반제품은 하위 원료로 전개한다(경로는 따로 표시).
"""
from collections import defaultdict
import pandas as pd
from . import db, dims, config as C

SRC_ACTUAL = "실적 단가"
SRC_FORECAST = "예상단가"


# ---------- 기준 데이터 ----------
def base_months():
    """단가 기준별 선택 가능한 월."""
    pr = db.load_price()
    fp = db.load_forecast()
    return {SRC_ACTUAL: sorted(pr["년월"].astype(str).unique()),
            SRC_FORECAST: sorted(fp["년월"].astype(str).unique()) if len(fp) else []}


def base_prices(ym, source=SRC_ACTUAL):
    """기준월 단가표 {원료코드: 단가}와 원료명 {원료코드: 이름}."""
    df = db.load_price() if source == SRC_ACTUAL else db.load_forecast()
    df = df.copy()
    df["년월"] = df["년월"].astype(str)
    df["원료코드"] = df["원료코드"].astype(str)
    sub = df[df["년월"] == str(ym)]
    return dict(zip(sub["원료코드"], sub["단가"].astype(float))), dict(zip(sub["원료코드"], sub["원료명"]))


def explode_with_path(bom_raw):
    """키블 반제품을 전개하되 경로(직접/키블)를 남긴 제품×원료 배합률.
    반환: [표준명칭, ERP코드, 경로, 배합률]"""
    kib = {k: bom_raw[bom_raw["표준명칭"] == v][["ERP코드", "배합률"]].values.tolist()
           for k, v in C.KIBBLE_CODES.items()}
    out = defaultdict(float)
    for p, code, ratio in bom_raw[["표준명칭", "ERP코드", "배합률"]].itertuples(index=False):
        code = str(code)
        if code in kib:
            for sc, sr in kib[code]:
                out[(p, str(sc), "키블 경유")] += float(ratio) * float(sr) / 100.0
        else:
            out[(p, code, "직접")] += float(ratio)
    return pd.DataFrame([(p, c, k, v) for (p, c, k), v in out.items()],
                        columns=["표준명칭", "ERP코드", "경로", "배합률"])


def plan_weights(ym):
    """물량 기준: 기준월 계획중량. 없으면(미래 월) 최신 계획월로 대체."""
    pl = db.load_plan().copy()
    pl["년월"] = pl["년월"].astype(str)
    months = sorted(pl["년월"].unique())
    if not months:
        return pd.Series(dtype=float), None
    use = str(ym) if str(ym) in months else months[-1]
    return pl[pl["년월"] == use].groupby("표준제품")["계획중량"].sum(), use


def material_options(ym, source=SRC_ACTUAL, name_map=None):
    """선택 가능한 원료(기준월 BOM에 있는 원료) — 사용 제품 수·현재 단가 포함."""
    bx = explode_with_path(db.load_bom(ym))
    pm, nm = base_prices(ym, source)
    g = bx.groupby("ERP코드").agg(사용제품수=("표준명칭", "nunique")).reset_index()
    names = dict(name_map or {})
    names.update({k: v for k, v in nm.items() if v})
    g["원료명"] = g["ERP코드"].map(names).fillna(g["ERP코드"])
    g["현재단가"] = g["ERP코드"].map(pm).fillna(0.0)
    g["라벨"] = g["원료명"] + " (" + g["ERP코드"] + ")"
    return g.sort_values(["사용제품수", "원료명"], ascending=[False, True]).reset_index(drop=True)


# ---------- 시뮬레이션 ----------
def simulate(ym, new_prices, source=SRC_ACTUAL, name_map=None):
    """new_prices: {원료코드: 새 단가}. 반환: (제품별 df, 원료별 df, 요약 dict)."""
    bx = explode_with_path(db.load_bom(ym))
    pm, nm = base_prices(ym, source)
    names = dict(name_map or {})
    names.update({k: v for k, v in nm.items() if v})
    w, w_month = plan_weights(ym)

    dp = {str(c): float(v) - float(pm.get(str(c), 0.0)) for c, v in new_prices.items()}
    bx["p0"] = bx["ERP코드"].map(pm).fillna(0.0)
    bx["dp"] = bx["ERP코드"].map(dp).fillna(0.0)
    bx["c0"] = bx["배합률"] / 100.0 * bx["p0"]
    bx["dc"] = bx["배합률"] / 100.0 * bx["dp"]
    hit = bx[bx["ERP코드"].isin(dp.keys())]

    base = bx.groupby("표준명칭").agg(현재=("c0", "sum"),
                                     결측원료수=("p0", lambda s: int((s <= 0).sum())))
    if hit.empty:
        return (pd.DataFrame(), pd.DataFrame(),
                {"영향제품수": 0, "월영향": 0.0, "물량월": w_month, "가중평균": 0.0})

    paths = (hit.groupby("표준명칭")["경로"]
             .agg(lambda s: "직접, 키블 경유" if s.nunique() > 1 else s.iloc[0]))
    prod = hit.groupby("표준명칭").agg(대상배합률=("배합률", "sum"), 변화=("dc", "sum"))
    prod = prod.join(base, how="left").join(paths)
    prod["변경후"] = prod["현재"] + prod["변화"]
    prod["변화율"] = prod["변화"] / prod["현재"].where(prod["현재"] > 0) * 100
    prod["생산kg"] = prod.index.map(w).fillna(0.0)
    prod["월영향"] = prod["생산kg"] * prod["변화"]
    prod["브랜드"] = prod.index.map(dims.brand_of)
    prod = (prod.reset_index().rename(columns={"표준명칭": "제품"})
            .sort_values("변화", key=lambda s: s.abs(), ascending=False).reset_index(drop=True))

    hit = hit.assign(생산kg=hit["표준명칭"].map(w).fillna(0.0))
    mat = (hit.groupby("ERP코드")
           .agg(사용제품수=("표준명칭", "nunique"),
                최대변화=("dc", lambda s: float(s.abs().max())),
                월영향=("dc", lambda s: float((s * hit.loc[s.index, "생산kg"]).sum())))
           .reset_index())
    mat["원료명"] = mat["ERP코드"].map(names).fillna(mat["ERP코드"])
    mat["현재단가"] = mat["ERP코드"].map(pm).fillna(0.0)
    mat["새단가"] = mat["ERP코드"].map({str(k): float(v) for k, v in new_prices.items()})
    mat["단가변동"] = mat["새단가"] - mat["현재단가"]

    W = float(prod["생산kg"].sum()) if len(prod) else 0.0
    tot_w = float(w.sum()) if len(w) else 0.0
    summ = {
        "영향제품수": int(len(prod)),
        "월영향": float(prod["월영향"].sum()),
        "물량월": w_month,
        # 전 생산량 가중 평균 kg당 변화(영향 없는 제품은 0으로 포함)
        "가중평균": float(prod["월영향"].sum()) / tot_w if tot_w else 0.0,
        "영향제품생산kg": W,
        "최대제품": prod.iloc[0]["제품"],
        "최대변화": float(prod.iloc[0]["변화"]),
    }
    return prod, mat.sort_values("월영향", key=lambda s: s.abs(), ascending=False), summ


def actual_usage_impact(ym, new_prices):
    """실적 사용량 기준 월 영향 = Σ 실적사용kg × Δ단가 (BOM 없는 라인까지 포함한 실제 지출 기준)."""
    pr = db.load_price().copy()
    pr["년월"] = pr["년월"].astype(str)
    pr["원료코드"] = pr["원료코드"].astype(str)
    sub = pr[pr["년월"] == str(ym)].set_index("원료코드")
    tot = 0.0
    for c, v in new_prices.items():
        c = str(c)
        if c in sub.index:
            tot += float(sub.at[c, "실적사용kg"]) * (float(v) - float(sub.at[c, "단가"]))
    return tot


# ---------- 민감도 ----------
def sensitivity(ym, pct=10.0, source=SRC_ACTUAL, name_map=None):
    """전 BOM 원료를 각각 pct% 바꿨을 때의 영향 순위(한 번에 하나씩)."""
    bx = explode_with_path(db.load_bom(ym))
    pm, nm = base_prices(ym, source)
    names = dict(name_map or {})
    names.update({k: v for k, v in nm.items() if v})
    w, w_month = plan_weights(ym)
    bx["p0"] = bx["ERP코드"].map(pm).fillna(0.0)
    bx["dc"] = bx["배합률"] / 100.0 * bx["p0"] * pct / 100.0
    bx["생산kg"] = bx["표준명칭"].map(w).fillna(0.0)
    bx["amt"] = bx["dc"] * bx["생산kg"]
    g = (bx.groupby("ERP코드")
         .agg(사용제품수=("표준명칭", "nunique"), 최대변화=("dc", "max"), 월영향=("amt", "sum"))
         .reset_index())
    g["원료명"] = g["ERP코드"].map(names).fillna(g["ERP코드"])
    g["현재단가"] = g["ERP코드"].map(pm).fillna(0.0)
    top = bx.loc[bx.groupby("ERP코드")["dc"].idxmax(), ["ERP코드", "표준명칭"]]
    g["최대제품"] = g["ERP코드"].map(dict(zip(top["ERP코드"], top["표준명칭"])))
    base_amt = float((bx["배합률"] / 100.0 * bx["p0"] * bx["생산kg"]).sum())
    g["원료비대비"] = g["월영향"] / base_amt * 100 if base_amt else 0.0
    g = g.sort_values("월영향", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    g.insert(0, "순위", range(1, len(g) + 1))
    return g, {"물량월": w_month, "기준원료비": base_amt}
