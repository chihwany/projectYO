"""
번개장터 스크래퍼 사용 예제
"""

from bunjang_scraper import BunjangScraper
import json


def example_basic_search():
    """기본 검색 예제"""
    print("\n" + "=" * 50)
    print("1. 기본 검색")
    print("=" * 50)

    scraper = BunjangScraper()
    results = scraper.search("아이폰 16", count=5)
    print(BunjangScraper.format_results(results))


def example_filtered_search():
    """필터 적용 검색 예제"""
    print("\n" + "=" * 50)
    print("2. 필터 적용 검색 (가격 범위 + 최신순)")
    print("=" * 50)

    scraper = BunjangScraper()
    results = scraper.search(
        keyword="맥북 프로",
        sort="recent",
        min_price=500000,
        max_price=2000000,
        count=5,
    )
    print(BunjangScraper.format_results(results))


def example_category_search():
    """카테고리 검색 예제"""
    print("\n" + "=" * 50)
    print("3. 카테고리 검색 (스마트폰: 601)")
    print("=" * 50)

    scraper = BunjangScraper()
    results = scraper.search(
        keyword="갤럭시 S24",
        category=601,  # 스마트폰
        count=5,
    )
    print(BunjangScraper.format_results(results))


def example_multi_page():
    """멀티 페이지 검색 예제"""
    print("\n" + "=" * 50)
    print("4. 멀티 페이지 검색 (3페이지)")
    print("=" * 50)

    scraper = BunjangScraper(delay=1.5)
    results = scraper.search_all(
        keyword="에어팟",
        max_pages=3,
        count=10,
    )
    print(f"\n총 {len(results)}개 결과 수집 완료")
    # 처음 5개만 출력
    print(BunjangScraper.format_results(results[:5]))


def example_json_output():
    """JSON 출력 예제"""
    print("\n" + "=" * 50)
    print("5. JSON 출력")
    print("=" * 50)

    scraper = BunjangScraper()
    results = scraper.search("닌텐도 스위치", count=3)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def example_price_sort():
    """가격순 정렬 예제"""
    print("\n" + "=" * 50)
    print("6. 가격 낮은 순 정렬")
    print("=" * 50)

    scraper = BunjangScraper()
    results = scraper.search(
        keyword="아이패드",
        sort="price_asc",
        min_price=100000,
        count=5,
    )
    print(BunjangScraper.format_results(results))


if __name__ == "__main__":
    print("번개장터 스크래퍼 예제")
    print("=" * 50)

    # 원하는 예제를 선택하여 실행하세요
    example_basic_search()
    # example_filtered_search()
    # example_category_search()
    # example_multi_page()
    # example_json_output()
    # example_price_sort()
