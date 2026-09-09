# -*- coding: utf-8 -*-
"""브랜드 테마 — 색상 팔레트 + Plotly 전역 템플릿.
Colour balance: Red 218,41,28 / Black / Gray 128,128,128 / Light Gray 221,221,221"""
import plotly.graph_objects as go
import plotly.io as pio

# ---- 브랜드 기본 ----
RED = "#DA291C"      # 218, 41, 28
BLACK = "#000000"
GRAY = "#808080"     # 128, 128, 128
LIGHT = "#DDDDDD"    # 221, 221, 221

# ---- 의미색 ----
UP = RED             # 증가 · 원가 상승 · 주의
DOWN = "#3E4A54"     # 감소 · 절감 (블랙 계열, RED와 명도 대비)
NEUTRAL = GRAY       # 합계 · 중립
MUTED = LIGHT        # 비교 기준(전월) · 보조
DARK = "#2B2B2B"     # 본문 · 강조선
GRID = "#ECECEC"

# ---- 다계열용(연도·원료군 등): 브랜드 단색조 + 명도 변주 ----
CATEGORICAL = [RED, DOWN, GRAY, "#F08076", "#5F5F5F", "#C4C4C4"]

FONT = "Malgun Gothic, Apple SD Gothic Neo, sans-serif"


def updown(values, up=UP, down=DOWN):
    """증감 값 → 색 리스트 (증가=브랜드 레드, 감소=다크)."""
    return [up if (v is not None and v >= 0) else down for v in values]


def apply_plotly():
    """Plotly 전역 템플릿 등록 — 앱 시작 시 1회 호출."""
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, size=12, color=DARK),
        colorway=CATEGORICAL,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRID, linecolor=LIGHT, zerolinecolor=GRID,
                   ticks="outside", tickcolor=LIGHT, automargin=True),
        yaxis=dict(gridcolor=GRID, linecolor=LIGHT, zerolinecolor=GRID, automargin=True),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=LIGHT,
                        font=dict(family=FONT, size=12, color=DARK)),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    pio.templates["harim"] = t
    pio.templates.default = "harim"
