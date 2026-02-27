"""
중고나라 스크래퍼 CLI
Usage: python main.py "검색어" [옵션]
"""

import argparse
import json
import sys
from ..scrapers.joongna_scraper import JoongnaScraper


def main():
    parser = argparse.ArgumentParser(
        description="중고나라 매물 검색 스크래퍼",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py "아이폰 15"
  python main.py "맥북" --category 8 --sort recent
  python main.py "갤럭시" --min-price 100000 --max-price 500000
  python main.py "에어팟" --json
  python main.py "아이패드" --pages 3
        """,
    )
    
    parser.add_argument("keyword", help="검색할 키워드")
    parser.add_argument("--page", type=int, default=1, help="페이지 번호 (기본: 1)")
    parser.add_argument("--pages", type=int, default=0, help="여러 페이지 검색 시 최대 페이지 수")
    parser.add_argument("--count", type=int, default=50, help="한 페이지당 결과 수 (기본: 50)")
    parser.add_argument(
        "--sort",
        choices=["recommend", "recent", "price_asc", "price_desc"],
        default="recommend",
        help="정렬 기준 (기본: recommend)",
    )
    parser.add_argument("--category", type=int, default=None, help="카테고리 코드")
    parser.add_argument("--min-price", type=int, default=0, help="최소 가격")
    parser.add_argument("--max-price", type=int, default=100_000_000, help="최대 가격")
    parser.add_argument("--include-sold", action="store_true", help="판매완료 포함")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON 형식 출력")
    parser.add_argument("--no-url", action="store_true", help="URL 미표시")
    parser.add_argument("--delay", type=float, default=1.0, help="요청 간 대기시간(초)")
    parser.add_argument("--detail", type=int, default=None, help="상품 ID로 상세 조회")

    args = parser.parse_args()

    scraper = JoongnaScraper(delay=args.delay)

    # 상세 조회 모드
    if args.detail:
        print(f"\n상품 #{args.detail} 상세 조회 중...")
        detail = scraper.get_product_detail(args.detail)
        if detail:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            print("상세 정보를 가져올 수 없습니다.")
        return

    # 검색 모드
    search_kwargs = {
        "count": args.count,
        "sort": args.sort,
        "category": args.category,
        "min_price": args.min_price,
        "max_price": args.max_price,
        "exclude_sold": not args.include_sold,
    }

    print(f"\n🔍 '{args.keyword}' 검색 중...\n")

    if args.pages > 0:
        results = scraper.search_all(args.keyword, max_pages=args.pages, **search_kwargs)
    else:
        results = scraper.search(args.keyword, page=args.page, **search_kwargs)

    if not results:
        print("검색 결과가 없습니다.")
        sys.exit(0)

    # 출력
    if args.json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(JoongnaScraper.format_results(results, show_url=not args.no_url))

    print(f"\n총 {len(results)}개 결과")


if __name__ == "__main__":
    main()
