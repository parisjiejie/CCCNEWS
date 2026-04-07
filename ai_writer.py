"""
CCC Daily News -- AI Writing Module
====================================
Uses Qwen API to generate Chinese articles, translate to Japanese,
and create issue-level headlines and editor's notes.
"""

import time
import json
import requests


# ---------------------------------------------------------------------------
# Qwen API caller with retries
# ---------------------------------------------------------------------------

def _call_qwen(api_key, messages, max_tokens=2000, retries=3):
    """
    Call the Qwen chat completion API with automatic retries.

    Args:
        api_key: str - Qwen API key
        messages: list of dicts with 'role' and 'content'
        max_tokens: int
        retries: int - number of retry attempts

    Returns:
        str - the assistant's reply text

    Raises:
        RuntimeError on persistent failure
    """
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "qwen-plus",
        "messages": messages,
        "max_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Qwen API failed after {retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def generate_chinese_article(api_key, news_items):
    """
    Given raw collected news data, produce a professional Chinese news article
    that consolidates and rewrites the source material.

    Args:
        api_key: str
        news_items: list of dicts, each with keys 'title', 'summary', 'source'

    Returns:
        dict with keys 'title_cn', 'content_cn'
    """
    material = ""
    for idx, item in enumerate(news_items if isinstance(news_items, list) else [news_items], 1):
        title = item.get("title", "")
        summary = item.get("summary", "") or item.get("content", "")
        source = item.get("source", "")
        material += f"素材{idx}:\n标题: {title}\n来源: {source}\n内容: {summary}\n\n"

    prompt = (
        "根据以下新闻素材，撰写一篇专业的中文科技新闻稿。"
        "要求：1) 用第三人称客观报道风格；2) 标题简洁有力（20字以内）；"
        "3) 正文200-400字，逻辑清晰，段落分明；4) 不要编造事实，只基于素材内容改写。\n\n"
        "请以JSON格式返回，包含 title 和 content 两个字段。\n\n"
        f"{material}"
    )

    messages = [
        {"role": "system", "content": "你是一位资深科技新闻编辑，擅长撰写专业的中文科技报道。请以JSON格式返回结果。"},
        {"role": "user", "content": prompt},
    ]

    reply = _call_qwen(api_key, messages, max_tokens=1500)

    # Parse JSON from reply
    try:
        # Try to extract JSON from the reply
        reply_clean = reply
        if "```json" in reply:
            reply_clean = reply.split("```json")[1].split("```")[0].strip()
        elif "```" in reply:
            reply_clean = reply.split("```")[1].split("```")[0].strip()
        data = json.loads(reply_clean)
        return {
            "title_cn": data.get("title", ""),
            "content_cn": data.get("content", ""),
        }
    except (json.JSONDecodeError, IndexError):
        # Fallback: treat entire reply as content
        lines = reply.strip().split("\n", 1)
        title = lines[0].strip().strip("#").strip() if lines else ""
        content = lines[1].strip() if len(lines) > 1 else reply.strip()
        return {"title_cn": title, "content_cn": content}


def generate_japanese_article(api_key, chinese_title, chinese_content):
    """
    Translate and adapt a Chinese article into professional Japanese news style.

    Args:
        api_key: str
        chinese_title: str
        chinese_content: str

    Returns:
        dict with keys 'title_jp', 'content_jp', 'summary_jp'
    """
    prompt = (
        "以下の中国語ニュース記事を、日本語のプロフェッショナルなテックニュース記事として書き直してください。\n"
        "要件：1) 日本語として自然で流暢な文章にする；2) タイトルは簡潔に（25文字以内）；"
        "3) 本文は200〜400文字；4) 50文字以内の要約も付ける。\n"
        "JSON形式で title, content, summary の3つのフィールドで返してください。\n\n"
        f"中国語タイトル: {chinese_title}\n"
        f"中国語本文: {chinese_content}"
    )

    messages = [
        {"role": "system", "content": "あなたはプロのテックニュース編集者です。中国語の記事を日本語に翻訳・リライトしてください。JSON形式で返してください。"},
        {"role": "user", "content": prompt},
    ]

    reply = _call_qwen(api_key, messages, max_tokens=1500)

    try:
        reply_clean = reply
        if "```json" in reply:
            reply_clean = reply.split("```json")[1].split("```")[0].strip()
        elif "```" in reply:
            reply_clean = reply.split("```")[1].split("```")[0].strip()
        data = json.loads(reply_clean)
        return {
            "title_jp": data.get("title", ""),
            "content_jp": data.get("content", ""),
            "summary_jp": data.get("summary", ""),
        }
    except (json.JSONDecodeError, IndexError):
        lines = reply.strip().split("\n", 1)
        title = lines[0].strip().strip("#").strip() if lines else ""
        content = lines[1].strip() if len(lines) > 1 else reply.strip()
        return {"title_jp": title, "content_jp": content, "summary_jp": content[:80]}


def generate_issue_headline_jp(api_key, articles):
    """
    Generate a Japanese headline and summary for the issue cover.

    Args:
        api_key: str
        articles: list of dicts with at least 'title_jp' or 'title'

    Returns:
        dict with keys 'headline_jp', 'summary_jp'
    """
    titles = []
    for art in articles:
        t = art.get("title_jp") or art.get("title", "")
        if t:
            titles.append(t)

    titles_str = "\n".join(f"- {t}" for t in titles)

    prompt = (
        "以下の記事タイトル一覧から、今日のニュースレターの表紙用に：\n"
        "1) メインヘッドライン（30文字以内、最も重要なニュースを反映）\n"
        "2) サマリー文（80文字以内、全体のトレンドを概括）\n"
        "を作成してください。JSON形式で headline と summary で返してください。\n\n"
        f"記事一覧:\n{titles_str}"
    )

    messages = [
        {"role": "system", "content": "あなたはCCC Daily Newsの編集長です。中国テック・AIニュースの日本語ダイジェストの表紙を作成します。JSON形式で返してください。"},
        {"role": "user", "content": prompt},
    ]

    reply = _call_qwen(api_key, messages, max_tokens=500)

    try:
        reply_clean = reply
        if "```json" in reply:
            reply_clean = reply.split("```json")[1].split("```")[0].strip()
        elif "```" in reply:
            reply_clean = reply.split("```")[1].split("```")[0].strip()
        data = json.loads(reply_clean)
        return {
            "headline_jp": data.get("headline", ""),
            "summary_jp": data.get("summary", ""),
        }
    except (json.JSONDecodeError, IndexError):
        return {
            "headline_jp": titles[0] if titles else "本日のテックニュース",
            "summary_jp": "中国テック・AI分野の最新動向をお届けします。",
        }


def generate_editors_note_jp(api_key, articles, issue_number):
    """
    Generate a Japanese editor's note for the issue.

    Args:
        api_key: str
        articles: list of dicts
        issue_number: int

    Returns:
        str - the editor's note in Japanese
    """
    titles = []
    for art in articles:
        t = art.get("title_jp") or art.get("title", "")
        cat = art.get("category", "")
        if t:
            titles.append(f"[{cat}] {t}")

    titles_str = "\n".join(titles)

    prompt = (
        f"CCC Daily News 第{issue_number}号の編集後記を書いてください。\n"
        "要件：1) 200〜300文字；2) 今日のニュースの全体的な傾向に触れる；"
        "3) 読者への感謝と次号への期待を含める；4) プロフェッショナルだが温かみのあるトーン。\n\n"
        f"本号の記事:\n{titles_str}"
    )

    messages = [
        {"role": "system", "content": "あなたはCCC Daily Newsの編集長です。編集後記を日本語で書いてください。テキストのみ返してください。"},
        {"role": "user", "content": prompt},
    ]

    return _call_qwen(api_key, messages, max_tokens=800)
