# 1_database_builder.py
# 2025 终极双栈 ASN 数据库构建器（支持 IPv4 + IPv6）
# 自动下载三大源 → 融合 → 输出 ultimate_asn.db（支持 IPv6 查询）

import os
import struct
import socket
import requests
import gzip
import shutil
import pickle
from datetime import datetime, timezone

print("=== 2025 双栈 ASN 数据库构建启动 ===")

os.makedirs("data", exist_ok=True)
DB_FILE = "data/ultimate_asn.db"

# ==================== 下载源（已支持 IPv6）===================
IPIN_V4_URL = "https://ipin.io/download/export?type=ipv4&format=csv"
IPIN_V6_URL = "https://ipin.io/download/export?type=ipv6&format=csv"
GEOLITE_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb"
IP2ASN_V4_URL = "https://iptoasn.com/data/ip2asn-v4.tsv.gz"
IP2ASN_V6_URL = "https://iptoasn.com/data/ip2asn-v6.tsv.gz"

def download(url, path):
    if os.path.exists(path):
        print(f"已存在: {path}")
        return
    print(f"下载: {url}")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        print(f"完成: {path}")
    except Exception as e:
        print(f"失败: {url} → {e}")

# 下载所有文件
download(IPIN_V4_URL, "data/ipin_v4.csv.gz")
download(IPIN_V6_URL, "data/ipin_v6.csv.gz")
download(GEOLITE_URL, "data/GeoLite2-ASN.mmdb")
download(IP2ASN_V4_URL, "data/ip2asn-v4.tsv.gz")
download(IP2ASN_V6_URL, "data/ip2asn-v6.tsv.gz")

# 解压 TSV
for gz in ["data/ip2asn-v4.tsv.gz", "data/ip2asn-v6.tsv.gz"]:
    if os.path.exists(gz):
        out = gz.replace(".gz", "")
        if not os.path.exists(out):
            print(f"解压 {gz}...")
            with gzip.open(gz, 'rb') as f_in, open(out, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(gz)

# ==================== 融合三大源（支持 IPv6）===================
merged = {}  # key: ip_str (v4/v6) → (asn, org)

# 1. GeoLite2 主力（最准，支持 IPv6）
try:
    import geoip2.database
    print("加载 GeoLite2-ASN.mmdb（支持 IPv6...")
    reader = geoip2.database.Reader("data/GeoLite2-ASN.mmdb")
    # 暴力遍历常见前缀（v4 + v6）
    prefixes = [
        "0.0.0.0", "128.0.0.0", "192.0.0.0", "224.0.0.0",
        "::", "2000::", "2400::", "2600::", "2800::", "2a00::", "2c00::"
    ]
    for p in prefixes:
        try:
            resp = reader.asn(p)
            if resp.autonomous_system_number:
                merged[p] = (resp.autonomous_system_number, resp.autonomous_system_organization or "Unknown")
        except:
            continue
    reader.close()
    print(f"GeoLite2 贡献记录")
except Exception as e:
    print(f"GeoLite2 加载失败: {e}")

# 2. ip2asn 补全（v4 + v6）
print("加载 ip2asn v4 + v6...")
for file in ["data/ip2asn-v4.tsv", "data/ip2asn-v6.tsv"]:
    if not os.path.exists(file): continue
    with open(file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("#"): continue
            parts = line.strip().split("\t")
            if len(parts) < 5 or parts[2] == "0": continue
            start_ip = parts[0]
            if start_ip not in merged:
                merged[start_ip] = (int(parts[2]), parts[4].split(",")[0])

# 3. IPin.io 兜底（v4 + v6）
try:
    import pandas as pd
    for file in ["data/ipin_v4.csv.gz", "data/ipin_v6.csv.gz"]:
        if not os.path.exists(file): continue
        print(f"加载 {file}...")
        df = pd.read_csv(file, dtype=str, on_bad_lines='skip')
        for _, row in df.iterrows():
            ip = row['start_ip']
            if ip in merged or row.get('asn', '0') == '0': continue
            merged[ip] = (int(row['asn']), row.get('org', 'Unknown'))
except Exception as e:
    print(f"IPin.io 加载失败: {e}")

# ==================== 生成双栈数据库（支持 IPv4/IPv6 精确查询）===================
# key: (family, ip_int_or_bytes) → (asn, org)
final_db = {}

def ip_to_key(ip_str: str):
    try:
        if ':' in ip_str:  # IPv6
            return ('v6', socket.inet_pton(socket.AF_INET6, ip_str))
        else:  # IPv4
            return ('v4', struct.unpack(">I", socket.inet_aton(ip_str))[0])
    except:
        return None

print("构建双栈精确数据库...")
for ip_str, (asn, org) in merged.items():
    key = ip_to_key(ip_str)
    if key:
        final_db[key] = (asn, org)

# 保存为 pickle（超快查询）
with open(DB_FILE, "wb") as f:
    pickle.dump(final_db, f)

print(f"\n双栈数据库构建完成！共 {len(final_db):,} 条记录（IPv4 + IPv6）")
print(f"文件大小: {os.path.getsize(DB_FILE)/1024/1024:.1f} MB")
print(f"构建时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")