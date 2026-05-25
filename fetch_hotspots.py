#!/usr/bin/env python3
"""
三站热点日报自动抓取脚本
- V2EX: 通过官方 API 获取热门话题
- Linux.do: 通过 Discourse API + RSS 获取热门话题
- NodeSeek: 通过 RSS Feed 获取最新帖子
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ========== 配置 ==========
CST = timezone(timedelta(hours=8))
TODAY = datetime.now(CST).strftime("%Y-%m-%d")
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)
REPORT_FILE = REPORT_DIR / f"{TODAY}.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

V2EX_API = "https://www.v2ex.com/api/topics/hot.json"
LINUXDO_TOP_API = "https://linux.do/top/weekly.json"
LINUXDO_LATEST_API = "https://linux.do/latest.json?no_definitions=true"
LINUXDO_RSS = "https://linux.do/top.rss?period=weekly"
NODESEEK_RSS = "https://rss.nodeseek.com/"


def fetch_with_retry(url, retries=3, timeout=15, headers=None, **kwargs):
    """带重试的请求"""
    req_headers = headers or HEADERS
    for i in range(retries):
        try:
            resp = requests.get(url, headers=req_headers, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"  [重试 {i+1}/{retries}] 请求 {url} 失败: {e}")
            time.sleep(2)
    return None


def parse_rss(xml_text):
    """解析 RSS/Atom feed，返回条目列表"""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0 格式
    for item in root.iter("item"):
        entry = {}
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        author_el = item.find("author")
        pubdate_el = item.find("pubDate")

        entry["title"] = title_el.text.strip() if title_el is not None and title_el.text else ""
        entry["url"] = link_el.text.strip() if link_el is not None and link_el.text else ""
        entry["desc"] = desc_el.text.strip()[:200] if desc_el is not None and desc_el.text else ""
        entry["author"] = author_el.text.strip() if author_el is not None and author_el.text else ""
        entry["pubDate"] = pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else ""
        if entry["title"]:
            items.append(entry)

    # Atom 格式
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        item = {}
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        summary_el = entry.find("atom:summary", ns)
        author_el = entry.find("atom:author/atom:name", ns)
        updated_el = entry.find("atom:updated", ns)

        item["title"] = title_el.text.strip() if title_el is not None and title_el.text else ""
        item["url"] = link_el.get("href", "") if link_el is not None else ""
        item["desc"] = summary_el.text.strip()[:200] if summary_el is not None and summary_el.text else ""
        item["author"] = author_el.text.strip() if author_el is not None and author_el.text else ""
        item["pubDate"] = updated_el.text.strip() if updated_el is not None and updated_el.text else ""
        if item["title"]:
            items.append(item)

    return items


# ========== V2EX ==========
def fetch_v2ex_hot():
    """通过 V2EX 官方 API 获取热门话题"""
    print("📡 正在抓取 V2EX 热门...")
    resp = fetch_with_retry(V2EX_API)
    if not resp:
        print("  ❌ V2EX API 请求失败，尝试备用方案...")
        return _fetch_v2ex_fallback()

    try:
        topics = resp.json()
    except json.JSONDecodeError:
        print("  ❌ V2EX API 返回数据解析失败")
        return _fetch_v2ex_fallback()

    results = []
    for t in topics[:20]:
        results.append({
            "title": t.get("title", ""),
            "node": t.get("node", {}).get("title", ""),
            "replies": t.get("replies", 0),
            "url": t.get("url", ""),
            "member": t.get("member", {}).get("username", ""),
            "created": t.get("created", 0),
        })

    print(f"  ✅ 获取到 {len(results)} 条 V2EX 热门话题")
    return results


def _fetch_v2ex_fallback():
    """V2EX 备用方案：抓取页面"""
    resp = fetch_with_retry("https://www.v2ex.com/?tab=hot")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    items = soup.select(".cell.item")
    for item in items[:20]:
        title_el = item.select_one(".item_title a")
        node_el = item.select_one(".node")
        reply_el = item.select_one(".count_livid, .count_orange")

        if title_el:
            results.append({
                "title": title_el.get_text(strip=True),
                "node": node_el.get_text(strip=True) if node_el else "",
                "replies": int(reply_el.get_text(strip=True)) if reply_el and reply_el.get_text(strip=True).isdigit() else 0,
                "url": "https://www.v2ex.com" + title_el.get("href", ""),
                "member": "",
                "created": 0,
            })

    print(f"  ✅ (备用) 获取到 {len(results)} 条 V2EX 热门话题")
    return results


# ========== Linux.do ==========
# Discourse 分类 ID 映射
LINUXDO_CATEGORIES = {
    4: "开发交流", 14: "资源分享", 42: "文档专区", 10: "跳蚤市场",
    27: "职场天地", 32: "书友会", 46: "远航", 34: "新闻快讯",
    92: "网络档案", 36: "福利", 11: "闲聊区", 2: "反馈",
}


def fetch_linuxdo_hot():
    """通过 Discourse API 获取 Linux.do 热门话题（多级降级）"""
    print("📡 正在抓取 Linux.do 热门...")

    # 方案1: Discourse JSON API（周热门）
    results = _fetch_linuxdo_api()
    if results:
        return results

    # 方案2: RSS Feed
    results = _fetch_linuxdo_rss()
    if results:
        return results

    # 方案3: latest API
    results = _fetch_linuxdo_latest_api()
    if results:
        return results

    print("  ❌ Linux.do 所有抓取方案均失败")
    return []


def _fetch_linuxdo_api():
    """方案1: Discourse JSON API（周热门）"""
    resp = fetch_with_retry(LINUXDO_TOP_API)
    if not resp:
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return []

    topics = data.get("topic_list", {}).get("topics", [])
    if not topics:
        return []

    results = []
    for t in topics[:20]:
        cat_id = t.get("category_id", "")
        results.append({
            "title": t.get("title", ""),
            "category": LINUXDO_CATEGORIES.get(cat_id, str(cat_id)),
            "replies": t.get("posts_count", 0) - 1,
            "views": t.get("views", 0),
            "url": f"https://linux.do/t/{t.get('slug', '')}/{t.get('id', '')}",
            "like_count": t.get("like_count", 0),
        })

    print(f"  ✅ (API) 获取到 {len(results)} 条 Linux.do 热门话题")
    return results


def _fetch_linuxdo_rss():
    """方案2: RSS Feed（周热门）"""
    rss_headers = {
        **HEADERS,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    resp = fetch_with_retry(LINUXDO_RSS, headers=rss_headers)
    if not resp:
        return []

    items = parse_rss(resp.text)
    if not items:
        return []

    results = []
    for item in items[:20]:
        results.append({
            "title": item.get("title", ""),
            "category": "",
            "replies": 0,
            "views": 0,
            "url": item.get("url", ""),
            "like_count": 0,
        })

    print(f"  ✅ (RSS) 获取到 {len(results)} 条 Linux.do 话题")
    return results


def _fetch_linuxdo_latest_api():
    """方案3: latest API"""
    resp = fetch_with_retry(LINUXDO_LATEST_API)
    if not resp:
        return []

    try:
        data = resp.json()
        topics = data.get("topic_list", {}).get("topics", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    results = []
    for t in topics[:20]:
        cat_id = t.get("category_id", "")
        results.append({
            "title": t.get("title", ""),
            "category": LINUXDO_CATEGORIES.get(cat_id, str(cat_id)),
            "replies": t.get("posts_count", 0) - 1,
            "views": t.get("views", 0),
            "url": f"https://linux.do/t/{t.get('slug', '')}/{t.get('id', '')}",
            "like_count": t.get("like_count", 0),
        })

    print(f"  ✅ (Latest API) 获取到 {len(results)} 条 Linux.do 话题")
    return results


# ========== NodeSeek ==========
def fetch_nodeseek_hot():
    """通过 RSS Feed 获取 NodeSeek 最新帖子（多级降级）"""
    print("📡 正在抓取 NodeSeek 热门...")

    # 方案1: RSS Feed（最稳定，官方提供）
    results = _fetch_nodeseek_rss()
    if results:
        return results

    # 方案2: 页面抓取
    results = _fetch_nodeseek_html()
    if results:
        return results

    print("  ❌ NodeSeek 所有抓取方案均失败")
    return []


def _fetch_nodeseek_rss():
    """方案1: RSS Feed"""
    rss_headers = {
        **HEADERS,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    resp = fetch_with_retry(NODESEEK_RSS, headers=rss_headers)
    if not resp:
        return []

    items = parse_rss(resp.text)
    if not items:
        return []

    results = []
    for item in items[:20]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "replies": 0,
            "category": "",
            "author": item.get("author", ""),
            "desc": item.get("desc", ""),
        })

    print(f"  ✅ (RSS) 获取到 {len(results)} 条 NodeSeek 话题")
    return results


def _fetch_nodeseek_html():
    """方案2: 页面抓取（备用）"""
    resp = fetch_with_retry("https://www.nodeseek.com")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # 查找所有含帖子链接的元素
    links = soup.find_all("a", href=re.compile(r"/post-\d+"))
    seen = set()
    for link in links:
        href = link.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        title = link.get_text(strip=True)
        if title and len(title) > 4:
            results.append({
                "title": title,
                "url": f"https://www.nodeseek.com{href}" if href.startswith("/") else href,
                "replies": 0,
                "category": "",
                "author": "",
                "desc": "",
            })

    if results:
        print(f"  ✅ (HTML) 获取到 {len(results)} 条 NodeSeek 话题")
    return results


# ========== 报告生成 ==========
def generate_report(v2ex_data, linuxdo_data, nodeseek_data):
    """生成 Markdown 格式的热点报告"""
    now = datetime.now(CST)
    lines = [
        f"# 🌐 三站热点日报 | {TODAY}",
        "",
        f"> 🕐 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')} (CST)",
        "",
        "---",
        "",
    ]

    # === V2EX ===
    lines.append("## 🟢 一、V2EX（v2ex.com）")
    lines.append("")
    lines.append("> 社区定位：中文老牌技术/生活社区")
    lines.append("")
    if v2ex_data:
        lines.append("### 🔥 热门话题")
        lines.append("")
        lines.append("| # | 话题 | 节点 | 回复数 |")
        lines.append("|---|------|------|--------|")
        for i, t in enumerate(v2ex_data[:15], 1):
            title = t["title"].replace("|", "｜")
            lines.append(f"| {i} | [{title}]({t['url']}) | {t['node']} | {t['replies']} |")
    else:
        lines.append("⚠️ 今日未能获取 V2EX 数据")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === NodeSeek ===
    lines.append("## 🟡 二、NodeSeek（nodeseek.com）")
    lines.append("")
    lines.append("> 社区定位：服务器/VPS交易为主的技术社区")
    lines.append("")
    if nodeseek_data:
        lines.append("### 🔥 热门话题")
        lines.append("")
        lines.append("| # | 话题 | 作者 |")
        lines.append("|---|------|------|")
        for i, t in enumerate(nodeseek_data[:15], 1):
            title = t["title"].replace("|", "｜")
            author = t.get("author", "")
            lines.append(f"| {i} | [{title}]({t['url']}) | {author} |")
    else:
        lines.append("⚠️ 今日未能获取 NodeSeek 数据（该站可能有反爬机制）")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === Linux.do ===
    lines.append("## 🔵 三、Linux.do（linux.do）")
    lines.append("")
    lines.append("> 社区定位：AI浪潮下崛起的中文开发者社区")
    lines.append("")
    if linuxdo_data:
        lines.append("### 🔥 热门话题")
        lines.append("")
        lines.append("| # | 话题 | 回复数 | 浏览数 | 点赞数 |")
        lines.append("|---|------|--------|--------|--------|")
        for i, t in enumerate(linuxdo_data[:15], 1):
            title = t["title"].replace("|", "｜")
            lines.append(f"| {i} | [{title}]({t['url']}) | {t.get('replies', 0)} | {t.get('views', 0)} | {t.get('like_count', 0)} |")
    else:
        lines.append("⚠️ 今日未能获取 Linux.do 数据")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === 趋势分析 ===
    lines.append("## 🎯 趋势速览")
    lines.append("")

    # 关键词提取
    all_titles = []
    for t in v2ex_data:
        all_titles.append(t["title"])
    for t in linuxdo_data:
        all_titles.append(t["title"])
    for t in nodeseek_data:
        all_titles.append(t["title"])

    hot_keywords = _extract_keywords(all_titles)
    if hot_keywords:
        lines.append("**高频关键词**: " + "、".join(hot_keywords[:10]))
        lines.append("")

    # 分类统计
    categories = _categorize_topics(v2ex_data, linuxdo_data, nodeseek_data)
    if categories:
        lines.append("| 主题方向 | V2EX | NodeSeek | Linux.do |")
        lines.append("|---------|------|----------|----------|")
        for cat, counts in categories.items():
            v = "✅" if counts.get("v2ex") else ""
            n = "✅" if counts.get("nodeseek") else ""
            l = "✅🔥" if counts.get("linuxdo") > 1 else ("✅" if counts.get("linuxdo") else "")
            lines.append(f"| {cat} | {v} | {n} | {l} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*本报告由 [hotspots](https://github.com/) 自动生成*")
    lines.append("")

    return "\n".join(lines)


def _extract_keywords(titles):
    """简单关键词提取"""
    # 停用词
    stopwords = set("的了是在我有和就不人都一个也这被到说会着要看与而且从及对等把但为所其".split())
    # 将所有标题分词（按标点和空格切分）
    words = {}
    for title in titles:
        # 去除标点
        parts = re.split(r"[，。！？、\s\|·\-—：；（）()【】\[\]{}「」''\"\"···…]", title)
        for part in parts:
            part = part.strip()
            if len(part) >= 2 and part not in stopwords:
                words[part] = words.get(part, 0) + 1

    # 按频次排序
    sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)
    return [w for w, c in sorted_words[:10] if c >= 1]


def _categorize_topics(v2ex_data, linuxdo_data, nodeseek_data):
    """简单话题分类统计"""
    categories = {
        "AI/人工智能": {"v2ex": 0, "nodeseek": 0, "linuxdo": 0},
        "云服务器/VPS": {"v2ex": 0, "nodeseek": 0, "linuxdo": 0},
        "职场/生活": {"v2ex": 0, "nodeseek": 0, "linuxdo": 0},
        "数码/消费": {"v2ex": 0, "nodeseek": 0, "linuxdo": 0},
        "开发/编程": {"v2ex": 0, "nodeseek": 0, "linuxdo": 0},
    }

    keywords_map = {
        "AI/人工智能": ["AI", "GPT", "ChatGPT", "Claude", "DeepSeek", "人工智能", "大模型", "LLM", "OpenAI", "vibe", "coding"],
        "云服务器/VPS": ["VPS", "服务器", "搬瓦工", "CN2", "云", "GPU", "带宽", "节点", "host", "server"],
        "职场/生活": ["35岁", "职场", "辞职", "工资", "领导", "加班", "养老", "中年", "无聊", "创业", "副业"],
        "数码/消费": ["618", "手机", "苹果", "iPhone", "Mac", "AirPods", "小米", "华为", "比亚迪", "车", "优惠"],
        "开发/编程": ["代码", "编程", "SDK", "Python", "Rust", "GitHub", "开源", "部署", "API", "Docker", "Linux"],
    }

    def classify(title, source):
        title_lower = title.lower()
        for cat, kws in keywords_map.items():
            for kw in kws:
                if kw.lower() in title_lower:
                    categories[cat][source] += 1
                    break

    for t in v2ex_data:
        classify(t["title"], "v2ex")
    for t in nodeseek_data:
        classify(t["title"], "nodeseek")
    for t in linuxdo_data:
        classify(t["title"], "linuxdo")

    # 过滤掉全为0的分类
    return {k: v for k, v in categories.items() if any(v.values())}


# ========== 主函数 ==========
def main():
    print(f"\n🚀 开始抓取三站热点 - {TODAY}\n")

    # 抓取数据
    v2ex_data = fetch_v2ex_hot()
    linuxdo_data = fetch_linuxdo_hot()
    nodeseek_data = fetch_nodeseek_hot()

    # 生成报告
    print("\n📝 正在生成报告...")
    report = generate_report(v2ex_data, linuxdo_data, nodeseek_data)

    # 保存报告
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n✅ 报告已保存: {REPORT_FILE}")

    # 同时输出到 stdout（供 cron 邮件或 GitHub Actions 日志查看）
    print("\n" + "=" * 60)
    print(report)

    return 0 if (v2ex_data or linuxdo_data or nodeseek_data) else 1


if __name__ == "__main__":
    sys.exit(main())
