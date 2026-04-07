"""
CCC Daily News Admin System
============================
Flask application for managing a Japanese-language Chinese tech/AI news digest.
Handles news collection (via Firecrawl), AI writing (via Qwen), article curation,
issue editing, PDF generation, and web preview.
"""

import os
import sqlite3
import datetime
import json
import hashlib
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, g, abort
)

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ccc-daily-news-dev-key-change-in-production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "data", "news.db")
PDF_OUTPUT_DIR = os.path.join(BASE_DIR, "generated_pdfs")

# API keys
QWEN_API_KEY = "sk-733a03a6a400474d8708e4ea62aa34eb"
FIRECRAWL_API_KEY = "fc-b9fb269ca58e4750906953ba8b68df67"

# Categories used across the platform
CATEGORIES = [
    "AI\u30fb\u5927\u898f\u6a21\u30e2\u30c7\u30eb",
    "IT\u30fb\u30af\u30e9\u30a6\u30c9",
    "\u534a\u5c0e\u4f53\u30fb\u30cf\u30fc\u30c9",
    "\u30c6\u30c3\u30af\u653f\u7b56",
    "\u30b9\u30bf\u30fc\u30c8\u30a2\u30c3\u30d7",
]

# Keyword mapping for auto-categorization
CATEGORY_KEYWORDS = {
    "AI\u30fb\u5927\u898f\u6a21\u30e2\u30c7\u30eb": [
        "AI", "\u4eba\u5de5\u667a\u80fd", "\u5927\u6a21\u578b", "LLM", "GPT", "\u673a\u5668\u5b66\u4e60", "\u6df1\u5ea6\u5b66\u4e60",
        "\u795e\u7ecf\u7f51\u7edc", "\u81ea\u7136\u8bed\u8a00", "NLP", "AIGC", "\u751f\u6210\u5f0f", "\u5927\u8bed\u8a00\u6a21\u578b",
        "ChatGPT", "\u7b97\u6cd5", "\u8bad\u7ec3", "\u63a8\u7406", "transformer", "\u667a\u80fd",
        "\u6a5f\u68b0\u5b66\u7fd2", "\u30c7\u30a3\u30fc\u30d7\u30e9\u30fc\u30cb\u30f3\u30b0", "\u30ed\u30dc\u30c3\u30c8",
    ],
    "IT\u30fb\u30af\u30e9\u30a6\u30c9": [
        "\u4e91\u8ba1\u7b97", "\u4e91\u670d\u52a1", "SaaS", "PaaS", "IaaS", "\u670d\u52a1\u5668", "\u6570\u636e\u5e93",
        "\u5fae\u670d\u52a1", "DevOps", "\u5bb9\u5668", "Kubernetes", "Docker", "\u5f00\u6e90",
        "\u4e92\u8054\u7f51", "\u8f6f\u4ef6", "\u5e73\u53f0", "\u6570\u636e\u4e2d\u5fc3", "AWS", "\u963f\u91cc\u4e91", "\u817e\u8baf\u4e91",
    ],
    "\u534a\u5c0e\u4f53\u30fb\u30cf\u30fc\u30c9": [
        "\u82af\u7247", "\u534a\u5bfc\u4f53", "\u5904\u7406\u5668", "GPU", "CPU", "\u6676\u5706", "\u5149\u523b",
        "\u5236\u7a0b", "\u5b58\u50a8", "DRAM", "NAND", "\u786c\u4ef6", "\u4f20\u611f\u5668", "\u91cf\u5b50",
        "\u96c6\u6210\u7535\u8def", "\u5c01\u88c5", "ASML", "\u53f0\u79ef\u7535", "\u82f1\u4f1f\u8fbe",
    ],
    "\u30c6\u30c3\u30af\u653f\u7b56": [
        "\u76d1\u7ba1", "\u653f\u7b56", "\u6cd5\u89c4", "\u5408\u89c4", "\u53cd\u5784\u65ad", "\u6570\u636e\u5b89\u5168",
        "\u9690\u79c1", "\u7f51\u4fe1\u529e", "\u5de5\u4fe1\u90e8", "\u5236\u88c1", "\u51fa\u53e3\u7ba1\u5236", "\u5ba1\u67e5",
        "\u6cbb\u7406", "\u6807\u51c6", "\u89c4\u8303", "\u77e5\u8bc6\u4ea7\u6743",
    ],
    "\u30b9\u30bf\u30fc\u30c8\u30a2\u30c3\u30d7": [
        "\u878d\u8d44", "\u521b\u4e1a", "\u5b75\u5316", "\u98ce\u6295", "VC", "\u5929\u4f7f", "IPO",
        "\u4f30\u503c", "\u72ec\u89d2\u517d", "\u52a0\u901f\u5668", "\u79cd\u5b50\u8f6e", "A\u8f6e", "B\u8f6e",
        "\u4e0a\u5e02", "\u521b\u6295", "\u8d5b\u9053",
    ],
}

# Preset search keywords for one-click collection
PRESET_KEYWORDS = [
    "AI\u5927\u6a21\u578b",
    "\u673a\u5668\u4eba",
    "\u534a\u5bfc\u4f53",
    "\u4e91\u8ba1\u7b97",
    "\u4eba\u5de5\u667a\u80fd \u4e2d\u56fd",
    "\u79d1\u6280\u653f\u7b56",
    "\u521b\u4e1a\u878d\u8d44",
    "\u82af\u7247 \u7814\u53d1",
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=30000")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def db_init():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT '',
            summary         TEXT NOT NULL DEFAULT '',
            content         TEXT NOT NULL DEFAULT '',
            source          TEXT NOT NULL DEFAULT '',
            source_url      TEXT NOT NULL DEFAULT '',
            collected_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status          TEXT NOT NULL DEFAULT 'new'
                            CHECK (status IN ('new', 'selected', 'used')),
            content_cn      TEXT NOT NULL DEFAULT '',
            content_jp      TEXT NOT NULL DEFAULT '',
            title_jp        TEXT NOT NULL DEFAULT '',
            summary_jp      TEXT NOT NULL DEFAULT '',
            ai_status       TEXT NOT NULL DEFAULT 'none'
                            CHECK (ai_status IN ('none', 'cn_done', 'jp_done', 'both_done')),
            issue_id        INTEGER,
            FOREIGN KEY (issue_id) REFERENCES issues(id) ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_number    INTEGER NOT NULL UNIQUE,
            date            TEXT NOT NULL,
            headline        TEXT NOT NULL DEFAULT '',
            summary         TEXT NOT NULL DEFAULT '',
            headline_jp     TEXT NOT NULL DEFAULT '',
            summary_jp      TEXT NOT NULL DEFAULT '',
            editors_note_jp TEXT NOT NULL DEFAULT '',
            pdf_path        TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'draft'
                            CHECK (status IN ('draft', 'generated', 'published')),
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrate existing tables: add new columns if missing
    try:
        cur.execute("SELECT content_cn FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        for col, default in [
            ("content_cn", "''"), ("content_jp", "''"), ("title_jp", "''"),
            ("summary_jp", "''"), ("ai_status", "'none'"),
        ]:
            try:
                cur.execute(f"ALTER TABLE articles ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
            except sqlite3.OperationalError:
                pass

    try:
        cur.execute("SELECT headline_jp FROM issues LIMIT 1")
    except sqlite3.OperationalError:
        for col, default in [
            ("headline_jp", "''"), ("summary_jp", "''"), ("editors_note_jp", "''"),
        ]:
            try:
                cur.execute(f"ALTER TABLE issues ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def auto_categorize(title, summary=""):
    text = f"{title} {summary}".lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        scores[category] = score

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "IT\u30fb\u30af\u30e9\u30a6\u30c9"


def article_fingerprint(title, source_url):
    raw = f"{title.strip()}|{source_url.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


_firecrawl_available = None  # None=untested, True/False=cached result

def firecrawl_search(query, limit=10):
    """Search for news using the Firecrawl API, with AI fallback."""
    global _firecrawl_available
    import requests as http_requests

    # --- Skip Firecrawl if previously failed ---
    if _firecrawl_available is not False:
        url = "https://api.firecrawl.dev/v1/search"
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "limit": limit,
            "lang": "zh",
            "country": "cn",
        }
        try:
            resp = http_requests.post(url, headers=headers, json=payload, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            _firecrawl_available = True

            results = []
            items = data.get("data", data.get("results", []))
            if isinstance(items, list):
                for item in items:
                    title = item.get("title", "") or item.get("metadata", {}).get("title", "")
                    url_val = item.get("url", "") or item.get("metadata", {}).get("sourceURL", "")
                    snippet = item.get("description", "") or item.get("markdown", "")[:300] or ""
                    source = item.get("metadata", {}).get("siteName", "") or ""
                    if title:
                        results.append({
                            "title": title.strip(),
                            "url": url_val.strip(),
                            "snippet": snippet.strip()[:500],
                            "source": source.strip(),
                            "category": auto_categorize(title, snippet),
                        })
            if results:
                return results
        except Exception as e:
            _firecrawl_available = False
            app.logger.warning(f"Firecrawl unavailable, will use AI for all searches: {e}")

    # --- Fallback: use Qwen AI ---
    return ai_search_news(query, limit)


def ai_search_news(query, limit=10):
    """Use Qwen AI to generate recent news items for a given topic."""
    import requests as http_requests
    import random

    today = datetime.date.today().strftime("%Y年%m月%d日")
    rand_seed = random.randint(1000, 9999)
    prompt = f"""你是一个中国科技新闻数据库。请根据关键词"{query}"，生成{limit}条最近7天内的中国科技新闻条目。(seed:{rand_seed})

要求：
1. 每条包含：title(标题)、snippet(50-100字摘要)、source(来源媒体如36kr、虎嗅、钛媒体、量子位、机器之心等)、url(来源网址)
2. 内容要聚焦AI、机器人、IT技术、半导体等中国科技领域
3. 内容应基于你所知的真实事件和公司，日期为最近7天（今天是{today}）
4. 标题要像真实新闻标题，简洁有力，每条标题必须不同且具体
5. 不要重复之前生成过的内容，尽量覆盖不同的公司和事件

请以JSON数组格式返回，每个元素包含title、snippet、source、url字段。只返回JSON数组，不要其他文字。"""

    try:
        resp = http_requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 3000,
                "temperature": 0.95,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # Parse JSON from response
        import re
        content = content.strip()
        # Remove markdown code fences if present
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        items = json.loads(content)
        results = []
        for item in items:
            title = item.get("title", "").strip()
            if title:
                results.append({
                    "title": title,
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                    "source": item.get("source", "AI采集"),
                    "category": auto_categorize(title, item.get("snippet", "")),
                })
        return results[:limit]
    except Exception as e:
        app.logger.error(f"AI search fallback error: {e}")
        return []


# ---------------------------------------------------------------------------
# Routes -- Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    db = get_db()

    total_articles = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_issues = db.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
    new_articles = db.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'new'"
    ).fetchone()[0]
    selected_articles = db.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'selected'"
    ).fetchone()[0]
    published_issues = db.execute(
        "SELECT COUNT(*) FROM issues WHERE status = 'published'"
    ).fetchone()[0]

    recent_articles = db.execute(
        "SELECT * FROM articles ORDER BY collected_at DESC LIMIT 10"
    ).fetchall()
    recent_issues = db.execute(
        "SELECT * FROM issues ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

    last_issue = db.execute(
        "SELECT MAX(issue_number) as max_num FROM issues"
    ).fetchone()
    latest_issue = last_issue["max_num"] or 0

    category_counts = {}
    for cat in CATEGORIES:
        count = db.execute(
            "SELECT COUNT(*) FROM articles WHERE category = ?", (cat,)
        ).fetchone()[0]
        category_counts[cat] = count

    return render_template(
        "dashboard.html",
        total_articles=total_articles,
        total_issues=total_issues,
        new_articles=new_articles,
        selected_count=selected_articles,
        published_issues=published_issues,
        recent_articles=recent_articles,
        recent_issues=recent_issues,
        latest_issue=latest_issue,
        category_counts=category_counts,
        categories=CATEGORIES,
    )


# ---------------------------------------------------------------------------
# Routes -- News Collection
# ---------------------------------------------------------------------------

@app.route("/collect")
def collect():
    return render_template("collect.html", categories=CATEGORIES, preset_keywords=PRESET_KEYWORDS)


@app.route("/collect/search", methods=["POST"])
def collect_search():
    query = request.form.get("query", "").strip()
    if not query:
        flash("\u8bf7\u8f93\u5165\u641c\u7d22\u5173\u952e\u8bcd\u3002", "error")
        return redirect(url_for("collect"))

    results = firecrawl_search(query)

    if not results:
        flash("\u672a\u627e\u5230\u7ed3\u679c\uff0c\u8bf7\u5c1d\u8bd5\u5176\u4ed6\u5173\u952e\u8bcd\u3002", "warning")
        return redirect(url_for("collect"))

    return render_template(
        "collect.html",
        categories=CATEGORIES,
        preset_keywords=PRESET_KEYWORDS,
        search_results=results,
        search_query=query,
    )


@app.route("/collect/import", methods=["POST"])
def collect_import():
    """Import selected search results as articles."""
    db = get_db()
    selected = request.form.getlist("selected")
    total_added = 0

    for idx_str in selected:
        title = request.form.get(f"title_{idx_str}", "").strip()
        url_val = request.form.get(f"url_{idx_str}", "").strip()
        snippet = request.form.get(f"snippet_{idx_str}", "").strip()
        source = request.form.get(f"source_{idx_str}", "").strip()
        category = request.form.get(f"category_{idx_str}", "").strip()

        if not title:
            continue

        # Check duplicate
        existing = db.execute(
            "SELECT id FROM articles WHERE source_url = ? OR title = ?",
            (url_val, title)
        ).fetchone()
        if existing:
            continue

        if not category:
            category = auto_categorize(title, snippet)

        db.execute(
            """INSERT INTO articles (title, category, summary, source, source_url, status)
               VALUES (?, ?, ?, ?, ?, 'new')""",
            (title, category, snippet, source, url_val),
        )
        total_added += 1

    db.commit()

    if total_added > 0:
        flash(f"\u6210\u529f\u5bfc\u5165 {total_added} \u7bc7\u6587\u7ae0\u3002", "success")
    else:
        flash("\u6ca1\u6709\u65b0\u6587\u7ae0\u88ab\u5bfc\u5165\uff08\u53ef\u80fd\u5df2\u5b58\u5728\uff09\u3002", "warning")

    return redirect(url_for("collect"))


@app.route("/collect/auto", methods=["POST"])
def collect_auto():
    """Auto-collect news using a single batch AI call for speed."""
    db = get_db()
    collect_auto_inner(db)
    return redirect(url_for("collect"))


def collect_auto_inner(db):
    """Core auto-collect logic, adds flash messages."""
    import requests as http_requests
    import re as _re
    total_added = 0
    total_skipped = 0

    # First try Firecrawl for one keyword to test connectivity
    global _firecrawl_available
    if _firecrawl_available is not False:
        # If Firecrawl works, use it per-keyword
        for keyword in PRESET_KEYWORDS:
            try:
                results = firecrawl_search(keyword, limit=5)
                for item in results:
                    title = item.get("title", "").strip()
                    url_val = item.get("url", "").strip()
                    snippet = item.get("snippet", "").strip()
                    source = item.get("source", "").strip()
                    category = item.get("category", "")
                    if not title:
                        continue
                    existing = db.execute(
                        "SELECT id FROM articles WHERE source_url = ? OR title = ?",
                        (url_val, title)
                    ).fetchone()
                    if existing:
                        total_skipped += 1
                        continue
                    db.execute(
                        """INSERT INTO articles (title, category, summary, source, source_url, status)
                           VALUES (?, ?, ?, ?, ?, 'new')""",
                        (title, category, snippet, source, url_val),
                    )
                    total_added += 1
            except Exception:
                pass
        db.commit()
        flash(f"自动采集完成：新增 {total_added} 篇文章，跳过 {total_skipped} 篇重复。", "success")
        return

    # Firecrawl unavailable — use single batch AI call
    today = datetime.date.today().strftime("%Y年%m月%d日")
    keywords_str = "、".join(PRESET_KEYWORDS)
    prompt = f"""你是一个中国科技新闻数据库。请生成20条最近7天内的中国科技新闻条目，覆盖以下主题领域：{keywords_str}

要求：
1. 每条包含：title(中文标题)、snippet(50-100字中文摘要)、source(来源媒体如36kr、虎嗅、钛媒体、量子位、机器之心等)、url(合理的来源网址)、category(从以下分类选一个：AI・大規模モデル、IT・クラウド、半導体・ハード、テック政策、スタートアップ)
2. 内容聚焦中国AI、机器人、IT技术、半导体、云计算、科技政策、创业融资等领域
3. 日期为最近7天（今天是{today}），每条新闻应有不同主题和公司
4. 标题简洁有力，像真实新闻标题
5. 确保5个分类都有覆盖，每个分类至少3条

请以JSON数组格式返回，只返回JSON数组，不要其他文字。"""

    try:
        resp = http_requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.85,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        import re
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        items = json.loads(content)

        for item in items:
            title = item.get("title", "").strip()
            url_val = item.get("url", "").strip()
            snippet = item.get("snippet", "").strip()
            source = item.get("source", "AI采集")
            category = item.get("category", "")

            if not title:
                continue
            if not category:
                category = auto_categorize(title, snippet)

            existing = db.execute(
                "SELECT id FROM articles WHERE title = ?", (title,)
            ).fetchone()
            if existing:
                total_skipped += 1
                continue

            db.execute(
                """INSERT INTO articles (title, category, summary, source, source_url, status)
                   VALUES (?, ?, ?, ?, ?, 'new')""",
                (title, category, snippet, source, url_val),
            )
            total_added += 1

        db.commit()
        flash(f"一键采集完成：新增 {total_added} 篇文章，跳过 {total_skipped} 篇重复。", "success")

    except Exception as e:
        app.logger.error(f"Batch AI collect error: {e}")
        flash(f"采集失败：{str(e)}", "error")


@app.route("/collect/manual", methods=["POST"])
def collect_manual():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    source = request.form.get("source", "").strip()
    source_url = request.form.get("source_url", "").strip()

    if not title:
        flash("\u6807\u9898\u4e0d\u80fd\u4e3a\u7a7a\u3002", "error")
        return redirect(url_for("collect"))

    if category not in CATEGORIES:
        category = auto_categorize(title, summary)

    db = get_db()
    db.execute(
        """INSERT INTO articles (title, category, summary, content, source, source_url, status)
           VALUES (?, ?, ?, ?, ?, ?, 'new')""",
        (title, category, summary, content, source, source_url),
    )
    db.commit()

    flash(f"\u6587\u7ae0\u5df2\u6dfb\u52a0\uff1a{title}", "success")
    return redirect(url_for("collect"))


# ---------------------------------------------------------------------------
# API Routes -- News Collection (AJAX)
# ---------------------------------------------------------------------------

@app.route("/api/collect/search", methods=["POST"])
def api_collect_search():
    """AJAX: Search news by keyword."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"success": False, "error": "请输入搜索关键词"}), 400

    results = firecrawl_search(query, limit=10)
    return jsonify({"success": True, "results": results, "count": len(results)})


@app.route("/api/collect/auto", methods=["POST"])
def api_collect_auto():
    """AJAX: One-click auto-collect from all preset keywords."""
    import requests as http_requests
    import re as _re
    import random

    db = get_db()
    total_added = 0
    total_skipped = 0

    today = datetime.date.today().strftime("%Y年%m月%d日")
    rand_seed = random.randint(1000, 9999)
    keywords_str = "、".join(PRESET_KEYWORDS)
    prompt = f"""你是一个中国科技新闻数据库。请生成20条最近7天内的中国科技新闻条目，覆盖以下主题领域：{keywords_str}。(seed:{rand_seed})

要求：
1. 每条包含：title(中文标题)、snippet(50-100字中文摘要)、source(来源媒体如36kr、虎嗅、钛媒体、量子位、机器之心等)、url(合理的来源网址)、category(从以下分类选一个：AI・大規模モデル、IT・クラウド、半導体・ハード、テック政策、スタートアップ)
2. 内容聚焦中国AI、机器人、IT技术、半导体、云计算、科技政策、创业融资
3. 今天是{today}，每条新闻应有不同主题和公司
4. 标题简洁有力，每条必须不同
5. 确保5个分类都有覆盖，每个分类至少3条

请以JSON数组格式返回，只返回JSON数组，不要其他文字。"""

    try:
        resp = http_requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.95,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        import re
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        items = json.loads(content)

        for item in items:
            title = item.get("title", "").strip()
            url_val = item.get("url", "").strip()
            snippet = item.get("snippet", "").strip()
            source = item.get("source", "AI采集")
            category = item.get("category", "")

            if not title:
                continue
            if not category:
                category = auto_categorize(title, snippet)

            existing = db.execute(
                "SELECT id FROM articles WHERE title = ?", (title,)
            ).fetchone()
            if existing:
                total_skipped += 1
                continue

            db.execute(
                """INSERT INTO articles (title, category, summary, source, source_url, status)
                   VALUES (?, ?, ?, ?, ?, 'new')""",
                (title, category, snippet, source, url_val),
            )
            total_added += 1

        db.commit()
        return jsonify({
            "success": True,
            "added": total_added,
            "skipped": total_skipped,
            "message": f"采集完成：新增 {total_added} 篇，跳过 {total_skipped} 篇重复"
        })
    except Exception as e:
        app.logger.error(f"API auto-collect error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/collect/import", methods=["POST"])
def api_collect_import():
    """AJAX: Import selected search results."""
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"success": False, "error": "没有选择文章"}), 400

    db = get_db()
    total_added = 0

    for item in items:
        title = item.get("title", "").strip()
        url_val = item.get("url", "").strip()
        snippet = item.get("snippet", "").strip()
        source = item.get("source", "").strip()
        category = item.get("category", "").strip()

        if not title:
            continue

        existing = db.execute(
            "SELECT id FROM articles WHERE source_url = ? OR title = ?",
            (url_val, title)
        ).fetchone()
        if existing:
            continue

        if not category:
            category = auto_categorize(title, snippet)

        db.execute(
            """INSERT INTO articles (title, category, summary, source, source_url, status)
               VALUES (?, ?, ?, ?, ?, 'new')""",
            (title, category, snippet, source, url_val),
        )
        total_added += 1

    db.commit()
    return jsonify({
        "success": True,
        "added": total_added,
        "message": f"成功导入 {total_added} 篇文章"
    })


# ---------------------------------------------------------------------------
# Routes -- Article Management
# ---------------------------------------------------------------------------

@app.route("/articles")
def articles():
    db = get_db()

    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")
    ai_status_filter = request.args.get("ai_status", "")

    query = "SELECT * FROM articles WHERE 1=1"
    params = []

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if ai_status_filter:
        if ai_status_filter == "has_jp":
            query += " AND ai_status IN ('jp_done', 'both_done')"
        elif ai_status_filter == "has_cn":
            query += " AND ai_status IN ('cn_done', 'both_done')"
        else:
            query += " AND ai_status = ?"
            params.append(ai_status_filter)

    query += " ORDER BY collected_at DESC"
    article_list = db.execute(query, params).fetchall()

    return render_template(
        "articles.html",
        articles=article_list,
        categories=CATEGORIES,
        category_filter=category_filter,
        status_filter=status_filter,
        ai_status_filter=ai_status_filter,
    )


@app.route("/api/articles/batch-select", methods=["POST"])
def api_batch_select():
    """Batch select articles for issue generation."""
    data = request.get_json(silent=True) or {}
    selected_ids = data.get("ids", [])

    if not selected_ids:
        return jsonify({"success": False, "error": "请先选择文章"}), 400

    db = get_db()
    # Reset all previously selected articles back to 'new'
    db.execute("UPDATE articles SET status = 'new' WHERE status = 'selected'")
    # Select the chosen articles
    placeholders = ",".join("?" * len(selected_ids))
    db.execute(
        f"UPDATE articles SET status = 'selected' WHERE id IN ({placeholders}) AND status != 'used'",
        selected_ids,
    )
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM articles WHERE status = 'selected'").fetchone()[0]
    return jsonify({"success": True, "selected": count, "message": f"已选择 {count} 篇文章，可前往期刊编辑"})


@app.route("/articles/<int:id>/toggle", methods=["POST"])
def article_toggle(id):
    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE id = ?", (id,)
    ).fetchone()

    if not article:
        flash("\u6587\u7ae0\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("articles"))

    current_status = article["status"]
    if current_status == "new":
        new_status = "selected"
    elif current_status == "selected":
        new_status = "new"
    else:
        flash("\u8be5\u6587\u7ae0\u5df2\u7528\u4e8e\u671f\u520a\uff0c\u65e0\u6cd5\u66f4\u6539\u72b6\u6001\u3002", "warning")
        return redirect(url_for("articles"))

    db.execute(
        "UPDATE articles SET status = ? WHERE id = ?", (new_status, id)
    )
    db.commit()

    flash("\u6587\u7ae0\u5df2\u9009\u62e9\u3002" if new_status == "selected" else "\u6587\u7ae0\u5df2\u53d6\u6d88\u9009\u62e9\u3002", "success")

    next_url = request.form.get("next") or request.referrer or url_for("articles")
    return redirect(next_url)


@app.route("/articles/<int:id>/edit", methods=["GET", "POST"])
def article_edit(id):
    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE id = ?", (id,)
    ).fetchone()

    if not article:
        flash("\u6587\u7ae0\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("articles"))

    if request.method == "GET":
        return render_template("article_edit.html", article=article, categories=CATEGORIES)

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    source = request.form.get("source", "").strip()
    source_url = request.form.get("source_url", "").strip()
    content_cn = request.form.get("content_cn", "").strip()
    title_jp = request.form.get("title_jp", "").strip()
    content_jp = request.form.get("content_jp", "").strip()
    summary_jp = request.form.get("summary_jp", "").strip()

    if not title:
        flash("\u6807\u9898\u4e0d\u80fd\u4e3a\u7a7a\u3002", "error")
        return redirect(url_for("article_edit", id=id))

    if category and category not in CATEGORIES:
        flash("\u65e0\u6548\u7684\u5206\u7c7b\u3002", "error")
        return redirect(url_for("article_edit", id=id))

    # Determine AI status
    ai_status = "none"
    if content_cn:
        ai_status = "cn_done"
    if title_jp and content_jp:
        ai_status = "jp_done" if not content_cn else "both_done"

    db.execute(
        """UPDATE articles
           SET title = ?, category = ?, summary = ?, content = ?,
               source = ?, source_url = ?,
               content_cn = ?, title_jp = ?, content_jp = ?, summary_jp = ?,
               ai_status = ?
           WHERE id = ?""",
        (title, category or article["category"], summary, content,
         source, source_url,
         content_cn, title_jp, content_jp, summary_jp, ai_status, id),
    )
    db.commit()

    flash(f"\u6587\u7ae0\u5df2\u66f4\u65b0\uff1a{title}", "success")
    return redirect(url_for("articles"))


@app.route("/articles/<int:id>/delete", methods=["POST"])
def article_delete(id):
    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE id = ?", (id,)
    ).fetchone()

    if not article:
        flash("\u6587\u7ae0\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("articles"))

    db.execute("DELETE FROM articles WHERE id = ?", (id,))
    db.commit()

    flash("\u6587\u7ae0\u5df2\u5220\u9664\u3002", "success")
    return redirect(url_for("articles"))


# ---------------------------------------------------------------------------
# Routes -- AI Generation API (AJAX)
# ---------------------------------------------------------------------------

@app.route("/api/ai/generate-cn/<int:id>", methods=["POST"])
def api_ai_generate_cn(id):
    """Generate Chinese article content via Qwen AI."""
    from ai_writer import generate_chinese_article

    db = get_db()
    article = db.execute("SELECT * FROM articles WHERE id = ?", (id,)).fetchone()
    if not article:
        return jsonify({"success": False, "error": "\u6587\u7ae0\u672a\u627e\u5230"}), 404

    try:
        news_item = {
            "title": article["title"],
            "summary": article["summary"] or article["content"],
            "source": article["source"],
        }
        result = generate_chinese_article(QWEN_API_KEY, news_item)

        ai_status = "cn_done"
        if article["title_jp"] and article["content_jp"]:
            ai_status = "both_done"

        db.execute(
            """UPDATE articles SET content_cn = ?, ai_status = ? WHERE id = ?""",
            (result["content_cn"], ai_status, id),
        )
        db.commit()

        return jsonify({
            "success": True,
            "content_cn": result["content_cn"],
            "ai_status": ai_status,
        })
    except Exception as e:
        app.logger.error(f"AI CN generation error for article {id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/generate-jp/<int:id>", methods=["POST"])
def api_ai_generate_jp(id):
    """Generate Japanese article content via Qwen AI."""
    from ai_writer import generate_japanese_article

    db = get_db()
    article = db.execute("SELECT * FROM articles WHERE id = ?", (id,)).fetchone()
    if not article:
        return jsonify({"success": False, "error": "\u6587\u7ae0\u672a\u627e\u5230"}), 404

    try:
        # Use Chinese content if available, otherwise use original
        cn_title = article["title"]
        cn_content = article["content_cn"] or article["content"] or article["summary"]

        result = generate_japanese_article(QWEN_API_KEY, cn_title, cn_content)

        ai_status = "jp_done"
        if article["content_cn"]:
            ai_status = "both_done"

        db.execute(
            """UPDATE articles SET title_jp = ?, content_jp = ?, summary_jp = ?,
               ai_status = ? WHERE id = ?""",
            (result["title_jp"], result["content_jp"], result["summary_jp"],
             ai_status, id),
        )
        db.commit()

        return jsonify({
            "success": True,
            "title_jp": result["title_jp"],
            "content_jp": result["content_jp"],
            "summary_jp": result["summary_jp"],
            "ai_status": ai_status,
        })
    except Exception as e:
        app.logger.error(f"AI JP generation error for article {id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/batch-cn", methods=["POST"])
def api_ai_batch_cn():
    """Batch generate Chinese content for selected articles."""
    from ai_writer import generate_chinese_article

    db = get_db()
    data = request.get_json(silent=True) or {}
    selected_ids = data.get("ids", [])

    if selected_ids:
        placeholders = ",".join("?" * len(selected_ids))
        articles_to_process = db.execute(
            f"SELECT * FROM articles WHERE id IN ({placeholders}) AND ai_status IN ('none') ORDER BY collected_at DESC",
            selected_ids,
        ).fetchall()
    else:
        return jsonify({"success": False, "error": "请先选择要处理的文章"}), 400

    results = {"processed": 0, "errors": 0, "total": len(articles_to_process), "details": []}

    for article in articles_to_process:
        try:
            news_item = {
                "title": article["title"],
                "summary": article["summary"] or article["content"],
                "source": article["source"],
            }
            result = generate_chinese_article(QWEN_API_KEY, news_item)

            db.execute(
                "UPDATE articles SET content_cn = ?, ai_status = 'cn_done' WHERE id = ?",
                (result["content_cn"], article["id"]),
            )
            db.commit()
            results["processed"] += 1
            results["details"].append({"id": article["id"], "title": article["title"], "status": "ok"})
        except Exception as e:
            results["errors"] += 1
            results["details"].append({"id": article["id"], "title": article["title"], "status": f"error: {str(e)}"})

    return jsonify({"success": True, **results})


@app.route("/api/ai/batch-jp", methods=["POST"])
def api_ai_batch_jp():
    """Batch generate Japanese content for selected articles. Auto-generates CN first if needed."""
    from ai_writer import generate_japanese_article, generate_chinese_article

    db = get_db()
    data = request.get_json(silent=True) or {}
    selected_ids = data.get("ids", [])

    if not selected_ids:
        return jsonify({"success": False, "error": "请先选择要处理的文章"}), 400

    placeholders = ",".join("?" * len(selected_ids))
    articles_to_process = db.execute(
        f"SELECT * FROM articles WHERE id IN ({placeholders}) ORDER BY collected_at DESC",
        selected_ids,
    ).fetchall()

    results = {"processed": 0, "errors": 0, "skipped": 0, "total": len(articles_to_process), "details": []}

    for article in articles_to_process:
        try:
            # Skip if already has Japanese content
            if article["content_jp"] and article["ai_status"] in ("jp_done", "both_done"):
                results["skipped"] += 1
                results["details"].append({"id": article["id"], "title": article["title"], "status": "skipped"})
                continue

            # If no Chinese content yet, generate it first
            cn_content = article["content_cn"]
            if not cn_content:
                news_item = {
                    "title": article["title"],
                    "summary": article["summary"] or article["content"] or "",
                    "source": article["source"],
                }
                cn_result = generate_chinese_article(QWEN_API_KEY, news_item)
                cn_content = cn_result["content_cn"]
                db.execute(
                    "UPDATE articles SET content_cn = ?, ai_status = 'cn_done' WHERE id = ?",
                    (cn_content, article["id"]),
                )
                db.commit()

            # Generate Japanese
            result = generate_japanese_article(QWEN_API_KEY, article["title"], cn_content)

            db.execute(
                """UPDATE articles SET title_jp = ?, content_jp = ?, summary_jp = ?,
                   ai_status = 'both_done' WHERE id = ?""",
                (result["title_jp"], result["content_jp"], result["summary_jp"], article["id"]),
            )
            db.commit()
            results["processed"] += 1
            results["details"].append({"id": article["id"], "title": article["title"], "status": "ok"})
        except Exception as e:
            results["errors"] += 1
            results["details"].append({"id": article["id"], "title": article["title"], "status": f"error: {str(e)}"})

    return jsonify({"success": True, **results})


# ---------------------------------------------------------------------------
# Routes -- Issue Editor
# ---------------------------------------------------------------------------

@app.route("/editor")
def editor():
    db = get_db()

    selected = db.execute(
        "SELECT * FROM articles WHERE status = 'selected' ORDER BY category, collected_at DESC"
    ).fetchall()

    last_issue = db.execute(
        "SELECT MAX(issue_number) as max_num FROM issues"
    ).fetchone()
    next_issue_number = (last_issue["max_num"] or 0) + 1

    today = datetime.date.today().isoformat()

    return render_template(
        "editor.html",
        selected_articles=selected,
        categories=CATEGORIES,
        next_issue_number=next_issue_number,
        today=today,
    )


# ---------------------------------------------------------------------------
# Routes -- PDF Generation
# ---------------------------------------------------------------------------

@app.route("/generate", methods=["POST"])
def generate():
    db = get_db()

    issue_number = request.form.get("issue_number", type=int)
    date_str = request.form.get("date", "").strip()
    headline = request.form.get("headline", "").strip()
    summary = request.form.get("summary", "").strip()

    if not issue_number or not date_str:
        flash("\u671f\u53f7\u548c\u65e5\u671f\u4e0d\u80fd\u4e3a\u7a7a\u3002", "error")
        return redirect(url_for("editor"))

    existing = db.execute(
        "SELECT id FROM issues WHERE issue_number = ?", (issue_number,)
    ).fetchone()
    if existing:
        flash(f"\u7b2c{issue_number}\u671f\u5df2\u5b58\u5728\u3002", "error")
        return redirect(url_for("editor"))

    selected = db.execute(
        "SELECT * FROM articles WHERE status = 'selected' ORDER BY category, collected_at DESC"
    ).fetchall()

    if not selected:
        flash("\u672a\u9009\u62e9\u6587\u7ae0\uff0c\u8bf7\u5148\u9009\u62e9\u6587\u7ae0\u3002", "error")
        return redirect(url_for("editor"))

    articles_for_pdf = [dict(row) for row in selected]

    # Generate Japanese headline/summary/editor's note via AI
    from ai_writer import generate_issue_headline_jp, generate_editors_note_jp

    try:
        if not headline:
            headline_data = generate_issue_headline_jp(QWEN_API_KEY, articles_for_pdf)
            headline = headline_data.get("headline_jp", articles_for_pdf[0].get("title_jp", articles_for_pdf[0]["title"]))
            summary = headline_data.get("summary_jp", "")
    except Exception as e:
        app.logger.error(f"Headline generation error: {e}")
        headline = headline or (articles_for_pdf[0].get("title_jp") or articles_for_pdf[0]["title"])

    editors_note = ""
    try:
        editors_note = generate_editors_note_jp(QWEN_API_KEY, articles_for_pdf, issue_number)
    except Exception as e:
        app.logger.error(f"Editor's note generation error: {e}")

    # Format date for Japanese display
    try:
        d = datetime.date.fromisoformat(date_str)
        date_display = f"{d.year}\u5e74{d.month}\u6708{d.day}\u65e5"
    except ValueError:
        date_display = date_str

    try:
        from pdf_generator import generate_issue_pdf

        pdf_path = generate_issue_pdf(
            issue_number=issue_number,
            date_str=date_display,
            headline=headline,
            summary=summary,
            articles=articles_for_pdf,
            output_dir=PDF_OUTPUT_DIR,
            editors_note=editors_note,
        )
    except Exception as e:
        app.logger.error(f"PDF generation error: {e}")
        flash(f"PDF\u751f\u6210\u5931\u8d25\uff1a{str(e)}", "error")
        return redirect(url_for("editor"))

    db.execute(
        """INSERT INTO issues (issue_number, date, headline, summary,
           headline_jp, summary_jp, editors_note_jp, pdf_path, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'generated')""",
        (issue_number, date_str, headline, summary,
         headline, summary, editors_note, pdf_path),
    )
    issue_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for article in articles_for_pdf:
        db.execute(
            "UPDATE articles SET status = 'used', issue_id = ? WHERE id = ?",
            (issue_id, article["id"]),
        )

    db.commit()

    flash(f"\u7b2c{issue_number}\u671fPDF\u5df2\u751f\u6210\u3002", "success")
    return redirect(url_for("issue_preview", id=issue_id))


# ---------------------------------------------------------------------------
# Routes -- Quick Generate API (AJAX endpoints)
# ---------------------------------------------------------------------------

@app.route("/api/quick/collect", methods=["POST"])
def api_quick_collect():
    """Step 1: Auto-collect articles via AJAX."""
    db = get_db()
    try:
        import requests as http_requests
        import re as _re
        total_added = 0
        total_skipped = 0

        global _firecrawl_available
        if _firecrawl_available is not False:
            for keyword in PRESET_KEYWORDS:
                try:
                    results = firecrawl_search(keyword, limit=5)
                    for item in results:
                        title = item.get("title", "").strip()
                        url_val = item.get("url", "").strip()
                        snippet = item.get("snippet", "").strip()
                        source = item.get("source", "").strip()
                        category = item.get("category", "")
                        if not title:
                            continue
                        existing = db.execute(
                            "SELECT id FROM articles WHERE source_url = ? OR title = ?",
                            (url_val, title)
                        ).fetchone()
                        if existing:
                            total_skipped += 1
                            continue
                        db.execute(
                            """INSERT INTO articles (title, category, summary, source, source_url, status)
                               VALUES (?, ?, ?, ?, ?, 'new')""",
                            (title, category, snippet, source, url_val),
                        )
                        total_added += 1
                except Exception:
                    pass
            db.commit()
            return jsonify(success=True, message=f"\u81ea\u52a8\u91c7\u96c6\u5b8c\u6210\uff1a\u65b0\u589e {total_added} \u7bc7\u6587\u7ae0\uff0c\u8df3\u8fc7 {total_skipped} \u7bc7\u91cd\u590d\u3002", added=total_added)

        # Firecrawl unavailable -- use single batch AI call
        today = datetime.date.today().strftime("%Y\u5e74%m\u6708%d\u65e5")
        keywords_str = "\u3001".join(PRESET_KEYWORDS)
        prompt = f"""\u4f60\u662f\u4e00\u4e2a\u4e2d\u56fd\u79d1\u6280\u65b0\u95fb\u6570\u636e\u5e93\u3002\u8bf7\u751f\u621020\u6761\u6700\u8fd17\u5929\u5185\u7684\u4e2d\u56fd\u79d1\u6280\u65b0\u95fb\u6761\u76ee\uff0c\u8986\u76d6\u4ee5\u4e0b\u4e3b\u9898\u9886\u57df\uff1a{keywords_str}

\u8981\u6c42\uff1a
1. \u6bcf\u6761\u5305\u542b\uff1atitle(\u4e2d\u6587\u6807\u9898)\u3001snippet(50-100\u5b57\u4e2d\u6587\u6458\u8981)\u3001source(\u6765\u6e90\u5a92\u4f53\u598236kr\u3001\u864e\u55c5\u3001\u949b\u5a92\u4f53\u3001\u91cf\u5b50\u4f4d\u3001\u673a\u5668\u4e4b\u5fc3\u7b49)\u3001url(\u5408\u7406\u7684\u6765\u6e90\u7f51\u5740)\u3001category(\u4ece\u4ee5\u4e0b\u5206\u7c7b\u9009\u4e00\u4e2a\uff1aAI\u30fb\u5927\u898f\u6a21\u30e2\u30c7\u30eb\u3001IT\u30fb\u30af\u30e9\u30a6\u30c9\u3001\u534a\u5c0e\u4f53\u30fb\u30cf\u30fc\u30c9\u3001\u30c6\u30c3\u30af\u653f\u7b56\u3001\u30b9\u30bf\u30fc\u30c8\u30a2\u30c3\u30d7)
2. \u5185\u5bb9\u805a\u7126\u4e2d\u56fdAI\u3001\u673a\u5668\u4eba\u3001IT\u6280\u672f\u3001\u534a\u5bfc\u4f53\u3001\u4e91\u8ba1\u7b97\u3001\u79d1\u6280\u653f\u7b56\u3001\u521b\u4e1a\u878d\u8d44\u7b49\u9886\u57df
3. \u65e5\u671f\u4e3a\u6700\u8fd17\u5929\uff08\u4eca\u5929\u662f{today}\uff09\uff0c\u6bcf\u6761\u65b0\u95fb\u5e94\u6709\u4e0d\u540c\u4e3b\u9898\u548c\u516c\u53f8
4. \u6807\u9898\u7b80\u6d01\u6709\u529b\uff0c\u50cf\u771f\u5b9e\u65b0\u95fb\u6807\u9898
5. \u786e\u4fdd5\u4e2a\u5206\u7c7b\u90fd\u6709\u8986\u76d6\uff0c\u6bcf\u4e2a\u5206\u7c7b\u81f3\u5c113\u6761

\u8bf7\u4ee5JSON\u6570\u7ec4\u683c\u5f0f\u8fd4\u56de\uff0c\u53ea\u8fd4\u56deJSON\u6570\u7ec4\uff0c\u4e0d\u8981\u5176\u4ed6\u6587\u5b57\u3002"""

        resp = http_requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.85,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        import re
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        items = json.loads(content)

        for item in items:
            title = item.get("title", "").strip()
            url_val = item.get("url", "").strip()
            snippet = item.get("snippet", "").strip()
            source = item.get("source", "AI\u91c7\u96c6")
            category = item.get("category", "")

            if not title:
                continue
            if not category:
                category = auto_categorize(title, snippet)

            existing = db.execute(
                "SELECT id FROM articles WHERE title = ?", (title,)
            ).fetchone()
            if existing:
                total_skipped += 1
                continue

            db.execute(
                """INSERT INTO articles (title, category, summary, source, source_url, status)
                   VALUES (?, ?, ?, ?, ?, 'new')""",
                (title, category, snippet, source, url_val),
            )
            total_added += 1

        db.commit()
        return jsonify(success=True, message=f"\u4e00\u952e\u91c7\u96c6\u5b8c\u6210\uff1a\u65b0\u589e {total_added} \u7bc7\u6587\u7ae0\uff0c\u8df3\u8fc7 {total_skipped} \u7bc7\u91cd\u590d\u3002", added=total_added)

    except Exception as e:
        app.logger.error(f"API quick collect error: {e}")
        return jsonify(success=False, error=str(e), message=f"\u91c7\u96c6\u5931\u8d25\uff1a{str(e)}", added=0)


@app.route("/api/quick/ai-generate", methods=["POST"])
def api_quick_ai_generate():
    """Step 2: Batch AI generate CN + JP via AJAX."""
    db = get_db()
    try:
        from ai_writer import generate_chinese_article, generate_japanese_article

        new_articles = db.execute(
            "SELECT * FROM articles WHERE status IN ('new', 'selected') AND ai_status IN ('none', 'cn_done') ORDER BY collected_at DESC LIMIT 15"
        ).fetchall()

        total = len(new_articles)
        processed = 0
        for article in new_articles:
            try:
                if article["ai_status"] == "none":
                    news_item = {
                        "title": article["title"],
                        "summary": article["summary"] or article["content"],
                        "source": article["source"],
                    }
                    cn_result = generate_chinese_article(QWEN_API_KEY, news_item)
                    cn_content = cn_result["content_cn"]
                    db.execute(
                        "UPDATE articles SET content_cn = ?, ai_status = 'cn_done' WHERE id = ?",
                        (cn_content, article["id"]),
                    )
                else:
                    cn_content = article["content_cn"]

                jp_result = generate_japanese_article(QWEN_API_KEY, article["title"], cn_content or article["summary"])
                db.execute(
                    """UPDATE articles SET title_jp = ?, content_jp = ?, summary_jp = ?,
                       ai_status = 'both_done' WHERE id = ?""",
                    (jp_result["title_jp"], jp_result["content_jp"],
                     jp_result["summary_jp"], article["id"]),
                )
                processed += 1
            except Exception as e:
                app.logger.error(f"Batch AI error for article {article['id']}: {e}")

        db.commit()
        return jsonify(success=True, message=f"AI\u751f\u6210\u5b8c\u6210\uff1a\u5904\u7406\u4e86 {processed}/{total} \u7bc7\u6587\u7ae0", processed=processed, total=total)

    except Exception as e:
        app.logger.error(f"API quick ai-generate error: {e}")
        return jsonify(success=False, error=str(e), message=f"AI\u751f\u6210\u5931\u8d25\uff1a{str(e)}", processed=0, total=0)


@app.route("/api/quick/auto-select", methods=["POST"])
def api_quick_auto_select():
    """Step 3: Auto-select articles via AJAX."""
    db = get_db()
    try:
        db.execute("UPDATE articles SET status = 'new' WHERE status = 'selected'")

        new_articles = db.execute(
            "SELECT * FROM articles WHERE status = 'new' ORDER BY ai_status DESC, collected_at DESC"
        ).fetchall()

        selected_ids = []
        used_categories = {}
        target = 8

        for article in new_articles:
            cat = article["category"]
            if cat not in used_categories and len(selected_ids) < target:
                selected_ids.append(article["id"])
                used_categories[cat] = 1

        for article in new_articles:
            if article["id"] not in selected_ids and len(selected_ids) < target:
                selected_ids.append(article["id"])

        if selected_ids:
            placeholders = ",".join("?" * len(selected_ids))
            db.execute(
                f"UPDATE articles SET status = 'selected' WHERE id IN ({placeholders})",
                selected_ids,
            )
            db.commit()
            return jsonify(success=True, message=f"\u5df2\u81ea\u52a8\u9009\u62e9 {len(selected_ids)} \u7bc7\u6587\u7ae0", selected_count=len(selected_ids))
        else:
            return jsonify(success=False, message="\u6ca1\u6709\u53ef\u9009\u62e9\u7684\u65b0\u6587\u7ae0\uff0c\u8bf7\u5148\u91c7\u96c6", selected_count=0)

    except Exception as e:
        app.logger.error(f"API quick auto-select error: {e}")
        return jsonify(success=False, error=str(e), message=f"\u81ea\u52a8\u9009\u62e9\u5931\u8d25\uff1a{str(e)}", selected_count=0)


@app.route("/api/quick/generate", methods=["POST"])
def api_quick_generate():
    """Step 4: Generate issue PDF via AJAX."""
    db = get_db()
    try:
        data = request.get_json() or {}
        issue_number = data.get("issue_number")
        date_str = data.get("date", "").strip()

        if not issue_number or not date_str:
            return jsonify(success=False, error="\u671f\u53f7\u548c\u65e5\u671f\u4e0d\u80fd\u4e3a\u7a7a", message="\u671f\u53f7\u548c\u65e5\u671f\u4e0d\u80fd\u4e3a\u7a7a")

        issue_number = int(issue_number)

        existing = db.execute(
            "SELECT id FROM issues WHERE issue_number = ?", (issue_number,)
        ).fetchone()
        if existing:
            return jsonify(success=False, error=f"\u7b2c{issue_number}\u671f\u5df2\u5b58\u5728", message=f"\u7b2c{issue_number}\u671f\u5df2\u5b58\u5728")

        selected = db.execute(
            "SELECT * FROM articles WHERE status = 'selected' ORDER BY category, collected_at DESC"
        ).fetchall()

        if not selected:
            return jsonify(success=False, error="\u672a\u9009\u62e9\u6587\u7ae0\uff0c\u8bf7\u5148\u6267\u884c\u300c\u81ea\u52a8\u9009\u62e9\u300d", message="\u672a\u9009\u62e9\u6587\u7ae0\uff0c\u8bf7\u5148\u6267\u884c\u300c\u81ea\u52a8\u9009\u62e9\u300d")

        articles_for_pdf = [dict(row) for row in selected]

        from ai_writer import generate_issue_headline_jp, generate_editors_note_jp

        headline = ""
        summary_text = ""
        editors_note = ""

        try:
            headline_data = generate_issue_headline_jp(QWEN_API_KEY, articles_for_pdf)
            headline = headline_data.get("headline_jp", "")
            summary_text = headline_data.get("summary_jp", "")
        except Exception as e:
            app.logger.error(f"Headline generation error: {e}")
            headline = articles_for_pdf[0].get("title_jp") or articles_for_pdf[0]["title"]

        try:
            editors_note = generate_editors_note_jp(QWEN_API_KEY, articles_for_pdf, issue_number)
        except Exception as e:
            app.logger.error(f"Editor's note generation error: {e}")

        try:
            d = datetime.date.fromisoformat(date_str)
            date_display = f"{d.year}\u5e74{d.month}\u6708{d.day}\u65e5"
        except ValueError:
            date_display = date_str

        try:
            from pdf_generator import generate_issue_pdf
            pdf_path = generate_issue_pdf(
                issue_number=issue_number,
                date_str=date_display,
                headline=headline,
                summary=summary_text,
                articles=articles_for_pdf,
                output_dir=PDF_OUTPUT_DIR,
                editors_note=editors_note,
            )
        except Exception as e:
            app.logger.error(f"PDF generation error: {e}")
            return jsonify(success=False, error=f"PDF\u751f\u6210\u5931\u8d25\uff1a{str(e)}", message=f"PDF\u751f\u6210\u5931\u8d25\uff1a{str(e)}")

        db.execute(
            """INSERT INTO issues (issue_number, date, headline, summary,
               headline_jp, summary_jp, editors_note_jp, pdf_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'generated')""",
            (issue_number, date_str, headline, summary_text,
             headline, summary_text, editors_note, pdf_path),
        )
        issue_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        for article in articles_for_pdf:
            db.execute(
                "UPDATE articles SET status = 'used', issue_id = ? WHERE id = ?",
                (issue_id, article["id"]),
            )
        db.commit()

        return jsonify(success=True, message=f"\u7b2c{issue_number}\u671fPDF\u5df2\u751f\u6210\uff01", issue_id=issue_id)

    except Exception as e:
        app.logger.error(f"API quick generate error: {e}")
        return jsonify(success=False, error=str(e), message=f"\u751f\u6210\u5931\u8d25\uff1a{str(e)}")


# ---------------------------------------------------------------------------
# Routes -- Quick Generate (page)
# ---------------------------------------------------------------------------

@app.route("/quick-generate")
def quick_generate():
    db = get_db()

    last_issue = db.execute(
        "SELECT MAX(issue_number) as max_num FROM issues"
    ).fetchone()
    next_number = (last_issue["max_num"] or 120) + 1
    today = datetime.date.today()
    today_str = today.strftime("%Y\u5e74%m\u6708%d\u65e5")

    new_count = db.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'new'"
    ).fetchone()[0]
    selected_count = db.execute(
        "SELECT COUNT(*) FROM articles WHERE status = 'selected'"
    ).fetchone()[0]

    return render_template(
        "quick_generate.html",
        next_number=next_number,
        today=today.isoformat(),
        today_display=today_str,
        new_count=new_count,
        selected_count=selected_count,
    )



# ---------------------------------------------------------------------------
# Routes -- Issue Preview (Japanese web page)
# ---------------------------------------------------------------------------

@app.route("/issues/<int:id>/preview")
def issue_preview(id):
    db = get_db()
    issue = db.execute("SELECT * FROM issues WHERE id = ?", (id,)).fetchone()
    if not issue:
        flash("\u671f\u520a\u672a\u627e\u5230", "error")
        return redirect(url_for("issues"))

    issue_articles = db.execute(
        "SELECT * FROM articles WHERE issue_id = ? ORDER BY category",
        (id,)
    ).fetchall()

    return render_template("issue_preview.html", issue=issue, articles=issue_articles,
                           categories=CATEGORIES)


# ---------------------------------------------------------------------------
# Routes -- Issues Management
# ---------------------------------------------------------------------------

@app.route("/issues")
def issues():
    db = get_db()
    issue_list = db.execute(
        "SELECT * FROM issues ORDER BY issue_number DESC"
    ).fetchall()

    return render_template("issues.html", issues=issue_list)


@app.route("/issues/<int:id>/download")
def issue_download(id):
    db = get_db()
    issue = db.execute(
        "SELECT * FROM issues WHERE id = ?", (id,)
    ).fetchone()

    if not issue:
        flash("\u671f\u520a\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("issues"))

    pdf_path = issue["pdf_path"]
    if not pdf_path or not os.path.isfile(pdf_path):
        flash("PDF\u6587\u4ef6\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("issues"))

    filename = f"CCC_Daily_News_#{issue['issue_number']}_{issue['date']}.pdf"
    return send_file(pdf_path, as_attachment=True, download_name=filename)


@app.route("/issues/<int:id>/publish", methods=["POST"])
def issue_publish(id):
    db = get_db()
    issue = db.execute(
        "SELECT * FROM issues WHERE id = ?", (id,)
    ).fetchone()

    if not issue:
        flash("\u671f\u520a\u672a\u627e\u5230\u3002", "error")
        return redirect(url_for("issues"))

    if issue["status"] == "published":
        flash(f"\u7b2c{issue['issue_number']}\u671f\u5df2\u53d1\u5e03\u3002", "warning")
        return redirect(url_for("issues"))

    if issue["status"] != "generated":
        flash("\u53ea\u6709\u5df2\u751f\u6210\u7684\u671f\u520a\u624d\u80fd\u53d1\u5e03\u3002", "error")
        return redirect(url_for("issues"))

    db.execute(
        "UPDATE issues SET status = 'published' WHERE id = ?", (id,)
    )
    db.commit()

    flash(f"\u7b2c{issue['issue_number']}\u671f\u5df2\u53d1\u5e03\u3002", "success")
    return redirect(url_for("issues"))


# ---------------------------------------------------------------------------
# Routes -- API
# ---------------------------------------------------------------------------

@app.route("/api/articles/selected")
def api_selected_articles():
    db = get_db()
    selected = db.execute(
        "SELECT * FROM articles WHERE status = 'selected' ORDER BY category, collected_at DESC"
    ).fetchall()

    result = []
    for row in selected:
        result.append({
            "id": row["id"],
            "title": row["title"],
            "title_jp": row["title_jp"],
            "category": row["category"],
            "summary": row["summary"],
            "summary_jp": row["summary_jp"],
            "content": row["content"],
            "content_cn": row["content_cn"],
            "content_jp": row["content_jp"],
            "source": row["source"],
            "source_url": row["source_url"],
            "collected_at": row["collected_at"],
            "status": row["status"],
            "ai_status": row["ai_status"],
        })

    return jsonify({"articles": result, "count": len(result)})


@app.route("/api/issues/recent")
def api_recent_issues():
    db = get_db()
    issue_list = db.execute(
        "SELECT * FROM issues ORDER BY issue_number DESC LIMIT 10"
    ).fetchall()
    result = []
    for row in issue_list:
        result.append({
            "id": row["id"],
            "issue_number": row["issue_number"],
            "date": row["date"],
            "headline": row["headline_jp"] or row["headline"],
            "status": row["status"],
        })
    return jsonify({"issues": result})


@app.route("/api/issues/published")
def api_published_issues():
    db = get_db()
    issue_list = db.execute(
        "SELECT * FROM issues WHERE status = 'published' ORDER BY issue_number DESC"
    ).fetchall()
    result = []
    for row in issue_list:
        result.append({
            "id": row["id"],
            "issue_number": row["issue_number"],
            "date": row["date"],
            "headline_jp": row["headline_jp"] or row["headline"],
            "summary_jp": row["summary_jp"] or row["summary"],
            "status": row["status"],
        })
    return jsonify({"issues": result})


@app.route("/api/issues/<int:id>/detail")
def api_issue_detail(id):
    db = get_db()
    issue = db.execute("SELECT * FROM issues WHERE id = ?", (id,)).fetchone()
    if not issue:
        return jsonify({"error": "not found"}), 404

    issue_articles = db.execute(
        "SELECT * FROM articles WHERE issue_id = ? ORDER BY category",
        (id,)
    ).fetchall()

    articles_data = []
    for row in issue_articles:
        articles_data.append({
            "id": row["id"],
            "title_jp": row["title_jp"] or row["title"],
            "category": row["category"],
            "summary_jp": row["summary_jp"] or row["summary"],
            "content_jp": row["content_jp"] or row["content"],
        })

    return jsonify({
        "issue": {
            "id": issue["id"],
            "issue_number": issue["issue_number"],
            "date": issue["date"],
            "headline_jp": issue["headline_jp"] or issue["headline"],
            "summary_jp": issue["summary_jp"] or issue["summary"],
            "editors_note_jp": issue["editors_note_jp"],
        },
        "articles": articles_data,
    })


# ---------------------------------------------------------------------------
# Template context processors
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    return {
        "now": datetime.datetime.now(),
        "all_categories": CATEGORIES,
    }


# ---------------------------------------------------------------------------
# Routes -- Public Frontend
# ---------------------------------------------------------------------------

@app.route("/site")
def frontend_site():
    """Public-facing Japanese news site."""
    db = get_db()

    # Latest published issue
    latest_issue = db.execute(
        "SELECT * FROM issues WHERE status = 'published' ORDER BY issue_number DESC LIMIT 1"
    ).fetchone()

    latest_articles = []
    categories_data = {cat: [] for cat in CATEGORIES}

    if latest_issue:
        latest_articles = db.execute(
            "SELECT * FROM articles WHERE issue_id = ? ORDER BY category",
            (latest_issue["id"],)
        ).fetchall()
        for article in latest_articles:
            cat = article["category"]
            if cat in categories_data:
                categories_data[cat].append(article)

    # All published issues for archive
    published_issues = db.execute(
        "SELECT * FROM issues WHERE status = 'published' ORDER BY issue_number DESC"
    ).fetchall()

    # Stats
    total_articles = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_issues = db.execute(
        "SELECT COUNT(*) FROM issues WHERE status = 'published'"
    ).fetchone()[0]

    return render_template(
        "frontend.html",
        latest_issue=latest_issue,
        latest_articles=latest_articles,
        published_issues=published_issues,
        total_articles=total_articles,
        total_issues=total_issues,
        categories_data=categories_data,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

db_init()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
