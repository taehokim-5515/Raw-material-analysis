# -*- coding: utf-8 -*-
"""분류 차원: 원료군(ERP코드 접두), 브랜드/그룹(제품명)."""

_GROUP = {
    "101": "육류·단백", "102": "유지·오일", "103": "곡물",
    "104": "전분", "105": "두류·채소·식이섬유", "106": "종실·베리",
    "107": "아미노산", "108": "미네랄·염류", "109": "기능성·첨가",
    "160": "쿠키·기타원료", "170": "쿠키·기타원료", "600": "반제품(키블)",
}

def material_group(code):
    return _GROUP.get(str(code)[:3], "기타")


# 쿠키류(브랜드 무관하게 별도 그룹으로 묶음)
_COOKIES = {
    "밥이보약 쿠키 관절", "밥이보약 눈이반짝", "밥이보약 면역쑥쑥",
    "맥시칸 양념 멍쿠키", "용가리 멍쿠키",
}

def is_cat(product):
    """고양이 제품 여부."""
    p = str(product)
    return ("캣" in p) or ("CAT" in p.upper()) or ("키튼" in p) or ("고양이" in p)


def brand_of(product):
    """브랜드 그룹: 더리얼(키블 포함) / 쿠키 / 밥이보약 / OEM(그외)."""
    p = str(product)
    if p in _COOKIES:
        return "쿠키"
    if p.startswith("더리얼") or p.startswith("그린파워") or p.startswith("베리베리"):
        return "더리얼"
    if p.startswith("밥이보약"):
        return "밥이보약"
    return "OEM"  # 프라임펫·펫후·마푸·닥터썸업·더베터 등


def plan_group(product):
    """계획중량 집계용: 더리얼 도그/캣 · 밥이보약 도그/캣 · OEM."""
    p = str(product)
    if p.startswith("더리얼") or p.startswith("그린파워") or p.startswith("베리베리"):
        return "더리얼 캣" if is_cat(p) else "더리얼 도그"
    if p.startswith("밥이보약"):
        return "밥이보약 캣" if is_cat(p) else "밥이보약 도그"
    return "OEM"
