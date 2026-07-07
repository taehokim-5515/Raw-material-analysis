# -*- coding: utf-8 -*-
"""경로·상수 정의."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLAN_DIR = DATA / "plan_files"

MAIN_DB = DATA / "main_db.xlsx"       # 시트: 원료단가사용, 생산계획
BOM_XLSX = DATA / "bom_master.xlsx"   # 시트: BOM, 원료마스터
MAPPING_XLSX = DATA / "mapping.xlsx"  # 시트: 매핑표

# 반제품(키블) 코드 → 표준제품명. 원료비 계산 시 하위 원료로 전개(explode).
KIBBLE_CODES = {
    "6000001": "그린파워딜라이트 키블",
    "6000002": "베리베리슈퍼러브 키블",
}

# 검증 임계값
BOM_SUM_TOL = 0.5      # 배합률 합계 100±0.5% 정상
PRICE_SPIKE_PCT = 15.0 # 단가 전월대비 ±15% 초과 시 감시 플래그
