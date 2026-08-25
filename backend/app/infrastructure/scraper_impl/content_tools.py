from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


async def safe_extract_text(element, selector: str = None) -> str:
    try:
        if selector:
            target = await element.query_selector(selector)
            if target:
                return (await target.inner_text()).strip()
        else:
            return (await element.inner_text()).strip()
    except Exception:
        return ""
    return ""


async def safe_get_attribute(element, attr: str) -> str:
    try:
        value = await element.get_attribute(attr)
        return value if value else ""
    except Exception:
        return ""


def clean_content(content: str, title: str = "") -> str:
    if not content:
        return content

    content = content.strip()
    content = re.sub(r"^【[^】]+】", "", content).strip()

    prefixes = [
        r"^Odaily(?:星球日报)?\s*(?:讯|消息|报道)[\s，,]*",
        r"^PANews(?:\s+\d+月\d+日)?\s*(?:讯|消息|报道)[\s，,]*",
        r"^ChainCatcher\s*(?:讯|消息|报道)[\s，,]*",
        r"^BlockBeats\s*(?:讯|消息|报道)[\s，,]*",
        r"^深潮\s*(?:TechFlow)?\s*(?:讯|消息|报道)[\s，,]*",
        r"^Foresight(?:\s*News)?\s*(?:讯|消息|报道|快讯)[\s，,]*",
        r"^火星财经\s*(?:讯|消息|报道)[\s，,]*",
        r"^MarsBit\s*(?:讯|消息|报道)[\s，,]*",
        r"^[\s，,]*消息[\s，,]*",
    ]
    for prefix_pattern in prefixes:
        content = re.sub(prefix_pattern, "", content, count=1, flags=re.IGNORECASE).strip()

    if title and content.startswith(title):
        remaining = content[len(title):].strip()
        if remaining:
            if remaining[0] in "。？！\n\r，,：:":
                content = re.sub(r"^[，,：:、。？！\s]+", "", remaining)
            elif len(remaining) > 50 and not remaining[0].isalnum():
                content = re.sub(r"^[，,：:、\s]+", "", remaining)

    return content.strip()


def parse_relative_time(time_str: str) -> Optional[datetime]:
    now = datetime.now()
    normalized = (time_str or "").strip()

    if normalized.replace(" ", "") == "刚刚":
        return now

    match = re.search(r"(\d+)\s*分钟", normalized)
    if match:
        return now - timedelta(minutes=int(match.group(1)))

    match = re.search(r"(\d+)\s*小时", normalized)
    if match:
        return now - timedelta(hours=int(match.group(1)))

    match = re.search(r"(\d+)\s*天", normalized)
    if match:
        return now - timedelta(days=int(match.group(1)))

    match = re.search(r"今天\s+(\d{1,2}):(\d{2})", normalized)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt - timedelta(days=1) if dt > now else dt

    match = re.search(
        r"(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})", normalized
    )
    if match:
        month, day, hour, minute = map(int, match.groups())
        try:
            dt = datetime(now.year, month, day, hour, minute, 0)
        except ValueError:
            return now
        return dt.replace(year=now.year - 1) if dt > now else dt

    full_date = re.match(
        r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$",
        normalized,
    )
    if full_date:
        year, month, day, hour, minute, second = full_date.groups()
        try:
            return datetime(
                int(year),
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                int(second or 0),
            )
        except ValueError:
            return None

    match = re.search(r"^(\d{1,2}):(\d{2})$", normalized)
    if match:
        hour, minute = map(int, match.groups())
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return dt - timedelta(days=1) if dt > now else dt

    return None


async def check_importance_by_style(element) -> Dict:
    try:
        style_info = await element.evaluate(
            """
            el => {
                const computed = window.getComputedStyle(el);
                return {
                    color: computed.color,
                    fontWeight: computed.fontWeight,
                    fontSize: computed.fontSize,
                    backgroundColor: computed.backgroundColor
                };
            }
            """
        )
        reasons = []
        color = style_info.get("color", "")
        if color:
            rgb_match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", color)
            if rgb_match:
                r, g, b = map(int, rgb_match.groups())
                if r > 200 and r > g + 50 and r > b + 50:
                    reasons.append("red_color")
                elif r > 200 and g > 100 and b < 100:
                    reasons.append("orange_color")

        font_weight = style_info.get("fontWeight", "")
        if font_weight == "bold" or (font_weight.isdigit() and int(font_weight) >= 600):
            reasons.append("bold_font")

        font_size = style_info.get("fontSize", "")
        if font_size and "px" in font_size and int(font_size.replace("px", "")) >= 18:
            reasons.append("large_font")

        return {
            "is_important": len(reasons) > 0,
            "reasons": reasons,
            "style_flag": "+".join(reasons) if reasons else "normal",
        }
    except Exception as exc:
        print(f"检查样式失败: {exc}")
        return {"is_important": False, "reasons": [], "style_flag": "unknown"}


async def fetch_full_content(scraper, detail_url: str, content_selectors: List[str] = None, extract_paragraphs: bool = False) -> str:
    selectors = content_selectors or [
        ".article-content",
        ".art_detail_content",
        ".rich_text_content",
        ".flash-content",
        ".detail-body",
        ".news_body_content",
        "article.prose",
        "article",
        ".content",
    ]

    try:
        print(f"  [DEBUG] Fetching content from: {detail_url}")
        async with scraper.detail_page(detail_url) as detail_page:
            full_content = ""
            for attempt in range(5):
                try:
                    for selector in selectors:
                        try:
                            content_el = await detail_page.query_selector(selector)
                            if not content_el:
                                continue
                            if extract_paragraphs:
                                elements = await content_el.query_selector_all("p, li")
                                if elements:
                                    lines = []
                                    for el in elements:
                                        text = await safe_extract_text(el)
                                        if not text:
                                            continue
                                        tag_name = await el.evaluate("el => el.tagName")
                                        lines.append(f"- {text}" if tag_name == "LI" else text)
                                    full_content = "\n\n".join(lines)
                                else:
                                    full_content = await safe_extract_text(content_el)
                            else:
                                full_content = await safe_extract_text(content_el)
                            if full_content and len(full_content) > 20:
                                break
                        except Exception:
                            continue
                    if full_content and len(full_content) > 20:
                        break
                    await detail_page.wait_for_timeout(1500)
                except Exception as exc:
                    print(f"  [Attempt {attempt + 1}] 获取内容尝试失败: {exc}")

            if not full_content:
                print(f"  [WARNING] 无法获取内容: {detail_url}")
                try:
                    body = await detail_page.inner_html("body")
                    print(f"  [DEBUG] Body Preview: {body[:200]}...")
                except Exception:
                    pass

            return full_content if full_content else ""
    except Exception as exc:
        print(f"  获取详情页失败: {exc}")
        return ""
