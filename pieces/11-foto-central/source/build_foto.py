#!/usr/bin/env python
"""Peça 11 — Foto Central (para o quadro de ranking às cegas com dois apresentadores).
A foto do jogador revelado entra grande numa moldura quadrada de destaque no vão entre as duas listas, com o nome embaixo.
As listas continuam sendo da edição de vídeo; esta peça é só a moldura (WebM transparente para pôr por cima).

  python build_foto.py render --player "RAFAEL MOURA" --photo FOTO.png [--hold 3.0] [--aspect 9x16|16x9]
        [--kind mp4|webm|still|sheet] [--transparent] [--demo] [--scale 1] [--name NOME] [--at 1.5] [--browser CAMINHO]
  --player  nome do jogador (caixa alta recomendada)
  --photo   foto quadrada do jogador (PNG/JPG); prefira >= 600 px (foto pequena fica mole)
  --hold    segundos que a moldura fica parada na tela depois de entrar (padrão 3,0)
  --kind    webm (transparente, sem logo, para a edição) | mp4 (fundo preto, com logo) | still (PNG em --at s) | sheet (folha com zona segura)
Saídas em ../9x16 ou ../16x9: "Foto Central <aspecto> <nome>.<ext>". Duração: 0,9 s de entrada + --hold + 0,45 s de saída.
Posição no 9:16 (1080x1920): moldura de 296 px em x 348, y 1010, entre as duas listas da edição (x 30 e x 668), topo das listas em y 960.
Movimento principal: a moldura de destaque abre do centro e a foto sobe por dentro. Secundários: o nome sobe por baixo; a foto aproxima devagar enquanto fica parada.
"""
import argparse, base64, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
IN, OUT = 0.9, 0.45

LAYOUT = {
    # tag_max: largura máxima da tarja do nome (no 9:16 é o vão entre as listas, x 327 a 668, menos um respiro)
    "9x16": dict(W=1080, H=1920, x=348, y=1010, s=296, b=10, fs=30, tag_max=300, left=72, logo_y=265, logo_h=64, demo_y=1480, demo_fs=26),
    "16x9": dict(W=1920, H=1080, x=760, y=250, s=400, b=12, fs=40, tag_max=600, left=160, logo_y=96, logo_h=56, demo_y=985, demo_fs=24),
}


def fit_fs(text, fs, max_w):
    """corpo do nome que cabe na tarja (texto + respiro lateral de 0,7 corpo de cada lado)"""
    from PIL import ImageFont
    f = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "fonts", "Inter-Black.ttf")
    while fs > 14 and ImageFont.truetype(f, fs).getlength(text) + 1.4 * fs > max_w:
        fs -= 1
    return fs


def build_html(aspect, player, photo, hold, transparent, demo):
    L = dict(LAYOUT[aspect])
    L["fs"] = fit_fs(player, L["fs"], L["tag_max"])
    W, H, x, y, s, b = L["W"], L["H"], L["x"], L["y"], L["s"], L["b"]
    total = IN + hold + OUT
    bg = "transparent" if transparent else "#000000"
    ext = os.path.splitext(photo)[1].lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    puri = "data:image/%s;base64,%s" % (mime, base64.b64encode(open(photo, "rb").read()).decode())
    logo = ""
    if not transparent:
        luri = "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
        logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, L["left"], L["logo_y"], L["logo_h"])
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE O JOGADOR E A FOTO ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    words = "".join('<span class="m"><span class="w">%s</span></span> ' % w for w in player.split())
    cx = x + s / 2
    js = ["tl.set('#tag',{autoAlpha:0},0);",
          # a moldura abre do centro (de destaque puro), depois a foto sobe por dentro
          "tl.fromTo('#frame',{scale:0.35,autoAlpha:0},{scale:1,autoAlpha:1,duration:0.55,ease:'expo.out'},0);",
          "tl.fromTo('#shadow',{autoAlpha:0},{autoAlpha:1,duration:0.5},0.1);",
          "tl.fromTo('#clip',{clipPath:'inset(100% 0 0 0)'},{clipPath:'inset(0% 0 0 0)',duration:0.6,ease:'expo.out'},0.18);",
          "tl.fromTo('#photo',{scale:1.18},{scale:1.0,duration:0.9,ease:'expo.out'},0.18);",
          "tl.to('#photo',{scale:1.05,duration:%.2f,ease:'none'},1.08);" % max(hold - 0.2, 0.1),
          "tl.set('#tag',{autoAlpha:1},0.45);tl.fromTo('#tag',{clipPath:'inset(0 0 100% 0)'},{clipPath:'inset(0 0 0% 0)',duration:0.45,ease:'expo.out'},0.45);",
          "tl.fromTo('#tag .w',{yPercent:115},{yPercent:0,duration:0.6,ease:'expo.out',stagger:0.06},0.5);",
          "tl.to('#all',{scale:0.9,autoAlpha:0,duration:%.2f,ease:'power2.in'},%.2f);" % (OUT, IN + hold)]
    if logo:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    js.append("tl.set({},{},%.2f);" % total)
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'FC Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'FC Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#all{position:absolute;inset:0;transform-origin:%(cx).0fpx %(cy).0fpx}
#shadow{position:absolute;left:%(sx)dpx;top:%(sy)dpx;width:%(fs_)dpx;height:%(fs_)dpx;background:rgba(0,0,0,.55);filter:blur(16px)}
#frame{position:absolute;left:%(fx)dpx;top:%(fy)dpx;width:%(fs_)dpx;height:%(fs_)dpx;background:%(P)s;transform-origin:50%% 50%%}
#clip{position:absolute;left:%(x)dpx;top:%(y)dpx;width:%(s)dpx;height:%(s)dpx;overflow:hidden;background:#fff}
#photo{width:100%%;height:100%%;object-fit:cover;display:block;transform-origin:50%% 40%%}
#tag{position:absolute;left:%(cx).0fpx;top:%(ty)dpx;transform:translateX(-50%%);background:#000;padding:%(pv)dpx %(ph)dpx;white-space:nowrap;
     font:900 %(nfs)dpx/1 'FC Head',sans-serif;color:#fff}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:.22em .02em .1em;margin-top:-.22em}.w{display:inline-block}
#demo{font:700 %(demo_fs)dpx/1 'FC Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="foto" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(total).2f" data-fps="%(FPS)d">
%(logo)s
<div id="all">
<div id="shadow"></div>
<div id="frame"></div>
<div id="clip"><img id="photo" alt="" src="%(puri)s"></div>
<div id="tag">%(words)s</div>
</div>
%(demo_div)s
</div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['foto']=tl;});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, P=P, x=x, y=y, s=s, fx=x - b, fy=y - b, fs_=s + 2 * b, sx=x - b + 14, sy=y - b + 18,
                       cx=cx, cy=y + s / 2, ty=y + s + b, nfs=L["fs"], pv=int(L["fs"] * .5), ph=int(L["fs"] * .7),
                       demo_fs=L["demo_fs"], total=total, FPS=FPS, logo=logo, puri=puri, words=words, demo_div=demo_div, js="\n".join(js)), total


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
    ap.add_argument("--hold", type=float, default=3.0)
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="webm", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=1.5)
    ap.add_argument("--browser")
    a = ap.parse_args()
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    html, total = build_html(a.aspect, a.player, a.photo, a.hold, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Foto Central %s %s" % (a.aspect, name)
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
            ts = [0.12, 0.3, 0.5, 0.75, 1.5, total - 0.2]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "foto_f.png")
                open(p, "wb").write(sess.frame(info["id"], t, "png"))
                im = Image.open(p).convert("RGBA")
                if a.transparent:
                    im = Image.alpha_composite(Image.new("RGBA", im.size, (60, 60, 60, 255)), im)
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
