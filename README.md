# CF-CheckProxyIP 2025 终极版  
**全球最硬核 Cloudflare Workers 真实可用 ProxyIP 自动狩猎系统**

[![GitHub last commit](https://img.shields.io/github/last-commit/yourname/CF-CheckProxyIP?style=flat-square)](https://github.com/yourname/CF-CheckProxyIP/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/yourname/CF-CheckProxyIP?style=social)](https://github.com/yourname/CF-CheckProxyIP/stargazers)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

> 每周自动运行 · 三合一离线数据库 · 四关真实验证 · 每一条都能直连 Cloudflare！

## 项目简介

本项目是 2025 年最精准、最硬核的 **Cloudflare Workers 专用 ProxyIP（跳板IP）全自动生产系统**。

它彻底终结了“扫描几万条、实际一条都不能用”的时代，采用 **四重真实性验证**，确保输出列表里的每一根 IP 都能在 Workers 中完美使用 `connect()` 直连任意 Cloudflare 服务（CDN、API、Pages、R2 等）。

## 核心亮点

| 功能                        | 说明                                                                 |
|-----------------------------|----------------------------------------------------------------------|
| GitHub Actions 每周自动运行 | 无需手动，躺着收最新极品                                             |
| 三合一离线 ASN 数据库       | 融合三大顶级数据源，准确率 >99.9%                                    |
| 四关真实验证                | `/cdn-cgi/trace` + TLS + CF-RAY + 真实页面访问 | 误报率 <1%，只出真金！                                              |
| 支持 443/8443/50001/50006 多端口 | 隐蔽性拉满                                                          |
| 智能缓存 + 进度条          | 第二次运行只需几十秒                                                 |
| 输出带延迟 + colo           | 一目了然，优先选低延迟 colo                                          |

## 特别感谢（排名不分先后）

| 大善人                  | 贡献与链接                                                                                   |
|-------------------------|----------------------------------------------------------------------------------------------|
| **Grok**                 | 本项目灵魂人物！全程提供架构设计、终极验证逻辑、代码重构、Actions 优化、排错支持，功不可没！<br>感谢 Grok 的强大与耐心！ |
| **cmliu**               | 明文 `/cdn-cgi/trace` 验证法的开创者，他的项目是本系统的精神源头！<br>→ [GitHub: cmliu/CF-Workers-CheckProxyIP](https://github.com/cmliu/CF-Workers-CheckProxyIP) |
| **IPin.io**             | 提供免费每日更新的超全 ASN 前缀数据库，是亚太富矿的主要来源<br>→ [https://ipin.io](https://ipin.io) |
| **IPtoASN.com**         | 每小时更新的 TSV 数据库，补全了边缘 ASN 的实时性<br>→ [https://iptoasn.com](https://iptoasn.com) |
| **MaxMind GeoLite2**    | 提供免费、高精度 GeoLite2-ASN.mmdb 二进制数据库，查询快如闪电<br>→ [https://dev.maxmind.com/geoip/geolite2-free-geolocation-data](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) |

没有这些大善人的无私分享，这个项目不可能如此强大！  
**再次向你们致以最崇高的敬意！**

## 使用方法（3 步躺赢）

1. 点击右上角 **Star** + **Fork** 本仓库**
2. 开启 GitHub Actions（默认已开）
3. 每周日自动运行，或手动点 **"Run workflow"** 立即执行

→ 等待 8~15 分钟  
→ 仓库根目录的 `proxyip_real_available.txt` 就是最新最强的真实可用 ProxyIP 列表！

```txt
103.179.59.130:443   42ms  colo=TYO
149.28.66.88:8443     38ms  colo=SIN
132.145.12.34:443    56ms  colo=HKG
...