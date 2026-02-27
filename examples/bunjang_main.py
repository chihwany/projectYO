"""
번개장터 CLI 검색 도구
사용법: python bunjang_main.py "검색어" [옵션]
"""

import argparse
import json
import sys
from ..scrapers.bunjang_scraper import BunjangScraper


def main():
    parser = argparse.ArgumentParser(
        description="번개장터 매물 검색 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python bunjang_main.py "아이폰 16"
  python bunjang_main.py "맥북" --sort recent --count 10
  python bunjang_main.py "에어팟" --min-price 50000 --max-price 150000
  python bunjang_main.py "갤럭시" --category 601 --json
  python bunjang_main.py "나이키" --pages 3 --include-sold
        """,
    )

    parser.add_argument("keyword", help="검색어")
    parser.add_argument("--page", type=int, default=1, help="페이지 번호 (기본: 1)")
    parser.add_argument("--pages", type=int, default=1, help="검색할 페이지 수 (기본: 1)")
    parser.add_argument("--count", type=int, default=20, help="페이지당 결과 수 (기본: 20, 최대: 100)")
    parser.add_argument(
        "--sort",
        choices=["recommend", "recent", "price_asc", "price_desc"],
        default="recommend",
        help="정렬 기준 (기본: recommend)",
    )
    parser.add_argument("--category", type=int, default=None, help="카테고리 코드")
    parser.add_argument("--min-price", type=int, default=None, help="최소 가격")
    parser.add_argument("--max-price", type=int, default=None, help="최대 가격")
    parser.add_argument("--include-sold", action="store_true", help="판매완료 포함")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    parser.add_argument("--delay", type=float, default=1.0, help="요청 간격 초 (기본: 1.0)")

    args = parser.parse_args()

    scraper = BunjangScraper(delay=args.delay)

    if args.pages > 1:
        results = scraper.search_all(
            keyword=args.keyword,
            max_pages=args.pages,
            count=args.count,
            sort=args.sort,
            category=args.category,
            min_price=args.min_price,
            max_price=args.max_price,
            exclude_sold=not args.include_sold,
        )
    else:
        results = scraper.search(
            keyword=args.keyword,
            page=args.page,
            count=args.count,
            sort=args.sort,
            category=args.category,
            min_price=args.min_price,
            max_price=args.max_price,
            exclude_sold=not args.include_sold,
        )

    if not results:
        print("검색 결과가 없습니다.")
        sys.exit(0)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(BunjangScraper.format_results(results))


if __name__ == "__main__":
    main()
