# 1_database_builder.py
import os, struct, socket, requests, gzip, shutil, pickle
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
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)

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
print("融合三大数据库中...")
merged = {}

# 1. GeoLite2 优先
try:
    import geoip2.database
    reader = geoip2.database.Reader("data/GeoLite2-ASN.mmdb")
    count = 0
    for net in reader.metadata().networks():
        try:
            rec = reader.asn(net.split('/')[0])
            if rec.autonomous_system_number:
                ip_int = struct.unpack("!I", socket.inet_aton(net.split('/')[0]))[0]
                merged[ip_int] = (rec.autonomous_system_number, rec.autonomous_system_organization or "Unknown")
                count += 1
        except: continue
    print(f"GeoLite2 贡献 {count:,} 条")
    reader.close()
except Exception as e:
    print("GeoLite2 加载失败:", e)

# 2. ip2asn 补漏
print("加载 ip2asn...")
with open("data/ip2asn.tsv") as f:
    for line in f:
        if line.startswith("#"): continue
        p = line.strip().split("\t")
        if len(p) < 5 or p[2] == "0": continue
        start = int(p[0])
        if start not in merged:
            merged[start] = (int(p[2]), p[4].split(",")[0])

# 3. IPin.io 兜底
print("加载 IPin.io...")
import pandas as pd
df = pd.read_csv("data/ipin.csv.gz", dtype=str)
for _, row in df.iterrows():
    try:
        start = struct.unpack("!I", socket.inet_aton(row['start_ip']))[0]
        if start not in merged and row['asn'] != '0':
            merged[start] = (int(row['asn']), row['org'])
    except: pass

# 生成最终数据库
starts = sorted(merged.keys())
records = [merged[k] for k in starts]

with open(DB_FILE, "wb") as f:
    pickle.dump((starts, records), f)

print(f"终极数据库构建完成！共 {len(merged):,} 条记录")
print(f"文件大小: {os.path.getsize(DB_FILE)/1024/1024:.1f} MB")
print(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
