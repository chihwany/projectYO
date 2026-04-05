"""전국 동 레벨 매물 수집 테스트 (수정된 설정)"""

import time
import json
import asyncio
import sys

import aiohttp
import redis
from datetime import datetime, timedelta, timezone

r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
SEARCH_URL = "https://www.daangn.com/kr/buy-sell/s/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
KST = timezone(timedelta(hours=9))

# 수정된 설정
BATCH_SIZE = 50
BATCH_DELAY = 0.5
MAX_RETRY = 2
TIMEOUT = 3
POOL_LIMIT = 50

districts = json.loads(r.get("daangn:districts:all") or "[]")
all_dongs = []
for d in districts:
    dongs_raw = r.get(f'daangn:dongs:{d["regionId"]}')
    if dongs_raw:
        for dong in json.loads(dongs_raw):
            if dong.get("name3Id"):
                all_dongs.append({
                    "dong_id": dong["name3Id"],
                    "dong_name": dong.get("name3", ""),
                    "district": d["name"],
                })

now = datetime.now(KST)
one_min_ago = now - timedelta(minutes=1)
five_min_ago = now - timedelta(minutes=5)

print(f"설정: batch={BATCH_SIZE}, delay={BATCH_DELAY}s, timeout={TIMEOUT}s, pool={POOL_LIMIT}, retry={MAX_RETRY}")
print(f"전체 동: {len(all_dongs)}개 | 배치 수: {(len(all_dongs)+BATCH_SIZE-1)//BATCH_SIZE}")
print(f"시작: {now.strftime('%H:%M:%S')} KST")
print("=" * 60)
sys.stdout.flush()

total_articles = 0
new_1min = []
new_5min = []
seen_ids = set()
success_count = 0
error_count = 0
rate_limit_count = 0


def process_articles(dong, articles):
    global total_articles
    for a in articles:
        pid = a.get("id", "").rstrip("/").rsplit("/", 1)[-1]
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            total_articles += 1
            created = a.get("createdAt", "")
            if created:
                try:
                    ct = datetime.fromisoformat(created)
                    info = {
                        "title": a.get("title", ""),
                        "price": a.get("price", 0),
                        "loc": dong["district"] + " " + dong["dong_name"],
                        "created": created,
                    }
                    if ct >= one_min_ago:
                        new_1min.append(info)
                    if ct >= five_min_ago:
                        new_5min.append(info)
                except Exception:
                    pass


async def run_all():
    global success_count, error_count, rate_limit_count

    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    connector = aiohttp.TCPConnector(limit=POOL_LIMIT)

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as session:
        for batch_start in range(0, len(all_dongs), BATCH_SIZE):
            batch = all_dongs[batch_start : batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1

            # 배치 내 동시 요청
            tasks = []
            for dong in batch:
                params = {"in": dong["dong_id"], "_data": "routes/kr.buy-sell.s"}
                tasks.append(session.get(SEARCH_URL, params=params))

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            retry_list = []
            for i, resp in enumerate(responses):
                dong = batch[i]
                if isinstance(resp, Exception):
                    error_count += 1
                    continue
                try:
                    if resp.status == 429:
                        rate_limit_count += 1
                        retry_list.append(dong)
                        continue
                    data = await resp.json(content_type=None)
                    articles = data.get("allPage", {}).get("fleamarketArticles", [])
                    success_count += 1
                    process_articles(dong, articles)
                except Exception:
                    error_count += 1

            # 429 재시도 (최대 MAX_RETRY회)
            for retry_attempt in range(MAX_RETRY):
                if not retry_list:
                    break
                await asyncio.sleep(1.0 * (retry_attempt + 1))
                retry_tasks = []
                for dong in retry_list:
                    params = {"in": dong["dong_id"], "_data": "routes/kr.buy-sell.s"}
                    retry_tasks.append(session.get(SEARCH_URL, params=params))

                retry_responses = await asyncio.gather(*retry_tasks, return_exceptions=True)
                next_retry = []
                for i, resp in enumerate(retry_responses):
                    dong = retry_list[i]
                    if isinstance(resp, Exception):
                        error_count += 1
                        continue
                    try:
                        if resp.status == 429:
                            next_retry.append(dong)
                            continue
                        data = await resp.json(content_type=None)
                        articles = data.get("allPage", {}).get("fleamarketArticles", [])
                        success_count += 1
                        process_articles(dong, articles)
                    except Exception:
                        error_count += 1
                retry_list = next_retry

            if retry_list:
                error_count += len(retry_list)

            elapsed = time.time() - start_time
            done = batch_start + len(batch)
            if batch_num % 10 == 0 or done >= len(all_dongs):
                print(
                    f"  {done:>5}/{len(all_dongs)} | 매물: {total_articles:>7,} | "
                    f"1분내: {len(new_1min):>3} | 429: {rate_limit_count} | "
                    f"err: {error_count} | {elapsed:.0f}초"
                )
                sys.stdout.flush()

            # 배치 간 딜레이
            if batch_start + BATCH_SIZE < len(all_dongs):
                await asyncio.sleep(BATCH_DELAY)


start_time = time.time()
asyncio.run(run_all())
elapsed_total = time.time() - start_time

print()
print("=" * 60)
print("전국 동 레벨 매물 수집 결과")
print("=" * 60)
print(f"설정:             batch={BATCH_SIZE}, delay={BATCH_DELAY}s, timeout={TIMEOUT}s, pool={POOL_LIMIT}, retry={MAX_RETRY}")
print(f"총 동:            {len(all_dongs):,}개")
print(f"성공:             {success_count:,}개 ({success_count/len(all_dongs)*100:.1f}%)")
print(f"에러:             {error_count:,}개")
print(f"429 횟수:         {rate_limit_count:,}회")
print(f"총 매물 (중복제거): {total_articles:,}건")
print(f"1분 이내 매물:    {len(new_1min)}건")
print(f"5분 이내 매물:    {len(new_5min)}건")
print(f"총 소요 시간:     {elapsed_total:.1f}초 ({elapsed_total/60:.1f}분)")
print()
if new_1min:
    print(f"--- 1분 이내 신규 매물 ({len(new_1min)}건) ---")
    for a in sorted(new_1min, key=lambda x: x["created"], reverse=True)[:20]:
        print(f'  [{a["loc"]}] {a["title"]} / {a["price"]:,.0f}원 / {a["created"]}')
if new_5min:
    print(f"--- 5분 이내 신규 매물 ({len(new_5min)}건) ---")
    for a in sorted(new_5min, key=lambda x: x["created"], reverse=True)[:10]:
        print(f'  [{a["loc"]}] {a["title"]} / {a["price"]:,.0f}원 / {a["created"]}')
