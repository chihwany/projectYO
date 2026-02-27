"""
사용 예제: 중고나라 스크래퍼
"""
from joongna_scraper import JoongnaScraper


def example_basic_search():
    """기본 검색 예제"""
    scraper = JoongnaScraper()
    
    # 아이폰 검색
    results = scraper.search("아이폰 15")
    print(JoongnaScraper.format_results(results))


def example_filtered_search():
    """필터 적용 검색 예제"""
    scraper = JoongnaScraper()
    
    # 맥북 - 노트북/PC 카테고리, 50만~150만원, 최신순
    results = scraper.search(
        "맥북",
        category=8,
        min_price=500000,
        max_price=1500000,
        sort="recent",
    )
    print(JoongnaScraper.format_results(results))


def example_multi_page():
    """다중 페이지 검색 예제"""
    scraper = JoongnaScraper(delay=1.5)  # 1.5초 간격
    
    # 닌텐도 스위치 - 3페이지까지
    results = scraper.search_all("닌텐도 스위치", max_pages=3)
    print(f"총 {len(results)}개 결과 수집")
    
    # 가격순 정렬 출력
    sorted_results = sorted(results, key=lambda x: x["price"])
    for item in sorted_results[:10]:
        print(f"  {item['price_str']:>12s} | {item['title'][:40]}")


def example_monitor_keyword():
    """키워드 모니터링 예제 (주기적 검색)"""
    import time
    
    scraper = JoongnaScraper()
    seen_ids = set()
    
    print("🔔 '에어팟 프로' 매물 모니터링 시작 (Ctrl+C로 종료)")
    
    try:
        while True:
            results = scraper.search("에어팟 프로", sort="recent", count=10)
            new_items = [r for r in results if r["id"] not in seen_ids]
            
            if new_items:
                print(f"\n🆕 새 매물 {len(new_items)}개 발견!")
                for item in new_items:
                    print(f"  [{item['price_str']}] {item['title']}")
                    print(f"    → {item['url']}")
                    seen_ids.add(item["id"])
            else:
                print(".", end="", flush=True)
            
            time.sleep(60)  # 1분 간격
    except KeyboardInterrupt:
        print(f"\n\n모니터링 종료. 총 {len(seen_ids)}개 매물 감지")


if __name__ == "__main__":
    print("=" * 50)
    print(" 중고나라 스크래퍼 예제")
    print("=" * 50)
    
    print("\n[1] 기본 검색 예제")
    example_basic_search()
    
    # 아래 주석을 해제하여 다른 예제 실행
    # print("\n[2] 필터 검색 예제")
    # example_filtered_search()
    
    # print("\n[3] 다중 페이지 검색 예제")
    # example_multi_page()
    
    # print("\n[4] 키워드 모니터링 예제")
    # example_monitor_keyword()
