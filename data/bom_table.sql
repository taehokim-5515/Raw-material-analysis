-- 배합비(BOM) 버전 테이블 --------------------------------------------------
-- eff_from = 이 배합이 "적용되기 시작한 월"(YYYY-MM). 종료월은 두지 않는다.
-- 다음 버전의 eff_from 직전까지 자동으로 유효 → 공백/중복 구간이 구조적으로 불가능.
create table if not exists public.bom (
  id         bigserial primary key,
  eff_from   text             not null,           -- 'YYYY-MM'
  product    text             not null,           -- 표준명칭(제품 또는 키블 반제품)
  code       text             not null,           -- ERP코드
  name       text,                                -- 원료한글명(참고용)
  ratio      double precision not null default 0, -- 배합률(%)
  note       text,                                -- 변경 사유 메모
  created_at timestamptz      default now()
);

create unique index if not exists bom_uk  on public.bom (eff_from, product, code);
create index        if not exists bom_pv  on public.bom (product, eff_from);
