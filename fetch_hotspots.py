#!/usr/bin/env python3
"""
三站热点日报自动抓取脚本
- V2EX: 通过官方 API 获取热门话题
- Linux.do: 通过 Discourse API 获取热门话题
- NodeSeek: 通过页面抓取获取热门帖子
"""

import json
import re
import sys
import time
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
LINUXDO_TOP_API = "https://linux.do/top.json"
LINUXDO_LATEST_API = "https://linux.do/latest.json"
NODESEEK_URL = "https://www.nodeseek.com"


def fetch_with_retry(url, retries=3, timeout=15, **kwargs):
    """带重试的请求"""
    for i in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"  [重试 {i+1}/{retries}] 请求 {url} 失败: {e}")
            time.sleep(2)
    return None


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
def fetch_linuxdo_hot():
    """通过 Discourse API 获取 Linux.do 热门话题"""
    print("📡 正在抓取 Linux.do 热门...")
    resp = fetch_with_retry(LINUXDO_TOP_API)
    if not resp:
        print("  ❌ Linux.do API 请求失败，尝试备用方案...")
        return _fetch_linuxdo_fallback()

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("  ❌ Linux.do API 返回数据解析失败")
        return _fetch_linuxdo_fallback()

    topics = data.get("topic_list", {}).get("topics", [])
    results = []
    for t in topics[:20]:
        results.append({
            "title": t.get("title", ""),
            "category": t.get("category_id", ""),
            "replies": t.get("posts_count", 0) - 1,  # posts_count 包含主帖
            "views": t.get("views", 0),
            "url": f"https://linux.do/t/{t.get('slug', '')}/{t.get('id', '')}",
            "like_count": t.get("like_count", 0),
        })

    print(f"  ✅ 获取到 {len(results)} 条 Linux.do 热门话题")
    return results


def _fetch_linuxdo_fallback():
    """Linux.do 备用方案：抓取 latest 页面"""
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
        results.append({
            "title": t.get("title", ""),
            "category": t.get("category_id", ""),
            "replies": t.get("posts_count", 0) - 1,
            "views": t.get("views", 0),
            "url": f"https://linux.do/t/{t.get('slug', '')}/{t.get('id', '')}",
            "like_count": t.get("like_count", 0),
        })

    print(f"  ✅ (备用) 获取到 {len(results)} 条 Linux.do 话题")
    return results


# ========== NodeSeek ==========
def fetch_nodeseek_hot():
    """抓取 NodeSeek 热门帖子"""
    print("📡 正在抓取 NodeSeek 热门...")
    resp = fetch_with_retry(NODESEEK_URL)
    if not resp:
        print("  ❌ NodeSeek 页面请求失败")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # 尝试多种选择器适配 NodeSeek 页面结构
    # 方案1: 查找帖子列表
    post_items = (
        soup.select(".post-list-item")
        or soup.select("[class*='post-item']")
        or soup.select("[class*='topic']")
        or soup.select("a[href*='/post-']")
    )

    if not post_items:
        # 方案2: 查找所有含帖子链接的元素
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
                })

    for item in post_items[:20]:
        title_el = item.select_one("a") or item
        title = title_el.get_text(strip=True) if title_el else ""
        href = title_el.get("href", "") if title_el and hasattr(title_el, "get") else ""
        if not title:
            continue
        results.append({
            "title": title,
            "url": f"https://www.nodeseek.com{href}" if href.startswith("/") else href,
            "replies": 0,
            "category": "",
        })

    # 如果以上方式都没获取到，尝试 API
    if not results:
        print("  ⚠️ 页面解析未获取到内容，尝试 NodeSeek API...")
        results = _fetch_nodeseek_api()

    print(f"  ✅ 获取到 {len(results)} 条 NodeSeek 话题")
    return results


def _fetch_nodeseek_api():
    """尝试 NodeSeek 的可能 API 端点"""
    api_urls = [
        "https://www.nodeseek.com/api/posts?sort=hot",
        "https://www.nodeseek.com/api/posts",
    ]
    for url in api_urls:
        resp = fetch_with_retry(url)
        if not resp:
            continue
        try:
            data = resp.json()
            items = data.get("data", data.get("posts", []))
            if isinstance(items, list):
                results = []
                for item in items[:20]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": f"https://www.nodeseek.com/post-{item.get('id', '')}",
                        "replies": item.get("comment_count", item.get("replies", 0)),
                        "category": item.get("category", ""),
                    })
                if results:
                    return results
        except (json.JSONDecodeError, AttributeError):
            continue
    return []


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
        lines.append("| # | 话题 | 分类 | 回复数 |")
        lines.append("|---|------|------|--------|")
        for i, t in enumerate(nodeseek_data[:15], 1):
            title = t["title"].replace("|", "｜")
            lines.append(f"| {i} | [{title}]({t['url']}) | {t.get('category', '-')} | {t.get('replies', '-')} |")
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
