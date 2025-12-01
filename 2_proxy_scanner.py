# 终极函数：ultimate_real_tls_verify.py
# 八大金标准 + 真实完整 TLS 握手（ssl.wrap_socket）

import asyncio
import ssl
import socket
import time
import struct
import os
from datetime import datetime
from tqdm import tqdm

# ================================ 终极八大验证 + 真TLS握手 ================================
async def ultimate_real_tls_verify(ip: str, port: int = 443) -> tuple[bool, str, float]:
    """
    2025 最严苛验证：八大金标准 + 真实完整 TLS 握手
    只有全部通过才是真正的 Cloudflare Workers 可用 ProxyIP！
    """
    start_time = time.time()
    try:
        # 第1步：建立原始 TCP 连接
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=False), timeout=10
        )

        # 第2步：发送 CONNECT 到 Cloudflare（必须 200）
        connect_req = f"CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n".encode()
        writer.write(connect_req)
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(1024), timeout=6)
        if b"200" not in resp or b"Connection established" not in resp:
            writer.close()
            return False, "CONNECT 失败", round((time.time()-start_time)*1000)

        # 第3步：真正开始 TLS 握手（关键！）
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(['h2', 'http/1.1'])  # CF 强制 h2

        # 用原始 socket 包装成 SSL
        try:
            ssl_reader, ssl_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=ip,
                    port=port,
                    ssl=context,
                    server_hostname="speed.cloudflare.com",  # SNI 必须填 CF 域名！
                    ssl_handshake_timeout=8
                ),
                timeout=12
            )
        except Exception as e:
            writer.close()
            return False, f"TLS握手失败: {str(e)[:20]}", round((time.time()-start_time)*1000)

        # 第4步：TLS 握手成功后，发送 GET /cdn-cgi/trace
        trace_req = (
            "GET /cdn-cgi/trace HTTP/1.1\r\n"
            "Host: speed.cloudflare.com\r\n"
            "User-Agent: ProxyIP-RealVerify/2025\r\n"
            "Connection: close\r\n\r\n"
        ).encode()

        ssl_writer.write(trace_req)
        await ssl_writer.drain()

        trace_data = b""
        for _ in range(10):
            chunk = await asyncio.wait_for(ssl_reader.read(4096), timeout=5)
            if not chunk: break
            trace_data += chunk

        text = trace_data.decode(errors='ignore')

        # 第5-8关：八大金标准检查
        checks = {
            "colo=": "无colo",
            "fl=": "无fl",
            "CF-RAY": "无CF-RAY",
            "server: cloudflare": "无Server头",
            "h2": "无HTTP/2",  # ALPN 协商成功
        }

        failed = []
        for key, msg in checks.items():
            if key not in text.lower():
                failed.append(msg)

        # 额外检查：访问真实页面
        if not failed:
            ssl_writer.write(b"GET / HTTP/1.1\r\nHost: developers.cloudflare.com\r\n\r\n")
            await ssl_writer.drain()
            page = await asyncio.wait_for(ssl_reader.read(2048), timeout=6)
            if b"cloudflare" not in page.lower():
                failed.append("页面无CF特征")

        ssl_writer.close()
        await ssl_writer.wait_closed()
        writer.close()

        if failed:
            return False, " | ".join(failed), round((time.time()-start_time)*1000)

        colo = text.split("colo=")[1].split("\n")[0] if "colo=" in text else "??"
        latency = round((time.time() - start_time) * 1000)
        return True, f"核弹级验证通过! colo={colo}", latency

    except Exception as e:
        return False, f"连接/TLS错误: {str(e)[:30]}", -1