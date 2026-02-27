"""
당근 (Daangn/Karrot) 스크래퍼
www.daangn.com 매물을 검색하고 조회하는 모듈
"""

import datetime
import requests
import json
import time
import re
from urllib.parse import quote, urlencode, unquote
from typing import Optional
from bs4 import BeautifulSoup


class DaangnScraper:
    """당근 매물 스크래퍼"""

    BASE_URL = "https://www.daangn.com"

    CATEGORY_MAP = {
        1: "디지털기기",
        172: "생활가전",
        8: "가구/인테리어",
        7: "생활/주방",
        4: "유아동",
        173: "유아도서",
        5: "여성의류",
        31: "여성잡화",
        14: "남성패션/잡화",
        6: "뷰티/미용",
        3: "스포츠/레저",
        2: "취미/게임/음반",
        9: "도서",
        304: "티켓/교환권",
        517: "e쿠폰",
        305: "가공식품",
        483: "건강기능식품",
        16: "반려동물용품",
        139: "식물",
        13: "기타 중고물품",
        32: "삽니다",
    }

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.daangn.com/",
        })
        self._last_request_time = 0
        self._region_cache = None  # 지역 캐시 (flat list)

    def _parse_time_ago(self, time_ago_str: str) -> Optional[datetime.datetime]:
        """
        'X분 전', 'X시간 전', 'X일 전', 'X주 전', 'X개월 전' 등의 문자열을
        절대 datetime 객체로 변환합니다.
        """
        now = datetime.datetime.now()

        if not time_ago_str:
            return None

        time_ago_str = time_ago_str.strip()
        # Handle "끌올" prefix
        if time_ago_str.startswith("끌올 "):
            time_ago_str = time_ago_str[3:] # Remove "끌올 " (3 characters + space)
        
        if "방금 전" in time_ago_str:
            return now
        
        match = re.match(r"(\d+)(분|시간|일|주|개월) 전", time_ago_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)

            if unit == "분":
                return now - datetime.timedelta(minutes=value)
            elif unit == "시간":
                return now - datetime.timedelta(hours=value)
            elif unit == "일":
                return now - datetime.timedelta(days=value)
            elif unit == "주":
                return now - datetime.timedelta(weeks=value)
            elif unit == "개월":
                # Assuming 1 month = 30 days for simplicity
                return now - datetime.timedelta(days=value * 30)
        
        # If it's not a relative time string, return None
        return None

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _resolve_region(self, region: str) -> str:
        """
        지역명을 당근 코드로 변환.
        이미 '지역명-ID' 형식이면 그대로 반환.
        아니면 캐시에서 검색하여 매칭.
        """
        if not region:
            return ""

        # 이미 코드 형식이면 그대로
        if "-" in region and region.rsplit("-", 1)[-1].isdigit():
            return region

        # 캐시에서 검색
        if self._region_cache is None:
            self._load_region_cache()

        if self._region_cache:
            # 정확한 이름 매칭 우선
            for item in self._region_cache:
                if item["name"] == region:
                    return item["code"]
            # 부분 매칭
            for item in self._region_cache:
                if region in item["name"] or region in item["full"]:
                    return item["code"]

        # 캐시에 없으면 그대로 전달 (당근이 처리)
        return region

    def _load_region_cache(self):
        """지역 캐시 파일 로드"""
        try:
            from daangn_regions import load_regions, build_flat_list
            data = load_regions()
            if data:
                self._region_cache = build_flat_list(data)
            else:
                self._region_cache = []
        except ImportError:
            self._region_cache = []

    def _build_search_url(
        self,
        keyword: str,
        region: Optional[str] = None,
        category: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        only_on_sale: bool = False,
        page: int = 1,
    ) -> str:
        params = {}

        if keyword:
            params["search"] = keyword

        if region:
            resolved = self._resolve_region(region)
            if resolved:
                params["in"] = resolved

        if category:
            params["category_id"] = category

        if min_price is not None and max_price is not None:
            params["price"] = f"{min_price}__{max_price}"
        elif min_price is not None:
            params["price"] = f"{min_price}__"
        elif max_price is not None:
            params["price"] = f"0__{max_price}"

        if only_on_sale:
            params["only_on_sale"] = "true"

        if page > 1:
            params["page"] = page

        url = f"{self.BASE_URL}/kr/buy-sell/s/"
        if params:
            url += "?" + urlencode(params)

        return url

    @staticmethod
    def _is_garbled(text: str) -> bool:
        """텍스트가 깨졌는지 확인 (latin1로 잘못 디코딩된 한글)"""
        if not text:
            return False
        garbled_chars = sum(1 for c in text if 127 < ord(c) < 256)
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
        if garbled_chars > 2 and korean_chars == 0:
            return True
        return False

    @staticmethod
    def _title_from_slug(href: str) -> str:
        """URL slug에서 제목을 복원"""
        slug = href.rstrip("/").split("/")[-1] if href else ""
        if not slug:
            return ""
        decoded = unquote(slug)
        parts = decoded.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) >= 8 and re.match(r'^[a-z0-9]+$', parts[1]):
            decoded = parts[0]
        title = decoded.replace("-", " ").strip()
        return title

    def _parse_items_from_html(self, html: str) -> list[dict]:
        """HTML 내의 window.__remixContext JSON에서 상품 목록 추출"""
        results = []
        
        # 1. JSON 데이터 추출 시도
        match = re.search(r"window\.__remixContext\s*=\s*({.*?});", html, re.DOTALL)
        if match:
            try:
                json_str = match.group(1)
                data = json.loads(json_str)
                
                # 경로: state -> loaderData -> routes/kr.buy-sell.s -> allPage -> fleamarketArticles
                # (참고: 검색 결과 페이지에 따라 경로가 다를 수 있음)
                loader_data = data.get("state", {}).get("loaderData", {})
                articles = []
                
                # 가능한 경로들을 탐색
                for route_key in loader_data:
                    if "buy-sell" in route_key:
                        articles = loader_data[route_key].get("allPage", {}).get("fleamarketArticles", [])
                        if articles:
                            break
                
                if articles:
                    for art in articles:
                        price_val = art.get("price", "0")
                        try:
                            price = int(float(price_val))
                        except (ValueError, TypeError):
                            price = 0
                            
                        # 시간 정보 (boostedAt이 있으면 우선 사용, 없으면 createdAt)
                        time_str = art.get("boostedAt") or art.get("createdAt")
                        
                        results.append({
                            "id": art.get("id", "").strip("/").split("/")[-1],
                            "title": art.get("title"),
                            "price": price,
                            "price_str": "나눔🧡" if price == 0 else f"{price:,}원",
                            "image_url": art.get("thumbnail"),
                            "status": "판매중" if art.get("status") == "Ongoing" else art.get("status"),
                            "location": art.get("region", {}).get("name", ""),
                            "url": f"{self.BASE_URL}{art.get('id')}" if art.get("id") else "",
                            "time": time_str,
                            "time_ago": "최근" # JSON에는 상대 시간이 없으므로 기본값 설정
                        })
                    return results
            except Exception as e:
                print(f"DEBUG: JSON parsing failed: {e}. Falling back to HTML parsing.")

        # 2. JSON 추출 실패 시 기존 HTML 파싱 방식 (Fallback)
        soup = BeautifulSoup(html, "html.parser")
        product_links = soup.find_all("a", href=re.compile(r"/kr/buy-sell/(?!s[/?]|s$)[^?]"))

        for link in product_links:
            href = link.get("href", "")
            if href == "/kr/buy-sell/":
                continue

            img_tag = link.find("img")
            image_url = ""
            img_alt = ""
            if img_tag:
                image_url = img_tag.get("src", img_tag.get("data-src", ""))
                img_alt = img_tag.get("alt", "")

            text_content = link.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in text_content.split("\n") if l.strip()]

            if not lines:
                continue

            status = "판매중"
            title_start = 0
            if lines[0] in ("예약중", "판매완료", "거래완료"):
                status = lines[0]
                title_start = 1

            title = lines[title_start] if len(lines) > title_start else ""
            if not title or title == "thumbnail":
                if img_alt and img_alt != "thumbnail":
                    title = img_alt
                else:
                    continue

            if self._is_garbled(title):
                slug_title = self._title_from_slug(href)
                if slug_title:
                    title = slug_title

            price = 0
            price_str = "가격미정"
            for line in lines[title_start + 1:]:
                price_match = re.search(r'([\d,]+)\s*원', line)
                if price_match:
                    price = int(price_match.group(1).replace(",", ""))
                    price_str = f"{price:,}원"
                    break
                if "나눔" in line:
                    price_str = "나눔🧡"
                    break

            if price == 0:
                price_in_title = re.search(r'([\d,]+)원$', title)
                if price_in_title:
                    price = int(price_in_title.group(1).replace(",", ""))
                    price_str = f"{price:,}원"
                    title = title[:price_in_title.start()].strip()

            location = ""
            time_ago_str = ""

            card_desc = link.find("div", class_="card-desc")
            if card_desc:
                card_desc_full_text = card_desc.get_text(separator=' ', strip=True)
                print(f"DEBUG: card_desc_full_text: '{card_desc_full_text}'") # Debug print

                # Pattern: (Location part) (optional · ) (optional 끌올 ) (Time ago part)
                # Group 1: Location (e.g., "진영읍")
                # Group 2: Optional "끌올 " prefix
                # Group 3: Time ago string (e.g., "15분 전", "방금 전")
                combined_pattern = r"([가-힣\w]+[읍면동구시리])(?:\s*·?\s*(끌올\s*)?((?:\d+(?:분|시간|일|주|개월))? 전|방금 전))?"
                
                match = re.search(combined_pattern, card_desc_full_text)
                print(f"DEBUG: Regex match: {match}") # Debug print
                if match:
                    location = match.group(1)
                    time_ago_str_candidate = match.group(3)
                    if time_ago_str_candidate:
                        time_ago_str = time_ago_str_candidate
                print(f"DEBUG: Extracted location: '{location}', time_ago_str: '{time_ago_str}'") # Debug print
            
            full_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
            slug = href.rstrip("/").split("/")[-1] if href else ""

            results.append({
                "id": slug,
                "title": title,
                "price": price,
                "price_str": price_str,
                "image_url": image_url,
                "status": status,
                "location": location,
                "url": full_url,
                "time_ago": time_ago_str,
                "time": self._parse_time_ago(time_ago_str).isoformat() if self._parse_time_ago(time_ago_str) else None,
            })

        return results

    def search(
        self,
        keyword: str,
        region: Optional[str] = None,
        page: int = 1,
        category: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        only_on_sale: bool = False,
    ) -> list[dict]:
        """
        당근 매물 검색

        Args:
            keyword: 검색어
            region: 지역명 또는 코드 (예: "서초4동", "강남구", "서초4동-366")
            page: 페이지 번호 (1부터 시작)
            category: 카테고리 코드
            min_price: 최소 가격
            max_price: 최대 가격
            only_on_sale: 거래 가능만 보기

        Returns:
            검색 결과 리스트
        """
        self._throttle()

        url = self._build_search_url(
            keyword=keyword,
            region=region,
            category=category,
            min_price=min_price,
            max_price=max_price,
            only_on_sale=only_on_sale,
            page=page,
        )

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"

            # DEBUG: Save response HTML to a file for inspection
            with open("daangn_response.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("DEBUG: Saved daangn_response.html for inspection.")
        except requests.RequestException as e:
            print(f"[오류] 요청 실패: {e}")
            return []

        results = self._parse_items_from_html(response.text)

        region_str = f" ({region})" if region else ""
        if results:
            print(f"[검색완료] '{keyword}'{region_str} - {len(results)}개 조회")
        else:
            print(f"[검색완료] '{keyword}'{region_str} - 검색 결과 없음")

        return results

    def search_all(
        self,
        keyword: str,
        max_pages: int = 5,
        **kwargs,
    ) -> list[dict]:
        """여러 페이지에 걸쳐 검색"""
        all_results = []
        for page in range(1, max_pages + 1):
            results = self.search(keyword, page=page, **kwargs)
            if not results:
                break
            all_results.extend(results)
            print(f"  ... {page}페이지 완료 (누적 {len(all_results)}개)")
        return all_results

    @staticmethod
    def format_results(results: list[dict], show_url: bool = True) -> str:
        """검색 결과를 보기 좋게 포맷팅"""
        if not results:
            return "검색 결과가 없습니다."

        lines = []
        lines.append(f"{'='*60}")
        lines.append(f" 당근 검색 결과: {len(results)}개")
        lines.append(f"{'='*60}")

        for i, item in enumerate(results, 1):
            lines.append(f"\n[{i}] {item['title']}")
            lines.append(f"    💰 가격: {item['price_str']}")
            if item.get("status") and item["status"] != "판매중":
                lines.append(f"    📌 상태: {item['status']}")
            if item.get("location"):
                lines.append(f"    📍 지역: {item['location']}")
            if show_url:
                lines.append(f"    🔗 링크: {item['url']}")
            lines.append(f"    {'─'*40}")

        return "\n".join(lines)
