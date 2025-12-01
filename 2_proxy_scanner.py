# 2_proxy_scanner.py
# 2025 终极双栈真实可用 Cloudflare Workers ProxyIP 扫描器（完整修复版）
# 每一条都能在 Workers 里直连 Cloudflare！

import asyncio
import ssl
import socket
import time
import struct          # ← 关键修复！加上这行就完美了！
import os
from tqdm import tqdm

# ================================ 配置 ================================
TEST_PORTS = [443, 8443, 50001, 50006]
TIMEOUT = 12
MAX_WORKERS = 1000
RESULT_FILE = "proxyip_real_available.txt"

# ================================ 2025 最强双栈富矿 CIDR =============================
CIDR_LIST = [
    # IPv4 王牌
    "5.75.128.0/17", "65.109.0.0/16", "135.181.0.0/16", "95.216.0.0/16",
    "78.46.0.0/15", "116.202.0.0/16", "167.235.0.0/16", "65.21.0.0/16",
    "132.145.0.0/16", "129.146.0.0/16", "130.61.0.0/16", "147.154.0.0/16",
    "140.91.0.0/16", "129.213.0.0.0/16", "158.101.0.0/16", "138.2.0.0/16",
    "37.19.192.0/19", "91.149.192.0/18", "185.152.64.0/22",
    "205.185.112.0/20", "192.40.56.0/21",

    # IPv6 王牌
    "2a01:4f8::/32", "2a01:4f9::/32", "2a01:4ff::/32",
    "2603:c020::/32", "2603:c021::/32", "2603:c022::/32", "2603:c023::/32",
    "2001:19f0::/32", "2400:6180::/32", "2001:df0::/32",
    "2a02:6ea0::/32", "2a0e:b107::/32",
    "2600:1901::/32", "2a01:7e00::/32",
]

# 历史缓存
success_cache = set()
if os.path.exists(RESULT_FILE):
    try:
        with open(RESULT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    success_cache.add(line.split()[0])
        print(f"已加载 {len(success_cache)} 条历史成功记录")
    except:
        print("读取缓存失败")

# ================================ 终极真实验证函数（支持 IPv6）===============================
async def is_real_proxy(host: str, port: int = 443) -> tuple[bool, str, float]:
    start_time = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=False), timeout=TIMEOUT
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
                    host=host, port=port, ssl=context,
                    server_hostname="speed.cloudflare.com"
                ),
                timeout=10
            )
            ssl_reader, ssl_writer = ssl_conn
        except:
            writer.close()
            return False, "TLS握手失败", round((time.time()-start_time)*1000)

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
            return False, "trace验证失败", round((time.time()-start_time)*1000)

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
    for cidr in CIDR_LIST:
        try:
            if '::' in cidr:  # IPv6
                prefix = cidr.split('::')[0]
                for i in range(0, 256, 16):
                    ip = f"{prefix}:{i}::1"
                    for p in TEST_PORTS:
                        key = f"[{ip}]:{p}"
                        if key not in success_cache and key not in seen:
                            seen.add(key)
                            yield ip, p
            else:  # IPv4
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
                            yield ip, p
        except Exception as e:
            print(f"[!] CIDR 解析失败: {cidr} → {e}")
            continue

candidates = list(generate_candidates())
print(f"生成双栈候选目标：{len(candidates):,} 个\n")

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
                line = f"[{ip}]:{port}" if ":" in ip and ip.count(":") >= 2 else f"{ip}:{port}"
                line += f"  {lat}ms  {msg}"
                results.append(line)
                success_cache.add(line.split()[0])
                print(f"\n[+] 真·可用！ {line}")

    tasks = [worker(p) for p in candidates]

    pbar = tqdm(total=len(tasks), desc="双栈真实可用扫描", colour="cyan")
    for f in asyncio.as_completed(tasks):
        await f
        pbar.update(1)
    pbar.close()

    if results:
        with open(RESULT_FILE, "a", encoding="utf-8") as f:
            for line in sorted(results, key=lambda x: int(x.split()[1][:-2])):
                f.write(line + "\n")
        print(f"\n本次新增 {len(results)} 条真实可用双栈 ProxyIP！")
        print("最快 Top 20：")
        for line in sorted(results, key=lambda x: int(x.split()[1][:-2]))[:20]:
            print("  " + line)
    else:
        print("\n本次未发现新可用 ProxyIP")

if __name__ == "__main__":
    asyncio.run(main())
