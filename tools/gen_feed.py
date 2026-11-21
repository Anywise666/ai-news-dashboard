#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 晨报双语播客 RSS（播客订阅源）
- 扫描 audio/YYYY-MM-DD/ 目录，读取 manifest.json
- 生成标准 RSS 2.0 + iTunes 命名空间，每天一期，enclosure 指向 brief_zh.mp3
- 输出仓库根目录 feed.xml，供 GitHub Pages 托管
依赖: 无（纯标准库）
"""
import os
import re
import json
import html
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

BASE = "https://aihot.news/api/v1"
SITE = "https://anywise666.github.io/ai-news-dashboard"
SITE_NAME = "AI 晨报 · 90秒速览播客"
SITE_DESC = "每天一期，90 秒听懂当天最重要的 AI 资讯。头条 + 各板块要点，中英双语。"
UA = {"User-Agent": "ai-news-podcast-feed/1.0"}
MAX_EPISODES = 60   # RSS 中保留最近 N 期

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
AUDIO_ROOT = os.path.join(WORK, "ai-daily-live", "audio")
if not os.path.isdir(AUDIO_ROOT):
    AUDIO_ROOT = os.path.join(WORK, "audio")
FEED_PATH = os.path.join(WORK, "feed.xml")


def fetch_lead(date):
    """取当天头条标题作为 episode 副标题（失败返回空）"""
    try:
        req = urllib.request.Request(BASE + "/dailies/" + date, headers=UA)
        j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
        lead = (j.get("report") or {}).get("lead") or {}
        return lead.get("title") or ""
    except Exception:
        return ""


def pub_date_of(date):
    """日期字符串 -> RFC822 时间（北京时间 08:30 发布）"""
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        dt = d.replace(hour=8, minute=30, tzinfo=timezone(timedelta(hours=8)))
        return format_datetime(dt)
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def duration_of(date, brief_file):
    """估算时长（分钟:秒），基于文件字节数 / 约 16KB每秒(24kbps mp3 偏低估) → 用字数更稳"""
    # 90 秒速览固定约 90 秒；无 brief 时按普通音频估 120 秒
    return "90" if brief_file else "120"


def esc(s):
    return html.escape(str(s or ""), quote=False)


def cdata(s):
    return "<![CDATA[" + str(s or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build():
    dates = sorted([d for d in os.listdir(AUDIO_ROOT)
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", d)
                    and os.path.isfile(os.path.join(AUDIO_ROOT, d, "manifest.json"))])
    dates = [d for d in dates if d <= datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")]
    dates = dates[-MAX_EPISODES:][::-1]   # 最新在前
    print("  可订阅期数:", len(dates))

    items = []
    for date in dates:
        mpath = os.path.join(AUDIO_ROOT, date, "manifest.json")
        try:
            m = json.load(open(mpath, encoding="utf-8"))
        except Exception:
            continue
        brief = m.get("brief")
        items_meta = m.get("items") or {}
        # 选音频：优先 brief，其次头条 zh
        audio_file = brief
        if not audio_file and items_meta:
            lead = items_meta.get("lead") or {}
            audio_file = lead.get("zh")
        if not audio_file:
            continue
        audio_url = SITE + "/audio/" + date + "/" + audio_file
        abs_url = SITE + "/index.html"
        hd = datetime.strptime(date, "%Y-%m-%d")
        title = "AI 晨报速览 · " + hd.strftime("%m月%d日")
        lead_title = fetch_lead(date)
        desc = "90 秒速览当天 AI 要闻。"
        if lead_title:
            desc += " 今日头条：" + lead_title
        desc += " 完整日报：" + abs_url
        guid = "ai-news-daily-" + date
        dur = duration_of(date, brief)
        item = """    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <enclosure url="{audio}" length="{length}" type="audio/mpeg" />
      <itunes:duration>{dur}</itunes:duration>
      <itunes:title>{title}</itunes:title>
      <itunes:summary>{desc}</itunes:summary>
      <itunes:episodeType>full</itunes:episodeType>
    </item>""".format(
            title=cdata(title), link=esc(abs_url), desc=cdata(desc), guid=esc(guid),
            pub=pub_date_of(date), audio=esc(audio_url),
            length=os.path.getsize(os.path.join(AUDIO_ROOT, date, audio_file)),
            dur=dur)
        items.append(item)
        print("    -", date, "| brief:", bool(brief))

    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{name}</title>
    <link>{site}</link>
    <description>{desc}</description>
    <language>zh-CN</language>
    <itunes:author>AI 晨报</itunes:author>
    <itunes:summary>{desc}</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Technology" />
    <atom:link href="{site}/feed.xml" rel="self" type="application/rss+xml" />
    <ttl>60</ttl>
{items}
  </channel>
</rss>
""".format(name=esc(SITE_NAME), site=esc(SITE), desc=cdata(SITE_DESC), items="\n".join(items))

    with open(FEED_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(rss)
    print("=== feed.xml 已生成:", FEED_PATH, "|", len(items), "期 ===")
    return len(items)


if __name__ == "__main__":
    build()
