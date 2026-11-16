#!/usr/bin/env python
"""Peça 04 — Revelação do Jogador (direção A: selo central + trilho de pistas). Python padrão + Chrome + ffmpeg.

  python build_revelacao.py render --player "RAFAEL MOURA" --photo FOTO.png --hit 2 [--aspect 9x16|16x9]
        [--kind mp4|webm|still|sheet] [--transparent] [--demo] [--scale 1] [--name NOME] [--at 5] [--browser CAMINHO]
  --player  nome do jogador (caixa alta recomendada)
  --photo   foto quadrada do jogador (PNG/JPG); recorte em círculo; use foto de boa resolução (>= 600 px)
  --hit     em qual pista acertou (1, 2 ou 3; vale 3, 2 ou 1 ponto); use --hit 0 para "ninguém acertou" (nenhum bloco acende)
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo, para pôr sobre vídeo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Revelação do Jogador <aspecto> <nome>.<ext>".
Movimento principal: o anel do selo se desenha. Secundários: o nome sobe palavra por palavra e o bloco da pista que acertou acende.
"""
import argparse, base64, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
TOTAL = 7.0

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=929, logo_y=265, logo_h=64, lab_y=430, lab_fs=54, circ=440, circ_x=300, circ_y=520,
                 name_cx=500, name_y=1050, name_fs=92, pistas_y=1190, pistas_fs=40, chip_y=1250, chip_h=200, gap=18,
                 chip_x0=72, chip_x1=929, demo_y=1480, demo_fs=26),
    "16x9": dict(W=1920, H=1080, left=160, right=1760, logo_y=96, logo_h=56, lab_y=250, lab_fs=44, circ=560, circ_x=160, circ_y=270,
                 name_cx=1250, name_y=420, name_fs=118, pistas_y=600, pistas_fs=36, chip_y=670, chip_h=200, gap=20,
                 chip_x0=800, chip_x1=1740, demo_y=985, demo_fs=24),
}


def build_html(aspect, player, photo, hit, transparent, demo):
    L = LAYOUT[aspect]
    W, H = L["W"], L["H"]
    wide = aspect == "16x9"
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    ext = os.path.splitext(photo)[1].lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    puri = "data:image/%s;base64,%s" % (mime, base64.b64encode(open(photo, "rb").read()).decode())
    luri = ""
    if not transparent:
        luri = "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    d = L["circ"]
    r = d / 2 - 8
    circ = 2 * 3.14159265 * r
    words = "".join('<span class="m"><span class="w">%s</span></span> ' % w for w in player.split())
    sw = (L["chip_x1"] - L["chip_x0"] - 2 * L["gap"]) // 3
    chips = ""
    for i, (lb, pt) in enumerate([("PISTA 1", "3"), ("PISTA 2", "2"), ("PISTA 3", "1")]):
        x = L["chip_x0"] + i * (sw + L["gap"])
        chips += ('<div class="abs chip" id="chp%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
                  '<div class="abs chp" id="cht%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"><span class="cl">%s</span><span class="cn">%s</span></div>'
                  % (i + 1, x, L["chip_y"], sw, L["chip_h"], i + 1, x, L["chip_y"], sw, L["chip_h"], lb, pt))
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, L["left"], L["logo_y"], L["logo_h"]) if luri else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE O JOGADOR E A FOTO ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    name_style = "left:%dpx;top:%dpx;width:%dpx;text-align:%s;font-size:%dpx" % (
        (L["name_cx"] - 450 if not wide else 800), L["name_y"], 900 if not wide else 960, "center" if not wide else "left", L["name_fs"])
    lab_left = L["left"] if not wide else 800
    pist_left = L["left"] if not wide else 800
    js = ["tl.set('#lab,#pistas,.chip,.chp,#name .w',{autoAlpha:0},0);",
          "tl.fromTo('#lab',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.3);",
          "tl.fromTo('#ring',{attr:{'stroke-dashoffset':%.1f}},{attr:{'stroke-dashoffset':0},duration:1.3,ease:'power3.out'},0.45);" % circ,
          "tl.fromTo('#photo',{autoAlpha:0,scale:1.07},{autoAlpha:1,scale:1,duration:1.2,ease:'expo.out'},0.5);",
          "tl.set('#name .w',{autoAlpha:1},1.5);tl.fromTo('#name .w',{yPercent:115},{yPercent:0,duration:0.8,ease:'expo.out',stagger:0.08},1.5);",
          "tl.fromTo('#pistas',{autoAlpha:0},{autoAlpha:1,duration:0.4},2.5);",
          "tl.fromTo('.chip,.chp',{autoAlpha:0,y:30},{autoAlpha:1,y:0,duration:0.7,ease:'expo.out',stagger:0.07},2.7);"]
    if hit in (1, 2, 3):
        others = ",".join("#chp%d,#cht%d" % (i, i) for i in (1, 2, 3) if i != hit)
        js.append("tl.to('#chp%d',{backgroundColor:'%s',duration:0.4,ease:'power2.out'},4.0);tl.to('#cht%d',{color:'#000000',duration:0.3},4.1);" % (hit, P, hit))
        js.append("tl.to('%s',{opacity:.35,duration:0.4},4.0);" % others)
    if not luri:
        pass
    else:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)
    html = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Rev Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Rev Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#lab{left:%(lab_left)dpx;top:%(lab_y)dpx;font:700 %(lab_fs)dpx/1 'Rev Label',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
#photo{position:absolute;left:%(cx)dpx;top:%(cy)dpx;width:%(d)dpx;height:%(d)dpx;border-radius:50%%;object-fit:cover;background:#fff;transform-origin:50%% 50%%}
#ringsvg{position:absolute;left:%(cx)dpx;top:%(cy)dpx}
#name{position:absolute;%(name_style)s;font-family:'Rev Head',sans-serif;font-weight:900;line-height:1.2;color:#fff;%(shadow)s}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:0 .02em .14em}.w{display:inline-block}
#pistas{left:%(pist_left)dpx;top:%(pistas_y)dpx;font:700 %(pistas_fs)dpx/1 'Rev Label',sans-serif;color:%(P)s;%(shadow)s}
.chip{border:5px solid %(P)s;border-radius:28px;background:transparent}
.chp{display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:'Rev Label',sans-serif;font-weight:700;color:%(P)s}
.cl{font-size:36px}.cn{font-family:'Rev Head',sans-serif;font-weight:900;font-size:92px;line-height:1}
#demo{font:700 %(demo_fs)dpx/1 'Rev Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="rev" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="lab" class="abs">A RESPOSTA</div>
<img id="photo" alt="" src="%(puri)s">
<svg id="ringsvg" width="%(d)d" height="%(d)d" viewBox="0 0 %(d)d %(d)d"><circle id="ring" cx="%(c)s" cy="%(c)s" r="%(r)s" fill="none" stroke="%(P)s" stroke-width="14" stroke-linecap="round" transform="rotate(-90 %(c)s %(c)s)" stroke-dasharray="%(circ).1f" stroke-dashoffset="%(circ).1f"/></svg>
<div id="name">%(words)s</div>
<div id="pistas" class="abs">PISTAS</div>
%(chips)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['rev']=tl;});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, shadow=shadow, P=P, lab_left=lab_left, lab_y=L["lab_y"], lab_fs=L["lab_fs"], cx=L["circ_x"], cy=L["circ_y"], d=d,
                       name_style=name_style, pist_left=pist_left, pistas_y=L["pistas_y"], pistas_fs=L["pistas_fs"], demo_fs=L["demo_fs"],
                       TOTAL=TOTAL, FPS=FPS, logo=logo, puri=puri, c=d / 2, r="%.1f" % r, circ=circ, words=words, chips=chips, demo_div=demo_div, js=js)
    return html


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--player", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--hit", type=int, default=2, choices=[0, 1, 2, 3])
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=5.0)
    ap.add_argument("--browser")
    a = ap.parse_args()
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    html = build_html(a.aspect, a.player, a.photo, a.hit, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Revelação do Jogador %s %s" % (a.aspect, name)
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
            ts = [0.3, 0.9, 1.8, 3.2, 5.0, 6.7]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "rev_f.png")
                open(p, "wb").write(sess.frame(info["id"], t, "png"))
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
