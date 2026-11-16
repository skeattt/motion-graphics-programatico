#!/usr/bin/env python
"""Gera a marca de demonstração (logo.png) e a foto genérica (foto-demo.png) usadas nos exemplos.
Troque estes dois arquivos pela sua marca e pelas suas fotos (com direito de uso)."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
ACCENT = (0, 194, 168)

# logo: palavra em branco + ponto na cor de destaque, fundo transparente
f = ImageFont.truetype(os.path.join(FONTS, "Inter-Black.ttf"), 120)
text = "MOTION LAB"
box = f.getbbox(text)
w, h = box[2] - box[0], box[3] - box[1]
im = Image.new("RGBA", (w + 70, h + 20), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.text((-box[0], 10 - box[1]), text, font=f, fill=(255, 255, 255, 255))
d.ellipse((w + 20, h - 30, w + 60, h + 10), fill=ACCENT + (255,))
im.save(os.path.join(HERE, "logo.png"))

# foto demo: silhueta genérica em degradê (nenhuma pessoa real)
S = 900
ph = Image.new("RGB", (S, S))
pd = ImageDraw.Draw(ph)
for y in range(S):
    k = y / S
    pd.line((0, y, S, y), fill=(int(20 + 30 * k), int(40 + 90 * (1 - k)), int(60 + 70 * (1 - k))))
pd.ellipse((S * .33, S * .16, S * .67, S * .50), fill=(14, 16, 20))
pd.rounded_rectangle((S * .18, S * .52, S * .82, S * 1.15), radius=int(S * .2), fill=(14, 16, 20))
ph.save(os.path.join(HERE, "foto-demo.png"))
print("ok")
