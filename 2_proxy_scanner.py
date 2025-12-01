import asyncio
import ssl
import socket
import time
import struct          
import os
from tqdm import tqdm

# ================================ 配置 ================================
TEST_PORTS = [443, 8443, 50001, 50006]
TIMEOUT = 12
MAX_WORKERS = 1000
RESULT_FILE = "proxyip_real_available.txt"


BEST_GLOBAL_CIDRS = [
    "132.145.0.0/16", "129.146.0.0/16", "130.61.0.0/16", "147.154.0.0/16",
    "140.91.0.0/16", "129.213.0.0.0/16", "158.101.0.0/16", "138.2.0.0/16",
    "37.19.192.0/19", "91.149.192.0/18", "185.152.64.0/22",
    "205.185.112.0/20", "192.40.56.0/21",
    "5.75.128.0/17", "65.109.0.0/16", "135.181.0.0/16", "95.216.0.0/16",
    "45.63.0.0/16", "108.61.0.0/16", "149.28.0.0/16", "207.148.64.0/18",
]

# 历史缓存
success_cache = set()
if os.path.exists(RESULT_FILE):
    try:
        with open(RESULT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line and line[0].isdigit():
                    success_cache.add(line.split()[0])
        print(f"已加载 {len(success_cache)} 条历史成功记录")
    except:
        print("读取缓存失败")

# ================================ 终极真实验证函数 ================================
async def is_real_proxy(ip: str, port: int = 443) -> tuple[bool, str, float]:
    start_time = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=False), timeout=TIMEOUT
        )

        # CONNECT
        writer.write(b"CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n")
        await writer.drain()
        resp = await asyncio.wait_for(reader.read(1024), timeout=6)
        if b"200" not in resp:
            writer.close()
            return False, "CONNECT失败", round((time.time()-start_time)*1000)

        # 真实 TLS 握手
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(['h2', 'http/1.1'])

        try:
            ssl_conn = await asyncio.wait_for(
                asyncio.open_connection(
                    host=ip, port=port, ssl=context,
                    server_hostname="speed.cloudflare.com"
                ),
                timeout=10
            )
            ssl_reader, ssl_writer = ssl_conn
        except:
            writer.close()
            return False, "TLS失败", round((time.time()-start_time)*1000)

        # GET /cdn-cgi/trace
        ssl_writer.write(b"GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\n\r\n")
        await ssl_writer.drain()

        data = b""
        for _ in range(10):
            chunk = await asyncio.wait_for(ssl_reader.read(4096), timeout=5)
            if not chunk: break
            data += chunk

        text = data.decode(errors='ignore')
        if not all(x in text for x in ["colo=", "CF-RAY", "cloudflare"]):
            ssl_writer.close()
            writer.close()
            return False, "trace失败", round((time.time()-start_time)*1000)

        colo = text.split("colo=")[1].split("\n")[0] if "colo=" in text else "??"

        latency = round((time.time() - start_time) * 1000)
        ssl_writer.close()
        writer.close()
        return True, f"colo={colo}", latency

    except:
        return False, "连接失败", -1

# ================================ 生成候选 ================================
def generate_candidates():
    seen = set()
    total = 0
    for cidr in BEST_GLOBAL_CIDRS:
        try:
            net, mask = cidr.split('/')
            start = struct.unpack(">I", socket.inet_aton(net))[0]
            size = 1 << (32 - int(mask))
            step = max(1, size // 500)
            for i in range(0, size, step):
                ip_int = (start + i) & 0xFFFFFFFF
                ip = socket.inet_ntoa(struct.pack(">I", ip_int))
                for p in TEST_PORTS:
                    key = f"{ip}:{p}"
                    if key not in success_cache and key not in seen:
                        seen.add(key)
                        total += 1
                        yield ip, p
        except Exception as e:
            print(f"[!] CIDR 解析失败: {cidr} → {e}")
            continue
    print(f"成功生成 {total} 个候选目标")

candidates = list(generate_candidates())
print(f"\n开始扫描 {len(candidates):,} 个目标...\n")

# ================================ 主扫描 ================================
async def main():
    if not candidates:
        print("无新目标")
        return

    results = []
    sem = asyncio.Semaphore(MAX_WORKERS)

    async def worker(pair):
        ip, port = pair
        async with sem:
            ok, msg, lat = await is_real_proxy(ip, port)
            if ok:
                line = f"{ip}:{port}  {lat}ms  {msg}"
                results.append(line)
                success_cache.add(f"{ip}:{port}")
                print(f"\n[+] 真·可用！ {line}")

    tasks = [worker(p) for p in candidates]

    pbar = tqdm(total=len(tasks), desc="真实可用扫描", colour="green")
    for f in asyncio.as_completed(tasks):
        await f
        pbar.update(1)
    pbar.close()

    if results:
        with open(RESULT_FILE, "a", encoding="utf-8") as f:
            for line in sorted(results, key=lambda x: int(x.split()[1][:-2])):
                f.write(line + "\n")
        print(f"\n本次新增 {len(results)} 条真正可用的 ProxyIP！")
        print("最快 Top 20：")
        for line in sorted(results, key=lambda x: int(x.split()[1][:-2]))[:20]:
            print("  " + line)
    else:
        print("\n本次未发现新可用 ProxyIP")

if __name__ == "__main__":
    asyncio.run(main())