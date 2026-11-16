#!/usr/bin/env python
"""Peça 08 — Veredito do Júri (opção B: barra de cabo de guerra + cartão branco). Python padrão + Chrome + ffmpeg.

  python build_veredito.py render [--case "O CASO"] [--label "O RÉU"] [--score 62 | --verdict acusacao|defesa] [--placar "4 A 3"]
        [--args "A:frase da acusação|D:frase da defesa"] [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet]
        [--transparent] [--demo] [--scale 1] [--name NOME] [--at 6] [--browser CAMINHO]
  --score    porcentagem final da ACUSAÇÃO (0 a 100) vinda do chat; a defesa fica com o resto. 50 = EMPATE.
  --verdict  só o lado vencedor, sem números (a barra pende 70/30). Ignorado se --score for dado.
  --placar   texto do placar no cartão no lugar das porcentagens (ex.: "4 A 3"); a barra continua usando --score.
  --args     opcional: argumentos dos hosts (A: acusação, D: defesa), cada um entra num cartão e puxa a barra.
             Padrão: nenhum (decisão de pauta: o júri é o chat, não precisa julgamento na tela).
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Veredito do Júri <aspecto> <nome>.<ext>".
Movimento principal: a barra pende para o resultado e o cartão do veredito carimba. Secundários: o brilho de destaque
no marcador da barra, o placar que conta e o traço de destaque que se desenha sob o lado vencedor.
"""
import argparse, base64, html as H, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, TUG, ARGSTEP, LEAD, HOLD = 1.0, 2.0, 2.2, 0.9, 2.8

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=929, logo_y=265, logo_h=64, head_y=420, head_fs=46, lab_y=510, lab_fs=48,
                 bar_y=585, bar_h=104, card_y=770, card_h=500, pad=52, clab_fs=38, score_fs=136, verd_fs=66, arg_fs=64,
                 demo_y=1440, demo_fs=26),
    "16x9": dict(W=1920, H=1080, left=160, right=1760, logo_y=70, logo_h=48, head_y=160, head_fs=40, lab_y=235, lab_fs=42,
                 bar_y=300, bar_h=96, card_y=470, card_h=430, pad=56, clab_fs=36, score_fs=150, verd_fs=72, arg_fs=66,
                 demo_y=955, demo_fs=24),
}


def total(nargs):
    return INTRO + (ARGSTEP * nargs if nargs else TUG) + LEAD + HOLD


def build_html(aspect, case, label, score, verdict, placar, args, transparent, demo):
    L = LAYOUT[aspect]
    W, Hh = L["W"], L["H"]
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    TOTAL = total(len(args))
    left, cw = L["left"], L["right"] - L["left"]
    # alvo da barra (porcentagem da acusação)
    if score is not None:
        target = score
    else:
        target = 70 if verdict == "acusacao" else 30
    win = "acusacao" if target > 50 else ("defesa" if target < 50 else "empate")
    if score is not None and not placar:
        hi, lo = max(score, 100 - score), min(score, 100 - score)
        score_html = '<span id="sHi">%d</span>%% A <span id="sLo">%d</span>%%' % (hi, lo)
    elif placar:
        score_html = H.escape(placar)
        hi = lo = None
    else:
        score_html = ""
        hi = lo = None
    if win == "acusacao":
        verd_html = 'PARA A <span class="kw" style="color:%s">ACUSAÇÃO<i class="ul"></i></span>' % P
    elif win == "defesa":
        verd_html = 'PARA A <span class="kw">DEFESA<i class="ul"></i></span>'
    else:
        verd_html = '<span class="kw">EMPATE<i class="ul"></i></span>'
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, left, L["logo_y"], L["logo_h"]) if luri else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE O CASO E O PLACAR ANTES DE POSTAR.</div>' % (left, L["demo_y"], L["demo_fs"])
    cards = ""
    for k, (side, txt) in enumerate(args):
        cards += ('<div class="abs card arg" id="a%d"><div class="clab">ARGUMENTO %d · %s</div><div class="atx">%s</div></div>'
                  % (k, k + 1, "ACUSAÇÃO" if side == "A" else "DEFESA", H.escape(txt)))
    big = '<div class="score" id="score">%s</div>' % score_html if score_html else ""
    cards += ('<div class="abs card" id="vc"><div class="clab">VEREDITO · O CHAT DECIDIU</div>%s<div class="verd" id="verd">%s</div></div>'
              % (big, verd_html))

    js = ["tl.set('.card',{autoAlpha:0},0);tl.set('.ul',{scaleX:0},0);tl.set('#fill',{width:'50%'},0);tl.set('#notch',{left:'50%'},0);",
          "tl.fromTo('#head',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.15);",
          "tl.fromTo('.lab',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out',stagger:0.08},0.3);",
          "tl.fromTo('#bar',{autoAlpha:0,scaleX:0.2},{autoAlpha:1,scaleX:1,duration:0.7,ease:'expo.out'},0.35);"]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")

    def pull(v, t, d, ease="power3.out"):
        js.append("tl.to('#fill',{width:'%.2f%%',duration:%.2f,ease:'%s'},%.2f);tl.to('#notch',{left:'%.2f%%',duration:%.2f,ease:'%s'},%.2f);"
                  % (v, d, ease, t, v, d, ease, t))
        js.append("tl.fromTo('#glow',{opacity:0.9},{opacity:0,duration:%.2f,ease:'power2.out',immediateRender:false},%.2f);" % (d + 0.2, t))

    v = 50.0
    if args:
        for k, (side, _) in enumerate(args):
            t = INTRO + k * ARGSTEP
            js.append("tl.fromTo('#a%d',{autoAlpha:0,y:40},{autoAlpha:1,y:0,duration:0.55,ease:'expo.out'},%.2f);" % (k, t))
            v = max(15.0, min(85.0, v + (7 if side == "A" else -7)))
            pull(v, t + 0.45, 0.8)
            js.append("tl.to('#a%d',{autoAlpha:0,y:-20,duration:0.3,ease:'power2.in'},%.2f);" % (k, t + ARGSTEP - 0.35))
        tp = INTRO + ARGSTEP * len(args)
    else:
        # cabo de guerra: puxões curtos, cada um para firme (sem elástico)
        for vv, t in ((54, INTRO), (47, INTRO + 0.65), (52, INTRO + 1.3)):
            pull(vv, t, 0.6, "power3.inOut")
        tp = INTRO + TUG
    pull(target, tp - 0.05, 1.0, "expo.out")
    tv = tp + LEAD
    js.append("tl.fromTo('#vc',{autoAlpha:0,scale:1.14},{autoAlpha:1,scale:1,duration:0.45,ease:'expo.out',immediateRender:false},%.2f);" % tv)
    js.append("tl.fromTo('#flash',{opacity:0.8,scale:1},{opacity:0,scale:1.06,duration:0.6,ease:'power2.out',immediateRender:false},%.2f);" % tv)
    if hi is not None:
        js.append("var c={h:50,l:50};tl.to(c,{h:%d,l:%d,duration:0.8,ease:'power2.out',onUpdate:function(){"
                  "document.getElementById('sHi').textContent=Math.round(c.h);document.getElementById('sLo').textContent=Math.round(c.l);}},%.2f);"
                  % (hi, lo, tv + 0.1))
        js.append("tl.set(c,{h:50,l:50},0);")
    js.append("tl.to('.ul',{scaleX:1,duration:0.55,ease:'power3.out'},%.2f);" % (tv + 0.55))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)

    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Ver Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Ver Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#head{left:%(left)dpx;top:%(head_y)dpx;width:%(cw)dpx;font:700 %(head_fs)dpx/1.1 'Ver Label',sans-serif;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;%(shadow)s}
#head span{color:rgba(255,255,255,.6)}
.lab{top:%(lab_y)dpx;font:700 %(lab_fs)dpx/1 'Ver Label',sans-serif;white-space:nowrap;%(shadow)s}
#labA{left:%(left)dpx;color:%(P)s}#labD{right:%(rgap)dpx;color:#fff}
#bar{left:%(left)dpx;top:%(bar_y)dpx;width:%(cw)dpx;height:%(bar_h)dpx;border-radius:%(rad)dpx;background:#fff;overflow:hidden;transform-origin:50%% 50%%}
#fill{position:absolute;left:0;top:0;bottom:0;width:50%%;background:%(P)s}
#notch{position:absolute;top:0;bottom:0;left:50%%;width:12px;margin-left:-6px;background:#000}
#glow{position:absolute;left:-10px;right:-10px;top:-6px;bottom:-6px;opacity:0;box-shadow:0 0 26px 6px %(P)s;border-radius:4px}
.card{left:%(left)dpx;top:%(card_y)dpx;width:%(cw)dpx;height:%(card_h)dpx;background:#fff;border-radius:22px;padding:%(pad)dpx;color:#000;
  display:flex;flex-direction:column;justify-content:center;gap:18px;transform-origin:50%% 50%%}
.clab{font:700 %(clab_fs)dpx/1 'Ver Label',sans-serif;letter-spacing:.02em;white-space:nowrap}
.atx{font:900 %(arg_fs)dpx/1.12 'Ver Head',sans-serif}
.score{font:900 %(score_fs)dpx/1 'Ver Head',sans-serif;white-space:nowrap;letter-spacing:-.01em}
.verd{font:900 %(verd_fs)dpx/1.1 'Ver Head',sans-serif;white-space:nowrap}
.kw{position:relative;display:inline-block}
.ul{position:absolute;left:0;right:0;bottom:-10px;height:8px;border-radius:4px;background:%(P)s;transform-origin:0 50%%}
#flash{left:%(left)dpx;top:%(card_y)dpx;width:%(cw)dpx;height:%(card_h)dpx;border:6px solid %(P)s;border-radius:22px;opacity:0;pointer-events:none}
#demo{font:700 %(demo_fs)dpx/1 'Ver Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="ver" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="head" class="abs">%(label)s · <span>%(case)s</span></div>
<div id="labA" class="abs lab">ACUSAÇÃO</div><div id="labD" class="abs lab">DEFESA</div>
<div id="bar" class="abs"><div id="fill"></div><div id="notch"><div id="glow"></div></div></div>
%(cards)s
<div id="flash" class="abs"></div>
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

function fit(sel,min){document.querySelectorAll(sel).forEach(function(el){var cs=getComputedStyle(el),fs=parseFloat(cs.fontSize),box=el.closest('.card');
 var max=box?box.clientWidth-2*%(pad)d:el.clientWidth;while(el.scrollWidth>max&&fs>min){fs-=2;el.style.fontSize=fs+'px';}});}
fit('.score',60);fit('.verd',36);fit('.clab',22);
document.querySelectorAll('.atx').forEach(function(el){var fs=%(arg_fs)d,box=el.closest('.card');while(box.scrollHeight>box.clientHeight&&fs>30){fs-=2;el.style.fontSize=fs+'px';}});
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['ver']=tl;});</script>
</body></html>""" % dict(W=W, H=Hh, bg=bg, shadow=shadow, P=P, left=left, cw=cw, rgap=W - L["right"], head_y=L["head_y"], head_fs=L["head_fs"],
                       lab_y=L["lab_y"], lab_fs=L["lab_fs"], bar_y=L["bar_y"], bar_h=L["bar_h"], rad=L["bar_h"] // 2, card_y=L["card_y"],
                       card_h=L["card_h"], pad=L["pad"], clab_fs=L["clab_fs"], score_fs=L["score_fs"], verd_fs=L["verd_fs"], arg_fs=L["arg_fs"],
                       demo_fs=L["demo_fs"], TOTAL=TOTAL, FPS=FPS, logo=logo, label=H.escape(label), case=H.escape(case), cards=cards,
                       demo_div=demo_div, js=js)


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--case", default="")
    ap.add_argument("--label", default="O RÉU")
    ap.add_argument("--score", type=int)
    ap.add_argument("--verdict", choices=["acusacao", "defesa"])
    ap.add_argument("--placar", default="")
    ap.add_argument("--args", default="")
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=-1)
    ap.add_argument("--browser")
    a = ap.parse_args()
    if a.demo:
        a.case = a.case or "TEMA DE DEMONSTRAÇÃO"
        if a.score is None and not a.verdict:
            a.score = 62
    if not a.case:
        sys.exit("--case é obrigatório (ou use --demo)")
    if a.score is None and not a.verdict:
        sys.exit("dê --score (porcentagem da acusação) ou --verdict acusacao|defesa")
    if a.score is not None and not 0 <= a.score <= 100:
        sys.exit("--score vai de 0 a 100")
    args = []
    for part in [p.strip() for p in a.args.split("|") if p.strip()]:
        side, _, txt = part.partition(":")
        side = side.strip().upper()
        if side not in ("A", "D") or not txt.strip():
            sys.exit('--args: use "A:frase|D:frase"')
        args.append((side, txt.strip()))
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    TOTAL = total(len(args))
    html = build_html(a.aspect, a.case, a.label, a.score, a.verdict, a.placar, args, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Veredito do Júri %s %s" % (a.aspect, name)
    tv = TOTAL - HOLD
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        n = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            at = a.at if a.at >= 0 else tv + 1.6
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.5, INTRO + 0.5, tv - LEAD + 0.3, tv - 0.1, tv + 0.4, tv + 1.6]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "ver_f.png")
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
