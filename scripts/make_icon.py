# -*- coding: utf-8 -*-
"""重新生成谛听桌面图标 assets/diting.ico（墨底鎏金「谛」+ 听波三点）。

用法：pip install pillow && python scripts/make_icon.py
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 512
GOLD = (232, 184, 75)
INK = (18, 18, 30)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 深墨底圆角方形（谛听=神兽善听，墨黑+鎏金）
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=96, fill=INK + (255,))
d.ellipse([56, 56, S - 56, S - 56], outline=GOLD + (255,), width=6)  # 鎏金细环

font = None
for fp in ("C:/Windows/Fonts/simkai.ttf", "C:/Windows/Fonts/msyhbd.ttc",
           "C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(fp):
        font = ImageFont.truetype(fp, 300)
        break
d.text((S / 2, S / 2 - 10), "谛", font=font, fill=GOLD + (255,), anchor="mm")

# 底部听波纹（三点渐弱，寓意「听」）
for i, (r, a) in enumerate([(10, 255), (7, 170), (5, 90)]):
    cx = S / 2 - 40 + i * 40
    d.ellipse([cx - r, S - 100 - r, cx + r, S - 100 + r], fill=GOLD + (a,))

out = Path(__file__).resolve().parent.parent / "assets" / "diting.ico"
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"written: {out} ({out.stat().st_size} bytes)")
