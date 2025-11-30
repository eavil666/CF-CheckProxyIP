# 2_proxy_scanner.py
# 只干一件事：用 ultimate_asn.db 疯狂扫亚太多端口
# 依赖：tqdm + 标准库

import asyncio, ssl, socket, time, struct, pickle, os
from tqdm.asyncio import tqdm_asyncio
from datetime import datetime

DB_FILE = "data/ultimate_asn.db"
RESULT_FILE = "proxyip_asia_final.txt"
TEST_PORTS = [443, 8443, 50001, 50006]
MAX_WORKERS = 1500

# 加载超快 ASN 数据库
print("加载终极ASN数据库...")
with open(DB_FILE, "rb") as f:
    STARTS, RECORDS = pickle.load(f)
print(f"数据库就绪：{len(STARTS):,} 条记录")

def query_asn(ip: str) -> tuple:
    n = struct.unpack("!I", socket.inet_aton(ip))[0]
    # 二分查找
    l, r = 0, len(STARTS)-1
    while l <= r:
        m = (l + r) // 2
        if STARTS[m] <= n:
            if m == len(STARTS)-1 or STARTS[m+1] > n:
                asn, org = RECORDS[m]
                return asn, org
            l = m + 1
        else:
            r = m - 1
    return 0, "Unknown"

# 读取历史成果（精确到端口）
cache = set()
if os.path.exists(RESULT_FILE):
    with open(RESULT_FILE) as f:
        cache = {l.split()[0] for l in f if ":" in l}

# 亚太高密度 CIDR（从你的历史经验 + IPin 精选）
ASIA_CIDRS = [
    "103.21.44.0/22","103.179.56.0/22","61.219.0.0/16","118.163.0.0/16",  # TW
    "1.201.0.0/16","58.120.0.0/13","110.8.0.0/13","175.192.0.0/10",        # KR
    "126.0.0.0/8","153.120.0.0/13","202.224.0.0/11","61.192.0.0/11",       # JP
    "8.208.0.0/12","43.152.0.0/14","150.107.0.0/16","103.231.164.0/22",    # SG
    # 加上你之前跑出来的所有富矿网段
]

def generate_ips():
    ips = set()
    for cidr in ASIA_CIDRS:
        try:
            ip, mask = cidr.split('/')
            start = struct.unpack('>I', socket.inet_aton(ip))[0]
            size = 1 << (32 - int(mask))
            step = max(1, size // 400)
            for i in range(0, size, step):
                cur_ip = socket.inet_ntoa(struct.pack('>I', (start + i) & 0xFFFFFFFF))
                for port in TEST_PORTS:
                    key = f"{cur_ip}:{port}"
                    if key not in cache:
                        yield cur_ip, port
        except: continue

candidates = list(generate_ips())
print(f"生成待扫目标：{len(candidates):,} 个")

async def check(ip: str, port: int):
    try:
        start = time.time()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        await asyncio.wait_for(asyncio.open_connection(ip, port, ssl=ctx), timeout=7)
        lat = round((time.time()-start)*1000,1)
        asn, org = query_asn(ip)
        return f"{ip}:{port}  {lat}ms  AS{asn} {org}"
    except:
        return None

async def main():
    results = []
    sem = asyncio.Semaphore(MAX_WORKERS)
    async def worker(pair):
        async with sem:
            return await check(pair[0], pair[1])

    tasks = [worker(p) for p in candidates]
    for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="极速收割", colour="cyan"):
        r = await f
        if r:
            results.append(r)
            print(f"\r\033[92m[+] {r}\033[0m", end="", flush=True)

    if results:
        with open(RESULT_FILE, "a") as f:
            for line in results:
                f.write(line + "\n")
        print(f"\n\n本次新增 {len(results)} 条！累计 {len(cache)+len(results)} 条")

if __name__ == "__main__":
    asyncio.run(main())
