# scrapers 패키지
# 각 스크래퍼는 이 패키지 아래에 위치합니다.
#
# 표준 아이템 스키마 (10개 필드 — 모든 스크래퍼 공통):
#   id        : str   — 플랫폼 상품 고유 ID
#   title     : str   — 상품 제목
#   price     : int   — 가격 (파싱 실패 시 0)
#   price_str : str   — 가격 문자열 예) "1,200,000원"
#   image_url : str   — 대표 이미지 URL
#   status    : str   — "판매중" | "예약중" | "판매완료"
#   location  : str   — 지역명
#   time      : str   — ISO 8601 형식 예) "2024-01-15T10:30:00"
#   url       : str   — 모바일 웹 상품 URL
#   source    : str   — "bunjang" | "daangn" | "joongna"
