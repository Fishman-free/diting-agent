"""生成谛听启动横幅的两块视觉资产（可重复运行，输出粘贴进源码）：

1. LOGO —— "DITING" ANSI Shadow 方块字（42 列 × 6 行）
2. HERO  —— 「听波」braille 画（30 列 × 15 行 = 60×60 点阵，与上游画布同宽）：
   左侧神兽之耳（耳轮 + 耳屏 + 耳垂），右侧三圈声波自耳前漾开，
   底部三点渐弱——与桌面图标 assets/diting.ico 同构（墨底鎏金、听波三点）。

用法：python -X utf8 scripts/make_banner_art.py
输出：
  - plain 段 → ui-tui/src/banner.ts（LOGO_ART / CADUCEUS_ART 数组）
  - rich  段 → hermes_cli/banner.py（HERMES_AGENT_LOGO / HERMES_CADUCEUS）
配色与旧版一致：#FFD700 鎏金 → #FFBF00 琥珀 → #CD7F32 青铜（自上而下渐深）。
"""

import math

# ── LOGO：ANSI Shadow "DITING" ──────────────────────────────────────

DITING_LOGO = [
    "██████╗ ██╗████████╗██╗███╗   ██╗ ██████╗ ",
    "██╔══██╗██║╚══██╔══╝██║████╗  ██║██╔════╝ ",
    "██║  ██║██║   ██║   ██║██╔██╗ ██║██║  ███╗",
    "██║  ██║██║   ██║   ██║██║╚██╗██║██║   ██║",
    "██████╔╝██║   ██║   ██║██║ ╚████║╚██████╔╝",
    "╚═════╝ ╚═╝   ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝ ",
]

# ── HERO：听波（braille 点阵作图）───────────────────────────────────

CELL_W, CELL_H = 30, 15          # 与旧双蛇杖画布同尺寸（30×15），布局数学零改动
DOTS_W, DOTS_H = CELL_W * 2, CELL_H * 4

# Unicode braille 点位：每字符 2×4 点，位序见下
_BRAILLE_BIT = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}


def _rasterize(draw) -> list[str]:
    """把 draw(x, y) 布尔函数栅格化为 braille 文本行。"""
    cells = [[0x2800] * CELL_W for _ in range(CELL_H)]
    for y in range(DOTS_H):
        for x in range(DOTS_W):
            if draw(x, y):
                cx, cy = x // 2, y // 4
                cells[cy][cx] |= _BRAILLE_BIT[(x % 2, y % 4)]
    return ["".join(chr(c) for c in row).rstrip() for row in cells]


def _arc(ox, oy, r, a0, a1, thick=1.6):
    """以 (ox, oy) 为心、角度 a0..a1（度，0° 朝右、逆时针）的圆弧。"""
    lo, hi = math.radians(min(a0, a1)), math.radians(max(a0, a1))

    def hit(x, y):
        dx, dy = x - ox, y - oy
        d = math.hypot(dx, dy)
        if abs(d - r) > thick:
            return False
        a = math.atan2(dy, dx)
        return lo <= a <= hi

    return hit


def _disc(ox, oy, r):
    return lambda x, y: (x - ox) ** 2 + (y - oy) ** 2 <= r * r


def _listening_waves():
    shapes = [
        # 耳轮：开口朝右的双层 C 弧（外圈 helix + 内圈耳甲）
        _arc(16, 30, 14, 100, 260, 1.6),
        _arc(17, 30, 8, 115, 245, 1.4),
        # 耳道：C 口内的一枚实心点
        _disc(20, 30, 1.8),
        # 耳垂：外弧下端的实心收笔
        _disc(12, 46, 2.4),
        # 三圈声波：自耳前向右漾开，越远越收角
        _arc(22, 30, 12, -60, 60, 1.4),
        _arc(22, 30, 22, -50, 50, 1.4),
        _arc(22, 30, 32, -40, 40, 1.4),
        # 听波三点（致敬图标底部三点渐弱）
        _disc(26, 54, 2.0),
        _disc(34, 55, 1.5),
        _disc(42, 54, 1.0),
    ]
    return lambda x, y: any(s(x, y) for s in shapes)


HERO_ART = _rasterize(_listening_waves())

# 自上而下的鎏金渐变（与旧双蛇杖同一套色阶，行号 → rich 色值）
HERO_COLORS = ["#CD7F32", "#CD7F32", "#FFBF00", "#FFBF00", "#FFD700", "#FFD700",
               "#FFD700", "#FFD700", "#FFBF00", "#FFBF00", "#CD7F32", "#CD7F32",
               "#B8860B", "#B8860B", "#B8860B"]
LOGO_COLORS = ["#FFD700", "#FFD700", "#FFBF00", "#FFBF00", "#CD7F32", "#CD7F32"]


def main() -> None:
    print("=" * 20, "LOGO plain (banner.ts LOGO_ART)", "=" * 20)
    for line in DITING_LOGO:
        print(line)
    print()
    print("=" * 20, "LOGO rich (banner.py HERMES_AGENT_LOGO)", "=" * 20)
    for i, line in enumerate(DITING_LOGO):
        weight = "bold " if i < 2 else ""
        print(f"[{weight}{LOGO_COLORS[i]}]{line}[/]")
    print()
    print("=" * 20, "HERO plain (banner.ts CADUCEUS_ART)", "=" * 20)
    for line in HERO_ART:
        print(line)
    print()
    print("=" * 20, "HERO rich (banner.py HERMES_CADUCEUS)", "=" * 20)
    for i, line in enumerate(HERO_ART):
        print(f"[{HERO_COLORS[i]}]{line}[/]")
    print()
    print(f"logo width={max(map(len, DITING_LOGO))}  hero width={max(map(len, HERO_ART))} rows={len(HERO_ART)}")


if __name__ == "__main__":
    main()
