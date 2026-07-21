# -*- coding: utf-8 -*-
"""월 파일 파싱 + 검증 게이트."""
import re
from collections import defaultdict
import pandas as pd
from . import db, model, config as C

_tail = re.compile(r'\s*\d+(?:\.\d+)?\s*[kK]?[gG]\s*(?:\([^)]*\))?\s*[\d,]*\s*개?\s*$')
_qty = re.compile(r'\s*[\d,]+\s*개\s*$')

def _base(s):
    s2 = _tail.sub('', s)
    if s2 != s and s2.strip():
        return re.sub(r'\s+', ' ', s2).strip()
    return re.sub(r'\s+', ' ', _qty.sub('', s)).strip()


def parse_plan(file, base2std=None):
    """관리자 계획중량 파일 → (plan_rows, report).
    plan_rows: DataFrame[표준제품, 계획중량]
    report: dict(행수, 미매칭[base:cnt], 복수제품행[list])"""
    if base2std is None:
        _, base2std = db.load_mapping()
    raw = pd.read_excel(file, header=None).iloc[1:][[2, 4]]
    raw.columns = ["품목명", "계획중량"]
    raw = raw.dropna(subset=["품목명"])
    agg = defaultdict(float)
    unmapped = defaultdict(int)
    multi = []
    for _, r in raw.iterrows():
        try: wt = float(r["계획중량"])
        except Exception: wt = 0.0
        stds = []
        for sk in re.split(r',(?!\d)', str(r["품목명"])):
            b = _base(sk.strip())
            if not b or re.fullmatch(r'[\d,]+개?', b):
                continue
            s = base2std.get(b)
            if s is None:
                unmapped[b] += 1
            else:
                stds.append(s)
        d = list(dict.fromkeys(stds))
        if len(d) == 1:
            agg[d[0]] += wt
        elif len(d) > 1:
            multi.append((wt, d))
            for s in d:
                agg[s] += wt / len(d)
    plan_rows = pd.DataFrame(sorted(agg.items()), columns=["표준제품", "계획중량"])
    report = {"행수": len(raw), "미매칭": dict(unmapped), "복수제품행": multi,
              "제품수": len(plan_rows)}
    return plan_rows, report


def parse_plan_multi(file, base2std=None):
    """여러 달이 섞인 관리자 계획중량 파일 → 작업일자로 월 자동 분리.
    반환: (months_dict{ 'YYYY-MM': DataFrame[표준제품,계획중량] }, report)"""
    if base2std is None:
        _, base2std = db.load_mapping()
    raw = pd.read_excel(file, header=None).iloc[1:][[0, 2, 4]]
    raw.columns = ["작업일자", "품목명", "계획중량"]
    raw = raw.dropna(subset=["품목명"])

    def to_ym(v):
        s = re.sub(r"\.0$", "", str(v)).strip()
        m = re.match(r"(\d{4})(\d{2})\d{2}", s)
        return f"{m.group(1)}-{m.group(2)}" if m else None

    raw["년월"] = raw["작업일자"].map(to_ym)
    bad_date = int(raw["년월"].isna().sum())
    raw = raw.dropna(subset=["년월"])

    months = {}
    unmapped = defaultdict(int)
    multi = 0
    per_month = {}
    for ym, g in raw.groupby("년월"):
        agg = defaultdict(float)
        for _, r in g.iterrows():
            try: wt = float(r["계획중량"])
            except Exception: wt = 0.0
            stds = []
            for sk in re.split(r',(?!\d)', str(r["품목명"])):
                b = _base(sk.strip())
                if not b or re.fullmatch(r'[\d,]+개?', b):
                    continue
                s = base2std.get(b)
                if s is None:
                    unmapped[b] += 1
                else:
                    stds.append(s)
            d = list(dict.fromkeys(stds))
            if len(d) == 1:
                agg[d[0]] += wt
            elif len(d) > 1:
                multi += 1
                for s in d:
                    agg[s] += wt / len(d)
        months[ym] = pd.DataFrame(sorted(agg.items()), columns=["표준제품", "계획중량"])
        per_month[ym] = {"행수": len(g), "제품수": len(months[ym]),
                         "생산kg": float(months[ym]["계획중량"].sum())}
    report = {"월별": per_month, "미매칭": dict(unmapped),
              "복수제품행": multi, "무효작업일자행": bad_date}
    return months, report


def parse_price(file):
    """단가/사용량 파일 → price_rows[원료코드,원료명,단가,실적사용kg,실적금액].
    메인DB와 동일 스키마(년월·품목코드·품목명·단가·사용량·금액) 가정, 유연 매핑."""
    df = pd.read_excel(file)
    cols = {c: str(c) for c in df.columns}
    df = df.rename(columns=cols)
    def pick(cands):
        for c in df.columns:
            if any(k in c for k in cands): return c
        return None
    ccode = pick(["코드"]); cname = pick(["품목명", "원료명", "명"])
    cprice = pick(["단가"]); cuse = pick(["사용량", "사용kg"]); camt = pick(["금액"])
    out = pd.DataFrame({
        "원료코드": df[ccode].astype(str),
        "원료명": df[cname] if cname else "",
        "단가": df[cprice] if cprice else 0,
        "실적사용kg": df[cuse] if cuse else 0,
        "실적금액": df[camt] if camt else 0,
    })
    return out


def _norm_ym(v):
    """다양한 년월 표기를 'YYYY-MM'으로. (2026-07, 202607, 2026.07, datetime 등)"""
    import datetime as _dt
    if isinstance(v, (_dt.datetime, _dt.date)):
        return f"{v.year:04d}-{v.month:02d}"
    s = re.sub(r"\.0$", "", str(v)).strip()
    m = re.match(r"(\d{4})[-.\/ ]?(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    return None


def parse_price_multi(file):
    """여러 달이 섞인 단가·사용량 파일(년월 컬럼 포함) → 월별 분리.
    반환: (months_dict{ym: DataFrame[원료코드,원료명,단가,실적사용kg,실적금액]}, report)"""
    df = pd.read_excel(file)
    df.columns = [str(c) for c in df.columns]
    def pick(cands):
        for c in df.columns:
            if any(k in c for k in cands):
                return c
        return None
    cym = pick(["년월", "월", "기간", "yyyy"])
    ccode = pick(["코드"]); cname = pick(["품목명", "원료명", "명"])
    cprice = pick(["단가"]); cuse = pick(["사용량", "사용kg"]); camt = pick(["금액"])
    if cym is None or ccode is None:
        raise ValueError("필수 컬럼(년월/코드)을 찾지 못했습니다. 업로드 양식을 확인하세요.")
    work = pd.DataFrame({
        "년월": df[cym].map(_norm_ym),
        "원료코드": df[ccode].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
        "원료명": df[cname] if cname else "",
        "단가": pd.to_numeric(df[cprice], errors="coerce") if cprice else 0,
        "실적사용kg": pd.to_numeric(df[cuse], errors="coerce") if cuse else 0,
        "실적금액": pd.to_numeric(df[camt], errors="coerce") if camt else 0,
    })
    bad = int(work["년월"].isna().sum() + (work["원료코드"].isin(["", "nan", "None"])).sum())
    work = work.dropna(subset=["년월"])
    work = work[~work["원료코드"].isin(["", "nan", "None"])]
    work[["단가", "실적사용kg", "실적금액"]] = work[["단가", "실적사용kg", "실적금액"]].fillna(0)
    months, per = {}, {}
    for ym, g in work.groupby("년월"):
        g = g.drop(columns=["년월"]).reset_index(drop=True)
        months[ym] = g
        per[ym] = {"코드수": g["원료코드"].nunique(), "단가0": int((g["단가"] == 0).sum())}
    report = {"월별": per, "무효행": bad}
    return months, report


def parse_forecast_multi(file):
    """예상단가 파일(년월·원료코드·단가, 여러 달) → 월별 분리.
    반환: (months_dict{ym: DataFrame[원료코드,원료명,단가]}, report)"""
    df = pd.read_excel(file)
    df.columns = [str(c) for c in df.columns]
    def pick(cands):
        for c in df.columns:
            if any(k in c for k in cands):
                return c
        return None
    cym = pick(["년월", "월", "기간"])
    ccode = pick(["코드"]); cname = pick(["원료명", "품목명", "명"])
    cprice = pick(["단가"])
    if cym is None or ccode is None or cprice is None:
        raise ValueError("필수 컬럼(년월/원료코드/단가)을 찾지 못했습니다.")
    work = pd.DataFrame({
        "년월": df[cym].map(_norm_ym),
        "원료코드": df[ccode].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
        "원료명": df[cname] if cname else "",
        "단가": pd.to_numeric(df[cprice], errors="coerce"),
    })
    bad = int(work["년월"].isna().sum())
    work = work.dropna(subset=["년월"])
    work = work[~work["원료코드"].isin(["", "nan", "None"])]
    work["단가"] = work["단가"].fillna(0)
    months, per = {}, {}
    for ym, g in work.groupby("년월"):
        months[ym] = g.drop(columns=["년월"]).reset_index(drop=True)
        per[ym] = {"코드수": g["원료코드"].nunique(), "단가0": int((g["단가"] == 0).sum())}
    return months, {"월별": per, "무효행": bad}


def validate_month(ym, plan_rows):
    """월 마감 검증 게이트. 통과 여부 + 이슈 리스트."""
    issues = []
    bom = db.load_bom()
    bomprods = set(bom["표준명칭"].unique())
    # 1) 생산제품 BOM 보유
    nobom = sorted(set(plan_rows["표준제품"]) - bomprods)
    if nobom:
        issues.append(("BOM없는 생산제품", nobom))
    # 2) 전개 후 원료 단가 커버리지
    bom_x = model.explode_bom(bom)
    need = set(bom_x[bom_x["표준명칭"].isin(plan_rows["표준제품"])]["ERP코드"])
    price = db.load_price(); price["년월"] = price["년월"].astype(str)
    have = set(price[price["년월"] == ym]["원료코드"])
    nomprice = sorted(need - have)
    if nomprice:
        issues.append(("단가없는 원료코드", nomprice))
    # 3) BOM 배합률 합계 체크
    bad = []
    for p, g in bom.groupby("표준명칭"):
        s = g["배합률"].sum()
        if not (100 - C.BOM_SUM_TOL <= s <= 100 + C.BOM_SUM_TOL):
            bad.append((p, round(s, 2)))
    if bad:
        issues.append(("BOM합계 100%아님", bad))
    return (len(issues) == 0), issues
