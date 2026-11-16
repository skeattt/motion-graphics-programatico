#!/usr/bin/env python
"""Peça 05 — Escada às Cegas (direção C: selos numerados + nome sublinhado + cadeado). Python padrão + Chrome + ffmpeg.

  python build_escada.py render --names "NOME 1|NOME 2|NOME 3|NOME 4|NOME 5" [--order 3,1,4,2,5] [--title "RANKING · 5 VAGAS"]
        [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet] [--transparent] [--demo] [--scale 1] [--name NOME] [--at 8] [--browser CAMINHO]
  --names  um nome por vaga, da 1ª à 5ª, separados por "|"; deixe vazio ("A||C") para a vaga ficar com "?" até o fim
  --order  ordem em que as vagas são preenchidas (números das vagas, separados por vírgula); padrão: de cima para baixo
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo, para pôr sobre vídeo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Escada às Cegas <aspecto> <nome>.<ext>".
Movimento principal: o nome sobe na vaga e o selo numerado acende. Secundários: o sublinhado de destaque se desenha e o cadeado trava.
"""
import argparse, base64, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, STEP, HOLD = 0.9, 1.3, 1.6

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=929, logo_y=265, logo_h=64, lab_y=430, lab_fs=54, y0=520, step=170, badge=130,
                 badge_fs=72, name_fs=64, lock=56, demo_y=1480, demo_fs=26),
    "16x9": dict(W=1920, H=1080, left=160, right=1160, logo_y=70, logo_h=48, lab_y=150, lab_fs=44, y0=220, step=150, badge=120,
                 badge_fs=66, name_fs=60, lock=52, demo_y=985, demo_fs=24),
}


def total(n):
    return INTRO + STEP * n + HOLD


def build_html(aspect, names, order, title, transparent, demo):
    L = LAYOUT[aspect]
    W, H = L["W"], L["H"]
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    TOTAL = total(len(order))
    b, gap = L["badge"], 38
    nx = L["left"] + b + gap
    nw = L["right"] - nx
    lock = ('<svg width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="5" y="11" width="14" height="10" rx="2" fill="%s"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>') % (L["lock"], L["lock"], P, P)
    rows = ""
    for i in range(5):
        y = L["y0"] + i * L["step"]
        nm = names[i] if i < len(names) else ""
        words = "".join('<span class="m"><span class="w">%s</span></span> ' % w for w in nm.split())
        rows += ('<div class="abs bdg" id="bg%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%d</div>'
                 '<div class="abs hole" id="h%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">?</div>'
                 '<div class="abs nm" id="nm%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%s</div>'
                 '<div class="abs ul" id="ul%d" style="left:%dpx;top:%dpx;width:%dpx"></div>'
                 '<div class="abs lk" id="lk%d" style="left:%dpx;top:%dpx">%s</div>'
                 % (i, L["left"], y, b, b, i + 1,
                    i, nx, y + 6, nw, b - 12,
                    i, nx, y, nw - L["lock"] - 24, b - 12, words,
                    i, nx, y + b - 8, nw,
                    i, L["right"] - L["lock"] - 22, y + (b - 12 - L["lock"]) // 2, lock))
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, L["left"], L["logo_y"], L["logo_h"]) if luri else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE OS NOMES ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    js = ["tl.set('.nm .w,.lk',{autoAlpha:0},0);tl.set('.ul',{scaleX:0},0);",
          "tl.fromTo('#lab',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.2);",
          "tl.fromTo('.bdg',{autoAlpha:0,y:30},{autoAlpha:.35,y:0,duration:0.7,ease:'expo.out',stagger:0.05},0.3);",
          "tl.fromTo('.hole',{autoAlpha:0,y:30},{autoAlpha:1,y:0,duration:0.7,ease:'expo.out',stagger:0.05},0.3);"]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    for k, s in enumerate(order):
        i, t = s - 1, INTRO + k * STEP
        js.append("tl.to('#h%d',{autoAlpha:0,duration:0.25,ease:'power2.in'},%.2f);" % (i, t))
        js.append("tl.set('#nm%d .w',{autoAlpha:1},%.2f);tl.fromTo('#nm%d .w',{yPercent:115},{yPercent:0,duration:0.7,ease:'expo.out',stagger:0.06},%.2f);" % (i, t + 0.15, i, t + 0.15))
        js.append("tl.to('#ul%d',{scaleX:1,duration:0.55,ease:'power3.out'},%.2f);" % (i, t + 0.35))
        js.append("tl.to('#bg%d',{opacity:1,duration:0.2},%.2f);tl.fromTo('#bg%d',{scale:1.14},{scale:1,duration:0.5,ease:'expo.out'},%.2f);" % (i, t + 0.55, i, t + 0.55))
        js.append("tl.fromTo('#lk%d',{autoAlpha:0,y:-16},{autoAlpha:1,y:0,duration:0.35,ease:'power3.out'},%.2f);" % (i, t + 0.75))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)
    html = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Esc Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Esc Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#lab{left:%(left)dpx;top:%(lab_y)dpx;font:700 %(lab_fs)dpx/1 'Esc Label',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
.bdg{border-radius:50%%;background:%(P)s;opacity:.35;display:flex;align-items:center;justify-content:center;font:900 %(badge_fs)dpx/1 'Esc Head',sans-serif;color:#000}
.hole{border:3px dashed #5a5a5a;border-radius:16px;display:flex;align-items:center;justify-content:center;font:900 %(badge_fs)dpx/1 'Esc Head',sans-serif;color:#5a5a5a}
.nm{font-family:'Esc Head',sans-serif;font-weight:900;font-size:%(name_fs)dpx;color:#fff;white-space:nowrap;overflow:visible;display:flex;align-items:center;gap:.25em;%(shadow)s}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:0 .02em .14em;line-height:1.2}.w{display:inline-block}
.ul{height:5px;background:%(P)s;border-radius:3px;transform-origin:0 50%%}
#demo{font:700 %(demo_fs)dpx/1 'Esc Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="esc" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="lab" class="abs">%(title)s</div>
%(rows)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

document.querySelectorAll('.nm').forEach(function(el){var fs=%(name_fs)d;while(el.scrollWidth>el.clientWidth&&fs>30){fs-=2;el.style.fontSize=fs+'px';}});
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['esc']=tl;});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, shadow=shadow, P=P, left=L["left"], lab_y=L["lab_y"], lab_fs=L["lab_fs"], badge_fs=L["badge_fs"],
                       name_fs=L["name_fs"], demo_fs=L["demo_fs"], TOTAL=TOTAL, FPS=FPS, logo=logo, title=title, rows=rows, demo_div=demo_div, js=js)
    return html


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--names", required=True)
    ap.add_argument("--order", default="")
    ap.add_argument("--title", default="RANKING · 5 VAGAS")
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=-1)
    ap.add_argument("--browser")
    a = ap.parse_args()
    names = [n.strip() for n in a.names.split("|")][:5]
    filled = [i + 1 for i, n in enumerate(names) if n]
    order = [int(x) for x in a.order.split(",") if x.strip()] if a.order else filled
    if sorted(order) != sorted(set(order)) or any(s not in filled for s in order):
        sys.exit("--order precisa citar só vagas com nome, sem repetir")
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    TOTAL = total(len(order))
    html = build_html(a.aspect, names, order, a.title, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Escada às Cegas %s %s" % (a.aspect, name)
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        n = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            at = a.at if a.at >= 0 else TOTAL - HOLD + 0.8
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.5, INTRO + 0.4, INTRO + STEP + 0.6, INTRO + 2 * STEP + 1.0, TOTAL - HOLD + 0.3, TOTAL - 0.5]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "esc_f.png")
                open(p, "wb").write(sess.frame(info["id"], min(t, TOTAL - 0.05), "png"))
                im = Image.open(p).convert("RGBA")
                if a.transparent:
                    im = Image.alpha_composite(Image.new("RGBA", im.size, (40, 90, 60, 255)), im)
                ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
                w, h = im.size; sh = (255, 0, 0, 70)
                if a.aspect == "9x16":
                    d.rectangle((0, 0, w, h * .12), fill=sh); d.rectangle((0, h * .8, w, h), fill=sh); d.rectangle((w * .86, 0, w, h), fill=sh)
                else:
                    d.rectangle((0, 0, w, h * .05), fill=sh); d.rectangle((0, h * .95, w, h), fill=sh)
                    d.rectangle((0, 0, w * .05, h), fill=sh); d.rectangle((w * .95, 0, w, h), fill=sh)
                ims.append(Image.alpha_composite(im, ov).convert("RGB"))
            tw = 400 if a.aspect == "9x16" else 640
            th = int(tw * ims[0].height / ims[0].width)
            sheet = Image.new("RGB", (len(ims) * (tw + 12) + 12, th + 24), (24, 24, 24))
            for i, im in enumerate(ims):
                sheet.paste(im.resize((tw, th), Image.LANCZOS), (12 + i * (tw + 12), 12))
            out = os.path.join(HERE, "qa", "folha %s %s.jpg" % (a.aspect, name))
            sheet.save(out, quality=88)
            print(out)
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
