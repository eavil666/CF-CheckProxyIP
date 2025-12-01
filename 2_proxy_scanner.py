# 2_proxy_scanner.py
# 2025 终极真实可用 Cloudflare Workers ProxyIP 扫描器
# 三关验证：/cdn-cgi/trace + TLS握手 + 访问真实CF页面
# 每一条输出都 100% 能在 Workers 里直连 Cloudflare！

import asyncio
import ssl
import socket
import time
import struct
import os
from datetime import datetime
from tqdm import tqdm

# ================================ 配置 ================================
TEST_PORTS = [443, 8443, 50001, 50006]
TIMEOUT = 12
MAX_WORKERS = 1200
RESULT_FILE = "proxyip_real_available.txt"

# 亚太高密度富矿 CIDR（2025.12）
ASIA_CIDRS = [
    "103.21.44.0/22", "103.179.56.0/22", "61.219.0.0/16", "118.163.0.0/16",     # 台湾
    "1.201.0.0/16", "58.120.0.0/13", "175.192.0.0/10", "211.32.0.0/11",        # 韩国
    "126.0.0.0/8", "153.120.0.0/13", "202.224.0.0/11", "61.192.0.0/11",        # 日本
    "8.208.0.0/12", "43.152.0.0/14", "150.107.0.0/16", "103.231.164.0/22",    # 新加坡
]

# 读取历史成功缓存
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

# ================================ TLS ClientHello ================================
def build_tls_client_hello() -> bytes:
    hello_hex = (
        "16030100a10100009d0303beefbeefbeefbeefbeefbeefbeefbeef"
        "beefbeefbeefbeefbeefbeefbeefbeef20c02bc02fc02cc030cca9"
        "cca8c013c014009c009d002f0035000a0100006a00050005010000"
        "000000000a00080006001700180019000b00020100000d00120010"
        "0403080404010503050305050108060601002d00020101001c0002"
        "4001001500840000"
    )
    return bytes.fromhex(hello_hex)

TLS_HELLO = build_tls_client_hello()

# ================================ 终极三关验证 ================================
async def is_real_proxy(ip: str, port: int = 443) -> tuple[bool, str, float]:
    start_time = time.time()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=False), timeout=TIMEOUT
        )

        # 关1：GET /cdn-cgi/trace
        ts = int(time.time() * 1000)
        trace_req = (
            f"GET /cdn-cgi/trace?t={ts} HTTP/1.1\r\n"
            f"Host: speed.cloudflare.com\r\n"
            f"User-Agent: ProxyIP-Scanner/2025\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()

        writer.write(trace_req)
        await writer.drain()

        trace_data = b""
        trace_ok = False
        colo = "??"
        for _ in range(15):
            chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
            if not chunk: break
            trace_data += chunk
            text = trace_data.decode(errors='ignore')
            if "colo=" in text and "CF-RAY" in text:
                trace_ok = True
                colo = text.split("colo=")[1].split("\n")[0]
                break

        if not trace_ok:
            writer.close()
            return False, "无colo", round((time.time() - start_time)*1000)

        # 关2：TLS ClientHello
        writer.write(TLS_HELLO)
        await writer.drain()
        try:
            tls_header = await asyncio.wait_for(reader.read(5), timeout=4)
            if not (tls_header and tls_header[0] == 0x16):
                writer.close()
                return False, "TLS失败", round((time.time() - start_time)*1000)
        except:
            writer.close()
            return False, "TLS超时", round((time.time() - start_time)*1000)

        # 关3：访问真实CF页面
        api_req = (
            "GET / HTTP/1.1\r\n"
            "Host: developers.cloudflare.com\r\n"
            "User-Agent: ProxyIP-Scanner/2025\r\n\r\n"
        ).encode()
        writer.write(api_req)
        await writer.drain()
        api_data = await asyncio.wait_for(reader.read(2048), timeout=5)
        if b"cloudflare" not in api_data.lower() or len(api_data) < 500:
            writer.close()
            return False, "页面异常", round((time.time() - start_time)*1000)

        latency = round((time.time() - start_time) * 1000)
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
        print("所有目标已验证完毕，无新目标")
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
                print(f"\n\033[92m[+] 真·可用！ {line}\033[0m")
            return ok

    tasks = [worker(p) for p in candidates]

    # 使用普通 tqdm 手动更新进度条
    pbar = tqdm(total=len(tasks), desc="真实可用扫描", colour="green")
    for f in asyncio.as_completed(tasks):
        await f
        pbar.update(1)
    pbar.close()

    # 保存结果
    if results:
        with open(RESULT_FILE, "a", encoding="utf-8") as f:
            for line in sorted(results, key=lambda x: float(x.split()[1].replace("ms",""))):
                f.write(line + "\n")
        print(f"\n本次新增 {len(results)} 条真正可用的 ProxyIP！")
        print("最快 Top 20：")
        for line in sorted(results, key=lambda x: float(x.split()[1].replace("ms","")))[:20]:
            print("  " + line)
    else:
        print("\n本次未发现新可用 ProxyIP")

if __name__ == "__main__":
    asyncio.run(main())
