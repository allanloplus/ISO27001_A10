#!/usr/bin/env python3
"""從 src/lesson.json 產生旁白語音、時間軸與講稿。

輸出：
  presentation/audio/narration.mp3  整堂課的旁白音軌（含場景轉換提示音）
  presentation/lesson.js            播放器使用的時間軸 (window.LESSON)
  docs/講稿.md                      講師逐字稿

需求：pip install edge-tts；系統需有 ffmpeg。
用法：python3 tools/build_audio.py
"""
import asyncio
import hashlib
import json
import math
import os
import re
import ssl
import struct
import subprocess
import sys
from pathlib import Path

import edge_tts
import edge_tts.communicate as _comm

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "lesson.json"
CACHE = ROOT / "build" / "tts"
OUT_AUDIO = ROOT / "presentation" / "audio" / "narration.mp3"
OUT_JS = ROOT / "presentation" / "lesson.js"
OUT_MD = ROOT / "docs" / "講稿.md"

SR = 24000
LEAD_IN = 0.7          # 場景開始到第一句
LEAD_IN_DIVIDER = 1.3  # 章節分隔頁多留一點時間給動畫
GAP_SAME = 0.35        # 同一人連續講
GAP_SWITCH = 0.5       # 換人講
TAIL = 0.9             # 場景最後一句之後
TAIL_LAST = 2.5

# 在需要自訂憑證的環境（例如企業代理）可設定 TTS_CA_BUNDLE
_ca = os.environ.get("TTS_CA_BUNDLE") or (
    "/root/.ccr/ca-bundle.crt" if Path("/root/.ccr/ca-bundle.crt").exists() else None)
if _ca:
    _comm._SSL_CTX = ssl.create_default_context(cafile=_ca)
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

ZH = "零一二三四五六七八九"


def num_zh(n: int) -> str:
    if n < 10:
        return ZH[n]
    tens, ones = divmod(n, 10)
    return ("" if tens == 1 else ZH[tens]) + "十" + (ZH[ones] if ones else "")


def to_speech(text: str) -> str:
    """把字幕文字轉成較好唸的 TTS 文字（條號 8.20 → 八點二十）。"""
    text = re.sub(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?![\d.])",
                  lambda m: f"{num_zh(int(m.group(1)))}點{num_zh(int(m.group(2)))}", text)
    return text.replace("Wi-Fi", "wifi").replace("「", "").replace("」", "")


async def synth(text: str, v: dict, path: Path):
    for attempt in range(4):
        try:
            com = edge_tts.Communicate(text, v["voice"], rate=v["rate"], pitch=v["pitch"], proxy=PROXY)
            await com.save(str(path))
            if path.stat().st_size > 0:
                return
        except Exception as exc:  # 網路偶發錯誤重試
            print(f"  retry {attempt + 1}: {exc}", file=sys.stderr)
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"TTS failed: {text}")


def decode(path: Path) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True).stdout


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(round(sec * SR))


def chime(kind: str) -> bytes:
    """合成短提示音：一般場景是輕快的「叮咚」，章節頁是三連音。"""
    notes = [(1318.5, 0.11), (1760.0, 0.22)] if kind == "scene" else [(1046.5, 0.1), (1318.5, 0.1), (1568.0, 0.28)]
    vol = 0.10 if kind == "scene" else 0.16
    out = bytearray()
    for freq, dur in notes:
        n = int(dur * SR)
        for i in range(n):
            env = min(1.0, i / (0.006 * SR)) * math.exp(-4.5 * i / n)
            s = math.sin(2 * math.pi * freq * i / SR) + 0.3 * math.sin(4 * math.pi * freq * i / SR)
            out += struct.pack("<h", int(32767 * vol * env * s / 1.3))
    return bytes(out)


async def main():
    lesson = json.loads(SRC.read_text(encoding="utf-8"))
    voices = lesson["voices"]
    CACHE.mkdir(parents=True, exist_ok=True)

    # 1) 逐句產生語音（以內容雜湊快取，修改講稿只會重做有變的句子）
    jobs = []
    for sc in lesson["scenes"]:
        for ln in sc["lines"]:
            v = voices[ln["w"]]
            say = ln.get("s") or to_speech(ln["t"])
            key = hashlib.sha1(json.dumps([say, v], ensure_ascii=False).encode()).hexdigest()[:16]
            ln["_file"] = CACHE / f"{key}.mp3"
            if not ln["_file"].exists():
                jobs.append((say, v, ln["_file"]))
    print(f"TTS: {len(jobs)} new line(s) to synthesize")
    for i in range(0, len(jobs), 6):
        await asyncio.gather(*(synth(*j) for j in jobs[i:i + 6]))

    # 2) 組合音軌並計算時間軸
    pcm = bytearray()
    t = 0.0
    scenes_out = []

    def add(chunk: bytes):
        nonlocal t
        pcm.extend(chunk)
        t = len(pcm) / 2 / SR

    for si, sc in enumerate(lesson["scenes"]):
        start = t
        divider = sc.get("divider", False)
        lead = LEAD_IN_DIVIDER if divider else LEAD_IN
        c = chime("divider" if divider else "scene") if si > 0 else b""
        add(silence(0.15) + c)
        add(silence(max(0.0, lead - (t - start))))
        lines_out = []
        prev = None
        for ln in sc["lines"]:
            if prev is not None:
                add(silence(GAP_SAME if prev == ln["w"] else GAP_SWITCH))
            data = decode(ln["_file"])
            ls = t
            add(data)
            lines_out.append({"w": ln["w"], "t": ln["t"], "e": ln.get("e", ""),
                              "start": round(ls, 3), "end": round(t, 3)})
            prev = ln["w"]
        add(silence(TAIL_LAST if si == len(lesson["scenes"]) - 1 else TAIL))
        scenes_out.append({"id": sc["id"], "sec": sc["sec"], "title": sc["title"],
                           "divider": divider, "start": round(start, 3), "end": round(t, 3),
                           "lines": lines_out})

    OUT_AUDIO.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ac", "1", "-ar", str(SR), "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "64k", str(OUT_AUDIO)], input=bytes(pcm), check=True)

    data = {"title": lesson["title"], "sections": lesson["sections"],
            "speakers": {k: v["name"] for k, v in voices.items()},
            "duration": round(t, 3), "scenes": scenes_out}
    OUT_JS.write_text("// 由 tools/build_audio.py 自動產生，請勿手動修改\nwindow.LESSON = "
                      + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")

    # 3) 講稿
    md = [f"# {lesson['title']}｜教學講稿", "",
          f"總長度約 {int(t // 60)} 分 {int(t % 60)} 秒。A = {voices['A']['name']}，R = {voices['R']['name']}。", ""]
    cur_sec = None
    for sc in scenes_out:
        if sc["sec"] != cur_sec:
            cur_sec = sc["sec"]
            md += [f"## {lesson['sections'][cur_sec]}", ""]
        md += [f"### {sc['title']}（{int(sc['start'] // 60):02d}:{int(sc['start'] % 60):02d}）", ""]
        for ln in sc["lines"]:
            md.append(f"- **{voices[ln['w']]['name']}**：{ln['t']}")
        md.append("")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Done: {len(scenes_out)} scenes, {t:.1f}s → {OUT_AUDIO.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
