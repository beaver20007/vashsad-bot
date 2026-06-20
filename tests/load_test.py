import asyncio
import aiohttp
import time
from statistics import mean, median, stdev

BASE_URL = 'http://localhost:3000'  # or from env

ENDPOINTS = [
    ('GET', '/api/health', {}),
    ('GET', '/api/plants?limit=20', {}),
    ('GET', '/api/weather', {}),
]

async def single_request(session, method, path, headers={}):
    url = BASE_URL + path
    start = time.monotonic()
    try:
        async with session.request(method, url, headers=headers) as resp:
            await resp.read()
            return time.monotonic() - start, resp.status
    except Exception as e:
        return time.monotonic() - start, 0

async def run_load_test(concurrency=10, total_requests=100):
    results = []
    async with aiohttp.ClientSession() as session:
        for endpoint in ENDPOINTS:
            method, path, headers = endpoint
            tasks = [single_request(session, method, path, headers) for _ in range(total_requests)]
            endpoint_results = await asyncio.gather(*tasks)
            times = [r[0] for r in endpoint_results]
            statuses = [r[1] for r in endpoint_results]
            ok = sum(1 for s in statuses if 200 <= s < 300)
            print(f"{method} {path}:")
            print(f"  Requests: {total_requests}, OK: {ok}, Failed: {total_requests-ok}")
            print(f"  Mean: {mean(times)*1000:.0f}ms, Median: {median(times)*1000:.0f}ms, P95: {sorted(times)[int(len(times)*0.95)]*1000:.0f}ms")
            results.append({'path': path, 'times': times, 'ok': ok})
    return results

if __name__ == '__main__':
    import sys
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    asyncio.run(run_load_test(concurrency, total))
