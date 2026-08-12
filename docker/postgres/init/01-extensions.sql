-- 컨테이너를 처음 만들 때 한 번만 실행됩니다.
-- (이미 데이터가 있는 볼륨에는 실행되지 않으니, 나중에 켜려면 psql 로 직접 실행하세요.)

-- 장소 이름/주소 부분 일치 검색용입니다.
-- `LIKE '%토큰%'` 은 일반 인덱스를 못 타서 215,436건을 순차 스캔합니다.
-- pg_trgm 의 GIN 인덱스가 이걸 인덱스 검색으로 바꿔 줍니다.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 반경/거리 질의용입니다.
-- 지금은 bounding box 로 좁힌 뒤 파이썬에서 하버사인을 돌고 있는데,
-- ST_DWithin + GiST 인덱스로 DB 안에서 끝낼 수 있습니다.
CREATE EXTENSION IF NOT EXISTS postgis;

-- 발음/오타 보정에 쓸 수 있습니다. 당장 쓰지 않지만 켜 두어도 비용이 없습니다.
CREATE EXTENSION IF NOT EXISTS unaccent;
