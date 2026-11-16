#!/usr/bin/env python
"""Peça 03 — Pista em Queda (direção C, trilho 3-2-1). Python padrão + Chrome + ffmpeg.

Comandos (rodar da pasta da peça ou de qualquer lugar):
  python build_pista.py render --clues "pista 1|pista 2|pista 3" [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet]
        [--transparent] [--demo] [--scale 1] [--name NOME] [--at 2.5] [--browser CAMINHO]
  --kind mp4    vídeo H.264 com fundo preto
  --kind webm   vídeo VP9 com transparência (use --transparent; sem logo, para pôr sobre vídeo)
  --kind still  um quadro PNG (em --at segundos) para deck e e-mail
  --kind sheet  folha de contato com a zona segura sombreada (checagem)
Aceita de 1 a 3 pistas; cada pista fica ~4 s. Pontos: 3, 2, 1 (a pista N vale 4-N).
Saídas em ../9x16 ou ../16x9, com o nome "Pista em Queda <aspecto> <nome>.<ext>".
"""
import argparse, base64, importlib.util, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS = 30
HOLD = 4.0            # segundos por pista
PURPLE = "#00C2A8"    # cor de destaque (marca demo, ver assets/brand)

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=929, logo_y=265, logo_h=64, lab_y=430, lab_fs=54,
                 rail_y=560, rail_h=260, gap=18, num_fs=190, cap_y=850, cap_fs=40, clue_y=1000, clue_fs=70,
                 clue_w=857, demo_y=1470, demo_fs=26),
    "16x9": dict(W=1920, H=1080, left=160, right=1160, logo_y=96, logo_h=56, lab_y=215, lab_fs=44,
                 rail_y=290, rail_h=200, gap=16, num_fs=150, cap_y=520, cap_fs=32, clue_y=620, clue_fs=76,
                 clue_w=1520, demo_y=985, demo_fs=24),
}


def build_html(aspect, clues, transparent, demo):
    L = LAYOUT[aspect]
    W, H = L["W"], L["H"]
    n = len(clues)
    total = 0.9 + HOLD * n + 0.7 + 0.4
    sw = (L["right"] - L["left"] - 2 * L["gap"]) // 3
    logo = ""
    if not transparent:
        uri = "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
        logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (uri, L["left"], L["logo_y"], L["logo_h"])
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    blocks, nums = "", ""
    for i in range(3):
        x = L["left"] + i * (sw + L["gap"])
        blocks += '<div class="abs blk" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>' % (x, L["rail_y"], sw, L["rail_h"])
        nums += ('<div class="abs num" id="n%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx;font-size:%dpx">%d</div>'
                 % (i + 1, x, L["rail_y"], sw, L["rail_h"], L["num_fs"], 3 - i))
    labs = "".join('<span class="lab" id="lab%d">PISTA %d DE %d</span>' % (i + 1, i + 1, n) for i in range(n))
    clue_divs = ""
    for i, c in enumerate(clues):
        words = "".join('<span class="m"><span class="w">%s</span></span> ' % w for w in c.split())
        clue_divs += '<div class="abs clue" id="c%d" style="left:%dpx;top:%dpx;width:%dpx;font-size:%dpx">%s</div>' % (
            i + 1, L["left"], L["clue_y"], L["clue_w"], L["clue_fs"], words)
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE AS PISTAS ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    js_steps = []
    for k in range(1, n):          # transição da pista k para k+1
        t = 0.9 + HOLD * k
        js_steps.append(
            "tl.to('#slab',{x:%d,duration:0.55,ease:'power4.out'},%.2f);"
            "tl.to('#n%d',{color:'%s',opacity:.32,duration:0.3,ease:'power2.out'},%.2f);"
            "tl.to('#n%d',{color:'#000000',duration:0.2,ease:'none'},%.2f);"
            "tl.to('#c%d',{autoAlpha:0,duration:0.25,ease:'power2.in'},%.2f);"
            "tl.set('#lab%d',{autoAlpha:0},%.2f);tl.set('#lab%d',{autoAlpha:1},%.2f);"
            "tl.fromTo('#c%d .w',{yPercent:115},{yPercent:0,duration:0.8,ease:'expo.out',stagger:0.035},%.2f);"
            "tl.fromTo('#c%d',{autoAlpha:0},{autoAlpha:1,duration:0.05},%.2f);"
            % (k * (sw + L["gap"]), t, k, PURPLE, t, k + 1, t + 0.15, k, t, k, t, k + 1, t, k + 1, t + 0.2, k + 1, t + 0.2))
    js = """
var tl=gsap.timeline({paused:true});
tl.set('.clue',{autoAlpha:0},0);tl.set('.lab',{autoAlpha:0},0);tl.set('#lab1',{autoAlpha:1},0.3);
tl.fromTo('.blk',{opacity:0,y:30},{opacity:1,y:0,duration:0.7,ease:'expo.out',stagger:0.08},0.05);
tl.fromTo('.num',{opacity:0},{opacity:1,duration:0.4,ease:'power2.out',stagger:0.08},0.15);
tl.fromTo('#lab1',{y:20,opacity:0},{y:0,opacity:1,duration:0.6,ease:'expo.out'},0.3);
%s
tl.fromTo('#slab',{scaleX:0,transformOrigin:'0 50%%'},{scaleX:1,duration:0.5,ease:'expo.out'},0.45);
tl.fromTo('#n1',{color:'%s'},{color:'#000000',duration:0.2,ease:'none'},0.6);
tl.set('#c1',{autoAlpha:1},0.8);
tl.fromTo('#c1 .w',{yPercent:115},{yPercent:0,duration:0.8,ease:'expo.out',stagger:0.035},0.8);
%s
tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);
tl.set({},{},%.2f);
window.__timelines=window.__timelines||{};window.__timelines['pista']=tl;
""" % ("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);" if logo else "", PURPLE, "\n".join(js_steps), total - 0.4, total)
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Pista Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Pista Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
.blk{border:5px solid %(P)s;border-radius:28px}
#slab{position:absolute;left:%(left)dpx;top:%(rail_y)dpx;width:%(sw)dpx;height:%(rail_h)dpx;border-radius:28px;background:%(P)s}
.num{display:flex;align-items:center;justify-content:center;font-family:'Pista Head',sans-serif;font-weight:900;color:%(P)s;line-height:1}
#lab{position:absolute;left:%(left)dpx;top:%(lab_y)dpx;height:%(lab_fs)dpx}
.lab{position:absolute;left:0;top:0;white-space:nowrap;font:700 %(lab_fs)dpx/1 'Pista Label',sans-serif;color:#FFFFFF;%(shadow)s}
#cap{left:%(left)dpx;top:%(cap_y)dpx;font:700 %(cap_fs)dpx/1 'Pista Label',sans-serif;color:%(P)s;letter-spacing:.02em;%(shadow)s}
.clue{font-family:'Pista Head',sans-serif;font-weight:900;line-height:1.28;color:#FFFFFF;%(shadow)s}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:0 .02em .14em}.w{display:inline-block}
#demo{font:700 %(demo_fs)dpx/1 'Pista Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="pista" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(total).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="lab">%(labs)s</div>
%(blocks)s<div id="slab"></div>%(nums)s
<div id="cap" class="abs">PONTOS EM JOGO</div>
%(clue_divs)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada
%(js)s});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, P=PURPLE, left=L["left"], rail_y=L["rail_y"], sw=sw, rail_h=L["rail_h"], lab_y=L["lab_y"],
                       lab_fs=L["lab_fs"], cap_y=L["cap_y"], cap_fs=L["cap_fs"], demo_fs=L["demo_fs"], shadow=shadow, total=total,
                       FPS=FPS, logo=logo, labs=labs, blocks=blocks, nums=nums, clue_divs=clue_divs, demo_div=demo_div, js=js), total


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--clues", required=True)
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=2.5)
    ap.add_argument("--browser")
    a = ap.parse_args()
    clues = [c.strip() for c in a.clues.split("|") if c.strip()][:3]
    if not clues:
        sys.exit("passe de 1 a 3 pistas em --clues")
    if a.kind == "webm" and not a.transparent:
        a.transparent = True
    html, total = build_html(a.aspect, clues, a.transparent, a.demo)
    tag = "transp" if a.transparent else "preto"
    name = a.name or ("%s %d pista%s" % (tag, len(clues), "s" if len(clues) > 1 else ""))
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Pista em Queda %s %s" % (a.aspect, name)
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        n = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], a.at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.2, 0.9 + 1.5, 0.9 + HOLD + 1.5, 0.9 + 2 * HOLD + 1.5, total - 0.9, total - 0.3][: 6]
            ts = [t for t in ts if t < total][:6]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "pista_f.png")
                open(p, "wb").write(sess.frame(info["id"], t, "png"))
                im = Image.open(p).convert("RGBA")
                ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
                w, h = im.size; sh = (255, 0, 0, 70)
                if a.aspect == "9x16":
                    d.rectangle((0, 0, w, h * .12), fill=sh); d.rectangle((0, h * .8, w, h), fill=sh); d.rectangle((w * .86, 0, w, h), fill=sh)
                else:   # 16:9: margem de 5%
                    d.rectangle((0, 0, w, h * .05), fill=sh); d.rectangle((0, h * .95, w, h), fill=sh)
                    d.rectangle((0, 0, w * .05, h), fill=sh); d.rectangle((w * .95, 0, w, h), fill=sh)
                im = Image.alpha_composite(im if not a.transparent else Image.alpha_composite(Image.new("RGBA", im.size, (40, 90, 60, 255)), im), ov).convert("RGB")
                ims.append(im)
            tw = 400 if a.aspect == "9x16" else 640
            th = int(tw * ims[0].height / ims[0].width)
            sheet = Image.new("RGB", (len(ims) * (tw + 12) + 12, th + 24), (24, 24, 24))
            for i, im in enumerate(ims):
                sheet.paste(im.resize((tw, th), Image.LANCZOS), (12 + i * (tw + 12), 12))
            out = os.path.join(HERE, "qa", "folha %s %s.jpg" % (a.aspect, name))
            sheet.save(out, quality=88)
            print(out, "(quadros em", ", ".join("%.1f" % t for t in ts), "s)")
            return
        ext = "mp4" if a.kind == "mp4" else "webm"
        out = os.path.join(outdir, "%s.%s" % (base, ext))
        part = out + ".part." + ext
        if ext == "mp4":
            cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(info["fps"]), "-c:v", "mjpeg", "-i", "-",
                   "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart", part]
            fmt = "jpeg"
        else:
            cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(info["fps"]), "-c:v", "png", "-i", "-",
                   "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24", "-auto-alt-ref", "0", "-row-mt", "1", part]
            fmt = "png"
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.time()
        try:
            for i in range(n):
                ff.stdin.write(sess.frame(info["id"], i / info["fps"], fmt))
                if i % 30 == 0:
                    print("\r  frame %d/%d" % (i, n), end="", flush=True)
            ff.stdin.close()
        except BrokenPipeError:
            pass
        if ff.wait() != 0 or not os.path.isfile(part):
            sys.exit("ffmpeg falhou")
        os.replace(part, out)
        print("\r  %d quadros, %.1fs, em %.0fs -> %s" % (n, info["dur"], time.time() - t0, out))
    finally:
        sess.close()


if __name__ == "__main__":
    main()
