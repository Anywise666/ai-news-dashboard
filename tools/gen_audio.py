#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 晨报双语播客音频生成器
- 拉取 aihot 当日日报，为头条 + 每条卡片生成中英双语音频
- 写入 audio/YYYY-MM-DD/ 目录 + manifest.json
- 清理超过保留期的旧目录
依赖: pip install edge-tts
"""
import asyncio
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

BASE = "https://aihot.news/api/v1"
# 音频输出到发布目录下（GitHub Pages 从仓库 root 提供，故仓库内为 audio/）
AUDIO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai-daily-live", "audio")
VOICE_ZH = "zh-CN-XiaoxiaoNeural"   # 中文女声
VOICE_EN = "en-US-JennyNeural"      # 英文女声
KEEP_DAYS = 30
UA = {"User-Agent": "ai-news-podcast/1.0"}


def fetch_json(path):
    try:
        req = urllib.request.Request(BASE + path, headers=UA)
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except Exception as e:
        print("  [fetch fail]", path, repr(e)[:120])
        return None


def today_ymd():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def item_id(url):
    if not url:
        return ""
    m = re.search(r"/items/([a-z0-9]+)", str(url), re.I)
    return m.group(1) if m else ""


def clean_text(s):
    """清理不适合 TTS 的字符"""
    s = re.sub(r"[\u200b-\u200d\ufeff]", "", s or "")
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)[:40]


async def synth(text, voice, out_path, retries=3):
    import edge_tts
    text = clean_text(text)
    if not text:
        return False
    for i in range(retries):
        try:
            comm = edge_tts.Communicate(text, voice, rate="+0%")
            await comm.save(out_path)
            if os.path.getsize(out_path) > 500:
                return True
        except Exception as e:
            print("    [tts retry %d] %s" % (i + 1, repr(e)[:100]))
            await asyncio.sleep(2 * (i + 1))
    return False


def build_tts_items(report, en_map):
    """构造待生成条目列表，每项: {key, title, zh_text, en_text}"""
    items = []

    # 头条：从 sections/flashes/highlights 匹配链接
    lead = report.get("lead") or {}
    lead_title = lead.get("title") or ""
    lead_url = ""
    norm = lambda s: (s or "").replace("\u3000", "").replace(" ", "").lower()
    target = norm(lead_title)
    pools = []
    for s in report.get("sections", []):
        pools.extend(s.get("items", []))
    pools.extend(report.get("flashes", []))
    pools.extend(report.get("highlights", []))
    for p in pools:
        if norm(p.get("title")) == target:
            links = p.get("links") or {}
            lead_url = links.get("original") or links.get("aihot") or ""
            break
    if lead_title:
        lid = item_id(lead_url) or "lead"
        items.append({
            "key": "lead",
            "title": lead_title,
            "zh_text": "今日头条。" + lead_title + "。" + (lead.get("leadParagraph") or ""),
            "en_text": en_map.get(lid, ""),
        })

    # 卡片：用纯 itemId 作为 key（唯一且与页面匹配无关序号）
    for sec in report.get("sections", []):
        for it in sec.get("items", []):
            links = it.get("links") or {}
            aid = item_id(links.get("aihot"))
            key = safe_name(aid) if aid else ("t_" + safe_name((it.get("title") or "")[:20]))
            items.append({
                "key": key,
                "title": it.get("title") or "",
                "zh_text": it.get("title", "") + "。" + (it.get("summary") or ""),
                "en_text": en_map.get(aid, ""),
            })
    return items


def cleanup_old():
    """删除超过保留期的音频目录"""
    try:
        dirs = sorted([d for d in os.listdir(AUDIO_ROOT)
                       if re.match(r"^\d{4}-\d{2}-\d{2}$", d)])
        cutoff = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        for d in dirs:
            if d < cutoff:
                import shutil
                shutil.rmtree(os.path.join(AUDIO_ROOT, d), ignore_errors=True)
                print("  [cleanup] removed", d)
    except Exception as e:
        print("  [cleanup skip]", repr(e)[:100])


async def main():
    date = sys.argv[1] if len(sys.argv) > 1 else today_ymd()
    print("=== AI 晨报播客音频生成:", date, "===")
    outdir = os.path.join(AUDIO_ROOT, date)
    os.makedirs(outdir, exist_ok=True)

    # 拉取日报
    j = fetch_json("/dailies/" + date)
    if not j or not j.get("report"):
        print("!! 该日期无日报，退出")
        return
    report = j["report"]

    # 拉英文原题映射（近7天）
    en_map = {}
    ij = fetch_json("/items?limit=100")
    if ij and ij.get("items"):
        for it in ij["items"]:
            aid = item_id((it.get("links") or {}).get("aihot")) or it.get("id")
            if aid and it.get("originalTitle"):
                en_map[aid] = it["originalTitle"]
    print("  英文原题映射:", len(en_map), "条")

    items = build_tts_items(report, en_map)
    print("  待生成条目:", len(items), "条")

    manifest = {"date": date, "generatedAt": datetime.now(timezone.utc).isoformat(), "items": {}}
    ok_zh = ok_en = 0
    for idx, it in enumerate(items):
        key = it["key"]
        zh_file = key + "_zh.mp3"
        en_file = key + "_en.mp3"
        entry = {"title": it["title"]}
        # 中文
        if await synth(it["zh_text"], VOICE_ZH, os.path.join(outdir, zh_file)):
            entry["zh"] = zh_file
            ok_zh += 1
        # 英文
        if it["en_text"]:
            en_script = "Original headline. " + clean_text(it["en_text"])
            if await synth(en_script, VOICE_EN, os.path.join(outdir, en_file)):
                entry["en"] = en_file
                ok_en += 1
        manifest["items"][key] = entry
        print("  [%02d/%02d] %s | zh:%s en:%s" % (
            idx + 1, len(items), it["title"][:22],
            "Y" if "zh" in entry else "N", "Y" if "en" in entry else "-"))

    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    cleanup_old()
    total_size = sum(os.path.getsize(os.path.join(outdir, f))
                     for f in os.listdir(outdir) if f.endswith(".mp3"))
    print("=== 完成: 中文 %d / 英文 %d, 总大小 %.1f KB ===" % (ok_zh, ok_en, total_size / 1024))
    print("MANIFEST:", json.dumps({"date": date, "count": len(items),
                                    "zh": ok_zh, "en": ok_en}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
