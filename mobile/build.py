#!/usr/bin/env python3
"""把 dating-coach 技能打包成手机端单文件 PWA。

用法:
    python mobile/build.py

读取 .claude/skills/dating-coach/ 下的 SKILL.md 与 references/*.md（只取中文版），
注入 mobile/template.html，输出到 docs/（GitHub Pages 默认可用目录）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL_DIR = ROOT / ".claude" / "skills" / "dating-coach"
OUT = ROOT / "docs"

# id -> (显示名, 一句话说明, 默认勾选)
REFS = {
    "chat-analysis": ("聊天分析", "流程 A 必读：逐条读信号 + 构造回复", True),
    "profile-template": ("档案模板", "记录字段、局势分析、跨会话保存", True),
    "signal-patterns": ("信号识别", "区分兴趣 / 礼貌 / 废测 / 拒绝", True),
    "knowledge-base": ("知识库", "搭讪、聊天、约会、形象等主题", False),
    "lifecycle": ("阶段路线图", "吸引 → 平淡 → 暧昧 → 恋爱 → 长期", False),
    "damage-control": ("止损系统", "分级止损，什么时候该放弃", False),
    "self-diagnosis": ("自我诊断", "形象评分与短板定位", False),
    "realistic-scenarios": ("真实场景", "表白被拒 / 约会冷场等处理", False),
    "hard-value-reality": ("硬价值评估", "外貌 / 经济 / 地位的坦诚评估", False),
}


def read(p: Path) -> str:
    text = p.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").strip()


def png(path: Path, size: int) -> None:
    """程序化画图标：深色底 + 玫红爱心渐变，3x 超采样抗锯齿。"""
    ss = 3
    w = h = size
    bg_top = (20, 23, 30)
    bg_bot = (12, 14, 18)
    heart_top = (255, 154, 181)
    heart_bot = (224, 74, 124)
    px = bytearray()
    for y in range(h):
        for x in range(w):
            r = g = b = 0
            for sy in range(ss):
                for sx in range(ss):
                    fx = (x + (sx + .5) / ss) / w
                    fy = (y + (sy + .5) / ss) / h
                    # 背景竖直渐变
                    br, bg_, bb = (
                        bg_top[i] + (bg_bot[i] - bg_top[i]) * fy for i in range(3)
                    )
                    # 爱心隐函数 (x^2+y^2-1)^3 - x^2*y^3 <= 0
                    u = (fx - .5) * 2 / .74
                    v = -(fy - .52) * 2 / .74
                    f = (u * u + v * v - 1) ** 3 - u * u * v ** 3
                    if f <= 0:
                        t = (v + 1) / 2
                        r += heart_top[0] + (heart_bot[0] - heart_top[0]) * t
                        g += heart_top[1] + (heart_bot[1] - heart_top[1]) * t
                        b += heart_top[2] + (heart_bot[2] - heart_top[2]) * t
                    else:
                        r += br
                        g += bg_
                        b += bb
            n = ss * ss
            px += bytes((round(r / n), round(g / n), round(b / n), 255))

    raw = b"".join(b"\x00" + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    skill = read(SKILL_DIR / "SKILL.md")
    refs = []
    for rid, (label, desc, dflt) in REFS.items():
        f = SKILL_DIR / "references" / f"{rid}.md"
        if not f.exists():
            raise SystemExit(f"缺少参考资料: {f}")
        refs.append(
            {
                "id": rid,
                "label": label,
                "desc": desc,
                "dflt": dflt,
                "chars": len(read(f)),
                "content": read(f),
            }
        )

    payload = json.dumps(
        {"skill": skill, "refs": refs}, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")

    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    if "__KNOWLEDGE_JSON__" not in tpl:
        raise SystemExit("template.html 里找不到 __KNOWLEDGE_JSON__ 占位符")
    html = tpl.replace("__KNOWLEDGE_JSON__", payload)

    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(html, encoding="utf-8")

    # 每次内容变化就换缓存版本，避免手机上一直命中旧壳
    ver = hashlib.sha1(html.encode("utf-8")).hexdigest()[:8]
    sw = (HERE / "sw.js").read_text(encoding="utf-8").replace(
        "'dating-coach-v1'", f"'dating-coach-{ver}'"
    )
    (OUT / "sw.js").write_text(sw, encoding="utf-8")
    shutil.copy2(HERE / "manifest.webmanifest", OUT / "manifest.webmanifest")
    png(OUT / "icon-192.png", 192)
    png(OUT / "icon-512.png", 512)
    png(OUT / "apple-touch-icon.png", 180)

    kb = len(skill) + sum(r["chars"] for r in refs)
    print(f"已输出 {OUT}")
    print(f"  index.html          {(OUT / 'index.html').stat().st_size / 1024:.0f} KB")
    print(f"  技能 {len(skill)} 字 + 知识库 {kb - len(skill)} 字，合计 {kb} 字")
    print(f"  默认勾选 ≈ {len(skill) + sum(r['chars'] for r in refs if r['dflt'])} 字")


if __name__ == "__main__":
    main()
