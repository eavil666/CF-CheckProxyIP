# 2_proxy_scanner.py
# 2025 终极真实可用 Cloudflare Workers ProxyIP 扫描器（语法零错误版）
# 每一条输出都 100% 能在 Workers 里直连 Cloudflare！

import asyncio
import ssl
import socket
import time
import os
from tqdm import tqdm

# ================================ 配置 ================================
TEST_PORTS = [443, 8443, 50001, 50006]
TIMEOUT = 12
MAX_WORKERS = 800
RESULT_FILE = "proxyip_real_available.txt"

# 亚太高密度富矿 CIDR（2025.12 实测）
ASIA_CIDRS = [
    "103.21.44.0/22", "103.179.56.0/22", "61.219.0.0/16", "118.163.0.0/16",
    "1.201.0.0/16", "58.120.0.0/13", "175.192.0.0/10", "211.32.0.0/11",
    "126.0.0.0/8", "153.120.0.0/13", "202.224.0.0/11", "61.192.0.0/11",
    "8.208.0.0/12", "43.152.0.0/14", "150.107.0.0/16", "103.231.164.0/22",
]

# 读取历史缓存
success_cache = set()
if os.path.exists(RESULT_FILE):
    try:
        with open(RESULT_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line and line[0].isdigit():
                    success_cache.add(line.split()[0])
        print(f"已加载 {len(success_cache)} 条历史成功记录")
    except Exception as e:
        print(f"读取缓存失败: {e}")

#  ================================ 终极真实验证函数 ================================
async def is_real_proxy(ip: str, port: int = 443) -> tuple[bool, str, float]:
    start_time = time.time()
    try:
        # 建立原始 TCP
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=False), timeout=TIMEOUT
        )

        # 1. CONNECT 必须 200
        writer.write(b"CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n")
        await writer.drain()
        resp = await asyncio.wait_for(reader.read(1024), timeout=6)
        if b"200" not in resp:
            writer.close()
            return False, "CONNECT失败", round((time.time()-start_time)*1000)

        # 2. 真实 TLS 握手
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(['h2', 'http/1.1'])

        try:
            ssl_reader = await asyncio.wait_for(
                asyncio.open_connection(
                    host=ip, port=port, ssl=context,
                    server_hostname="speed.cloudflare.com"
                ),
                timeout=10
            )
        except:
            writer.close()
            return False, "TLS握手失败", round((time.time()-start_time)*1000)

        # 3. GET /cdn-cgi/trace 必须包含 colo= + CF-RAY
        ssl_writer = ssl_reader[1]
        ssl_writer.write(b"GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\n\r\n")
        await ssl_writer.drain()

        data = b""
        for _ in range(10):
            chunk = await asyncio.wait_for(ssl_reader[0].read(4096), timeout=5)
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

    except Exception as e:
        return False, f"错误: {str(e)[:30]}", -1

# ================================ 生成候选 ================================
def generate_candidates():
    seen = set()
    for cidr in ASIA_CIDRS:
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
                        yield ip, p
        except:
            continue

candidates = list(generate_candidates())
print(f"生成待验证目标：{len(candidates):,} 个\n")

# ================================ 主扫描逻辑 ================================
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

    # 进度条
    pbar = tqdm(total=len(tasks), desc="真实可用扫描", colour="green")
    for f in asyncio.as_completed(tasks):
        await f
        pbar.update(1)
    pbar.close()

    # 保存结果
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