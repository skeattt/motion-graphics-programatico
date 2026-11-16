#!/usr/bin/env python
"""Peça 07 — Grade de Dicas (direção C: grade 5x4 de 20 dicas, cada uma valendo 21 - n pontos). Python padrão + Chrome + ffmpeg.

  python build_grade.py render --clues "dica 1|dica 2|..." --hit 9 [--title "QUEM É? · QUANTO ANTES, MAIS VALE"] [--step 1.6]
        [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet] [--transparent] [--demo] [--scale 1] [--name NOME] [--at S] [--browser CAMINHO]
  --clues  texto de cada dica aberta, na ordem, separados por "|" (até 20; dica vazia acende sem texto)
  --hit    número da dica em que alguém acertou (1 a 20); 0 = ninguém acertou (abre todas as dicas dadas em --clues)
  --step   segundos por dica (padrão 1.6)
  --demo   marca "DEMO" na tela; sem --clues, usa textos "Dica N de demonstração."
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo, para pôr sobre vídeo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Grade de Dicas <aspecto> <nome>.<ext>".
Movimento principal: a dica da vez acende na cor de destaque na grade. Secundários: o valor da dica anterior é riscado e esmaece; o texto da dica sobe palavra por palavra.
"""
import argparse, base64, html as H_, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, HOLD = 1.0, 2.6
NCLUES, COLS = 20, 5

# grade: left/top, tile, gap; painel (texto da dica e faixa final): px, py, pw, ph
LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, logo_y=292, logo_h=60, lab_y=410, lab_fs=40, gy=480, tile=152, gap=18, lb_fs=26, pt_fs=66,
                 px=72, py=1210, pw=832, ph=250, cl_fs=28, tx_fs=46, bn_fs=58, bs_fs=36, demo_y=1490, demo_fs=24),
    "16x9": dict(W=1920, H=1080, left=160, logo_y=80, logo_h=48, lab_y=172, lab_fs=36, gy=236, tile=134, gap=16, lb_fs=22, pt_fs=60,
                 px=1000, py=380, pw=760, ph=260, cl_fs=26, tx_fs=44, bn_fs=58, bs_fs=34, demo_y=970, demo_fs=22),
}


def total(n, step):
    return INTRO + step * n + HOLD


def esc(s):
    return H_.escape(s, quote=False)


def build_html(aspect, clues, hit, title, step, transparent, demo):
    L = LAYOUT[aspect]
    W, H = L["W"], L["H"]
    n = hit if hit else len(clues)
    TOTAL = total(n, step)
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    t, g = L["tile"], L["gap"]
    tiles = ""
    for i in range(NCLUES):
        r, c = divmod(i, COLS)
        x, y = L["left"] + c * (t + g), L["gy"] + r * (t + g)
        pts = NCLUES - i
        tiles += ('<div class="abs tile" id="t%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">'
                  '<div class="ly fut"><span class="lb">%d</span><span class="pt">%d</span></div>'
                  '<div class="ly used"><span class="lb">%d</span><span class="pt">%d<span class="st"></span></span></div>'
                  '<div class="ly cur"><span class="lb">%d</span><span class="pt">%d</span></div></div>'
                  % (i, x, y, t, t, i + 1, pts, i + 1, pts, i + 1, pts))
    panels = ""
    for k in range(n):
        txt = clues[k] if k < len(clues) else ""
        words = "".join('<span class="m"><span class="w">%s</span></span> ' % esc(w) for w in txt.split())
        panels += ('<div class="abs cl" id="c%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">'
                   '<div class="ck">DICA %d · VALE %d</div><div class="ct">%s</div></div>'
                   % (k, L["px"], L["py"], L["pw"], L["ph"], k + 1, NCLUES - k, words))
    if hit:
        pts = NCLUES - hit + 1
        big, small, bcls = "ACERTOU NA DICA %d" % hit, "%d %s" % (pts, "PONTO" if pts == 1 else "PONTOS"), "bn"
    else:
        big, small, bcls = "NINGUÉM ACERTOU", "0 PONTOS", "bn none"
    bh = int(L["bn_fs"] * 1.2 + L["bs_fs"] * 1.2 + 56)
    banner = ('<div class="abs %s" id="bn" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"><div class="b1">%s</div><div class="b2">%s</div></div>'
              % (bcls, L["px"], L["py"], L["pw"], bh, big, small))
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, L["left"], L["logo_y"], L["logo_h"]) if luri else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE AS DICAS ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    js = ["tl.set('.used,.cur,.cl,#bn',{autoAlpha:0},0);tl.set('.st',{scaleX:0},0);tl.set('.cl .w',{yPercent:115},0);",
          "tl.fromTo('#lab',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.2);",
          "tl.fromTo('.tile',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out',stagger:0.025},0.3);"]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    for k in range(n):
        s = INTRO + k * step
        if k:
            j = k - 1
            js.append("tl.to('#t%d .cur',{autoAlpha:0,duration:0.25},%.2f);tl.to('#t%d .used',{autoAlpha:1,duration:0.25},%.2f);"
                      "tl.to('#t%d .st',{scaleX:1,duration:0.4,ease:'power3.out'},%.2f);" % (j, s, j, s, j, s + 0.1))
            js.append("tl.to('#c%d',{autoAlpha:0,duration:0.2,ease:'power2.in'},%.2f);" % (j, s))
        js.append("tl.to('#t%d .fut',{autoAlpha:0,duration:0.15},%.2f);tl.to('#t%d .cur',{autoAlpha:1,duration:0.15},%.2f);"
                  "tl.fromTo('#t%d',{scale:1.1},{scale:1,duration:0.55,ease:'expo.out'},%.2f);" % (k, s, k, s, k, s))
        js.append("tl.set('#c%d',{autoAlpha:1},%.2f);tl.fromTo('#c%d .ck',{autoAlpha:0,x:-16},{autoAlpha:1,x:0,duration:0.4,ease:'expo.out'},%.2f);"
                  "tl.to('#c%d .w',{yPercent:0,duration:0.6,ease:'expo.out',stagger:0.04},%.2f);" % (k, s + 0.2, k, s + 0.2, k, s + 0.3))
    e = INTRO + n * step
    if n:
        js.append("tl.to('#c%d',{autoAlpha:0,duration:0.2,ease:'power2.in'},%.2f);" % (n - 1, e))
        if not hit:
            j = n - 1
            js.append("tl.to('#t%d .cur',{autoAlpha:0,duration:0.25},%.2f);tl.to('#t%d .used',{autoAlpha:1,duration:0.25},%.2f);"
                      "tl.to('#t%d .st',{scaleX:1,duration:0.4,ease:'power3.out'},%.2f);" % (j, e, j, e, j, e + 0.1))
        else:
            js.append("tl.fromTo('#t%d .cur',{boxShadow:'0 0 0px 0px rgba(0,194,168,0)'},{boxShadow:'0 0 48px 6px rgba(0,194,168,.75)',duration:0.5,ease:'power2.out'},%.2f);"
                      "tl.to('#t%d .cur',{boxShadow:'0 0 22px 2px rgba(0,194,168,.45)',duration:0.8,ease:'power2.inOut'},%.2f);" % (hit - 1, e + 0.2, hit - 1, e + 0.7))
    js.append("tl.fromTo('#bn',{autoAlpha:0,y:40},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},%.2f);" % (e + 0.2))
    js.append("tl.fromTo('#bn .b2',{autoAlpha:0},{autoAlpha:1,duration:0.4},%.2f);" % (e + 0.55))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Gr Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Gr Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#lab{left:%(left)dpx;top:%(lab_y)dpx;font:700 %(lab_fs)dpx/1 'Gr Label',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
.ly{position:absolute;inset:0;border-radius:16px;display:flex;align-items:center;justify-content:center}
.lb{position:absolute;left:12px;top:9px;font:700 %(lb_fs)dpx/1 'Gr Label',sans-serif}
.pt{position:relative;font:900 %(pt_fs)dpx/1 'Gr Head',sans-serif;margin-top:.18em}
.fut{border:3px solid rgba(0,194,168,.62);background:%(futbg)s}.fut .lb{color:#9a9a9a}.fut .pt{color:%(P)s}
.used{background:#1c1c1c}.used .lb{color:#6e6e6e}.used .pt{color:#555}
.st{position:absolute;left:-6%%;right:-6%%;top:52%%;height:5px;background:#6e6e6e;border-radius:3px;transform-origin:0 50%%}
.cur{background:%(P)s}.cur .lb,.cur .pt{color:#000}
.cl{display:flex;flex-direction:column;gap:14px;overflow:hidden}
.ck{font:700 %(cl_fs)dpx/1 'Gr Label',sans-serif;color:%(P)s;letter-spacing:.1em}
.ct{font:700 %(tx_fs)dpx/1.22 'Gr Label',sans-serif;color:#fff;%(shadow)s}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:0 .02em .1em}.w{display:inline-block}
.bn{border-radius:22px;background:%(P)s;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}
.bn .b1{font:900 %(bn_fs)dpx/1.1 'Gr Head',sans-serif;color:#000;white-space:nowrap}
.bn .b2{font:700 %(bs_fs)dpx/1.1 'Gr Label',sans-serif;color:#000;letter-spacing:.04em}
.bn.none{background:#000;border:3px solid %(P)s}.bn.none .b1{color:#fff}.bn.none .b2{color:%(P)s}
#demo{font:700 %(demo_fs)dpx/1 'Gr Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="grade" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="lab" class="abs">%(title)s</div>
%(tiles)s
%(panels)s
%(banner)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

document.querySelectorAll('.cl .ct').forEach(function(el){var p=el.parentNode,fs=%(tx_fs)d;while(p.scrollHeight>p.clientHeight&&fs>24){fs-=2;el.style.fontSize=fs+'px';}});
document.querySelectorAll('.bn .b1').forEach(function(el){var fs=%(bn_fs)d;while(el.scrollWidth>el.parentNode.clientWidth-48&&fs>28){fs-=2;el.style.fontSize=fs+'px';}});
var lab=document.getElementById('lab'),lf=%(lab_fs)d,lw=%(gw)d;while(lab.scrollWidth>lw&&lf>20){lf-=2;lab.style.fontSize=lf+'px';}
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['grade']=tl;});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, futbg="rgba(0,0,0,.55)" if transparent else "#000", shadow=shadow, P=P, left=L["left"],
                       lab_y=L["lab_y"], lab_fs=L["lab_fs"], lb_fs=L["lb_fs"], pt_fs=L["pt_fs"], cl_fs=L["cl_fs"], tx_fs=L["tx_fs"],
                       bn_fs=L["bn_fs"], bs_fs=L["bs_fs"], demo_fs=L["demo_fs"], gw=COLS * t + (COLS - 1) * g, TOTAL=TOTAL, FPS=FPS,
                       logo=logo, title=esc(title), tiles=tiles, panels=panels, banner=banner, demo_div=demo_div, js=js)


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--clues", default="")
    ap.add_argument("--hit", type=int, default=0)
    ap.add_argument("--title", default="QUEM É? · QUANTO ANTES, MAIS VALE")
    ap.add_argument("--step", type=float, default=1.6)
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=-1)
    ap.add_argument("--browser")
    a = ap.parse_args()
    if not 0 <= a.hit <= NCLUES:
        sys.exit("--hit vai de 0 a 20")
    clues = [c.strip() for c in a.clues.split("|")][:NCLUES] if a.clues else []
    if not clues:
        if not a.demo:
            sys.exit("--clues é obrigatório (ou use --demo)")
        clues = ["Dica %d de demonstração." % (k + 1) for k in range(a.hit or 6)]
    if a.hit and a.hit > len(clues):
        print("aviso: --hit %d mas só %d dicas com texto; as que faltam acendem sem texto" % (a.hit, len(clues)))
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    n = a.hit or len(clues)
    TOTAL = total(n, a.step)
    html = build_html(a.aspect, clues, a.hit, a.title, a.step, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Grade de Dicas %s %s" % (a.aspect, name)
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        nf = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            at = a.at if a.at >= 0 else TOTAL - HOLD + 1.2
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.6, INTRO + 0.9, INTRO + a.step + 1.0, INTRO + (n // 2) * a.step + 1.0, TOTAL - HOLD + 0.4, TOTAL - HOLD + 1.4]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "grade_f.png")
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
            for i in range(nf):
                ff.stdin.write(sess.frame(info["id"], i / info["fps"], fmt))
                if i % 30 == 0:
                    print("\r  frame %d/%d" % (i, nf), end="", flush=True)
            ff.stdin.close()
        except BrokenPipeError:
            pass
        if ff.wait() != 0 or not os.path.isfile(part):
            sys.exit("ffmpeg falhou")
        os.replace(part, out)
        print("\r  %d quadros, %.1fs, em %.0fs -> %s" % (nf, info["dur"], time.time() - t0, out))
    finally:
        sess.close()


if __name__ == "__main__":
    main()
