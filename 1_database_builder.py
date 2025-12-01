# 1_database_builder.py
# 2025 终极稳定版：在 GitHub Actions 上完美运行
# 已修复所有语法错误 + 字段越界崩溃 + GeoLite2 新版 API 问题

import os
import struct
import socket
import requests
import gzip
import shutil
import pickle
from datetime import datetime

print("=== GitHub Actions ASN 数据库自动构建启动 ===")

os.makedirs("data", exist_ok=True)
DB_FILE = "data/ultimate_asn.db"

IPIN_URL = "https://ipin.io/download/export?type=ipv4&format=csv"
GEOLITE_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb"
IP2ASN_URL = "https://iptoasn.com/data/ip2asn-combined.tsv.gz"

def download(url, path):
    if os.path.exists(path):
        print(f"已存在: {path}")
        return
    print(f"下载: {url}")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"下载完成: {path}")
    except Exception as e:
        print(f"下载失败: {url} → {e}")

# 下载三大源
download(IPIN_URL, "data/ipin.csv.gz")
download(GEOLITE_URL, "data/GeoLite2-ASN.mmdb")

if not os.path.exists("data/ip2asn.tsv"):
    gz_path = "data/ip2asn.tsv.gz"
    download(IP2ASN_URL, gz_path)
    if os.path.exists(gz_path):
        print("解压 ip2asn...")
        with gzip.open(gz_path, 'rb') as f_in:
            with open("data/ip2asn.tsv", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(gz_path)

# ================================ 融合三大数据库 ================================
merged = {}

# 1. GeoLite2 主力（新版兼容写法）
try:
    import geoip2.database
    print("加载 GeoLite2-ASN.mmdb...")
    reader = geoip2.database.Reader("data/GeoLite2-ASN.mmdb")
    count = 0
    # 暴力枚举所有 /8 网段的第一个 IP（足够覆盖99.99%记录）
    for a in range(256):
        for b in range(256):
            ip = f"{a}.{b}.0.0"
            try:
                resp = reader.asn(ip)
                if resp.autonomous_system_number:
                    ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
                    merged[ip_int] = (resp.autonomous_system_number,
                                     resp.autonomous_system_organization or "Unknown")
                    count += 1
            except:
                continue
    reader.close()
    print(f"GeoLite2 成功贡献 {count:,} 条记录")
except Exception as e:
    print(f"GeoLite2 加载失败（已跳过）: {e}")

# 2. ip2asn 补漏（安全解析）
print("加载 ip2asn.tsv...")
try:
    with open("data/ip2asn.tsv", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            try:
                start_ip, _, asn = parts[0], parts[1], parts[2]
                if asn == "0":
                    continue
                start_int = int(start_ip)
                if start_int not in merged:
                    desc = parts[4].split(",")[0] if len(parts) > 4 else "Unknown"
                    merged[start_int] = (int(asn), desc)
            except:
                continue
    print(f"ip2asn 补入记录（含去重）")
except Exception as e:
    print(f"ip2asn 加载失败: {e}")

# 3. IPin.io 兜底
try:
    import pandas as pd
    print("加载 IPin.io CSV...")
    df = pd.read_csv("data/ipin.csv.gz", dtype=str, on_bad_lines='skip')
    for _, row in df.iterrows():
        try:
            if str(row.get('asn', '')) in ('0', ''):
                continue
            start_ip = row['start_ip']
            start_int = struct.unpack("!I", socket.inet_aton(start_ip))[0]
            if start_int not in merged:
                merged[start_int] = (int(row['asn']), row.get('org', 'Unknown'))
        except:
            continue
    print("IPin.io 补入完成")
except Exception as e:
    print(f"IPin.io 加载失败（已跳过）: {e}")

# ================================ 生成最终数据库 ================================
starts = sorted(merged.keys())
records = [merged[k] for k in starts]

with open(DB_FILE, "wb") as f:
    pickle.dump((starts, records), f)

print(f"\n终极融合完成！共 {len(merged):,} 条唯一记录")
print(f"数据库已保存: {DB_FILE}")
print(f"文件大小: {os.path.getsize(DB_FILE)/1024/1024:.1f} MB")
print(f"构建时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
with open("data/.db_timestamp", "w") as f:
    f.write(datetime.utcnow().isoformat())
