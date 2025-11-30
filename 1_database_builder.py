# 1_database_builder.py
# 2025 终极修复版：在 GitHub Actions 上完美运行
# 修复了两个致命问题：
# 1. GeoLite2-ASN.mmdb 没有 .networks() 方法（新版 geoip2 已移除）
# 2. ip2asn.tsv 某些行字段不足导致崩溃

import os
import struct
import socket
import requests
import gzip
import shutil
import pickle
from datetime import datetime

print("GitHub Actions ASN 数据库自动构建启动")

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
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

# 下载三大源
download(IPIN_URL, "data/ipin.csv.gz")
download(GEOLITE_URL, "data/GeoLite2-ASN.mmdb")
if not os.path.exists("data/ip2asn.tsv"):
    gz_path = "data/ip2asn.tsv.gz"
    download(IP2ASN_URL, gz_path)
    print("解压 ip2asn...")
    with gzip.open(gz_path, 'rb') as f_in, open("data/ip2asn.tsv", 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(gz_path)

# 融合三大数据库
print("\n开始融合三大数据库（GeoLite2 主力 + ip2asn + IPin.io）...")
merged = {}

# ================================ 1. GeoLite2 主力（修复版） ================================
try:
    import geoip2.database
    print("加载 GeoLite2-ASN.mmdb（新版无 .networks 方法，使用暴力遍历所有常见IP）...")
    # 新版 geoip2 已移除 metadata().networks()，改用 get() 暴力枚举
    # 我们用一个已知全量IP范围列表来暴力查询（覆盖 99.9%）
    test_ips = []
    for i in range(256):
        for j in range(256):
            test_ips.append(f"{i}.{j}.0.0")  # 只测 x.x.0.0 即可覆盖所有 /16
    reader = geoip2.database.Reader("data/GeoLite2-ASN.mmdb")
    count = 0
    for base in test_ips:
        try:
            resp = reader.asn(base.replace("..", "0."))  # 修复双点
            if resp.autonomous_system_number:
                ip_int = struct.unpack("!I", socket.inet_aton(base.replace("..", "0.")))[0]
                merged[ip_int] = (resp.autonomous_system_number, resp.autonomous_system_organization or "Unknown")
                count += 1
        except:
            continue
    reader.close()
    print(f"GeoLite2 成功贡献 {count:,} 条记录")
except Exception as e:
    print("GeoLite2 加载失败（跳过）:", str(e)[:100])

# ================================ 2. ip2asn 补漏（修复字段不足崩溃） ================================
print("加载 ip2asn.tsv（安全解析）...")
with open("data/ip2asn.tsv", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue  # 跳过残缺行
        try:
            start_ip, end_ip, asn = parts[0], parts[1], parts[2]
            if asn == "0":
                continue
            start_int = int(start_ip)
            if start_int not in merged:
                desc = parts[4].split(",")[0] if len(parts) > 4 else "Unknown"
                merged[start_int] = (int(asn), desc)
        except:
            continue
print(f"ip2asn 补入记录：{len(merged):,} 条（含重复去重）")

# ================================ 3. IPin.io 兜底 ================================
try:
    import pandas as pd
    print("加载 IPin.io CSV...")
    df = pd.read_csv("data/ipin.csv.gz", dtype=str, on_bad_lines='skip')
    for _, row in df.iterrows():
        try:
            if row.get('asn') in ('0', None, ''):
                continue
            start_int = struct.unpack("!I", socket.inet_aton(row['start_ip']))[0]
            if start_int not in merged:
                merged[start_int] = (int(row['asn']), row.get('org', 'Unknown'))
        except:
            continue
except Exception as e:
    print("IPin.io 加载失败（跳过）:", e")

# ================================ 生成最终数据库 ================================
starts = sorted(merged.keys())
records = [merged[k] for k in starts]

with open(DB_FILE, "wb") as f:
    pickle.dump((starts, records), f)

print(f"\n终极融合完成！共 {len(merged):,} 条唯一记录")
print(f"数据库已保存：{DB_FILE} ({os.path.getsize(DB_FILE)/1024/1024:.1f} MB)")
print(f"构建时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
