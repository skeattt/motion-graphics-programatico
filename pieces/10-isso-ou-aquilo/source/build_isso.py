#!/usr/bin/env python
"""Peça 10 — Isso ou Aquilo (opção B: dois cartões com foto e o OU no meio). Python padrão + Chrome + ffmpeg.

  python build_isso.py render --a "NOME A" --b "NOME B" --pick a|b [--question "A PERGUNTA"] [--answer "a resposta em uma linha"]
        [--photo-a FOTO.png] [--photo-b FOTO.png] [--title "RESPONDE"] [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet]
        [--transparent] [--demo] [--scale 1] [--name NOME] [--at 5] [--browser CAMINHO]
  --pick      qual das duas a pessoa escolheu (a = esquerda, b = direita).
  --photo-a/b opcional: foto quadrada (>= 400 px) de cada opção; sem foto, o círculo fica com "FOTO".
  --answer    opcional: a resposta curta, sobe embaixo dos cartões depois da escolha.
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Isso ou Aquilo <aspecto> <nome>.<ext>".
Movimento principal: o contorno de destaque hesita entre as duas opções e a escolhida acende na cor de destaque enquanto a outra esmaece.
Secundários: o OU que pulsa a cada troca e a resposta subindo.
"""
import argparse, base64, html as H, importlib.util, mimetypes, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, HESIT, LEAD, HOLD = 1.0, 1.9, 0.6, 2.6

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=928, gap=40, logo_y=265, logo_h=64, title_y=420, title_fs=54, q_y=500, q_fs=38,
                 card_y=590, card_h=620, photo=240, photo_y=90, name_fs=62, ou=120, ans_fs=44, demo_y=1500, demo_fs=22),
    "16x9": dict(W=1920, H=1080, left=160, right=1760, gap=120, logo_y=60, logo_h=48, title_y=130, title_fs=50, q_y=200, q_fs=36,
                 card_y=270, card_h=520, photo=220, photo_y=60, name_fs=68, ou=130, ans_fs=42, demo_y=960, demo_fs=24),
}


def total():
    return INTRO + HESIT + LEAD + HOLD


def data_uri(path):
    mt = mimetypes.guess_type(path)[0] or "image/png"
    return "data:%s;base64,%s" % (mt, base64.b64encode(open(path, "rb").read()).decode())


def build_html(aspect, title, question, na, nb, pick, answer, pa, pb, transparent, demo):
    L = LAYOUT[aspect]
    W, Hh = L["W"], L["H"]
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    TOTAL = total()
    left, cw, gap = L["left"], L["right"] - L["left"], L["gap"]
    card_w = (cw - gap) // 2
    xa, xb = left, left + card_w + gap
    ou_x = left + card_w + gap // 2 - L["ou"] // 2
    ou_y = L["card_y"] + L["photo_y"] + L["photo"] // 2 + 50 - L["ou"] // 2

    def card(cid, x, nm, ph):
        inner = '<img alt="" src="%s">' % data_uri(ph) if ph else "FOTO"
        return ('<div class="abs card" id="%s" style="left:%dpx"><div class="fill"></div><div class="hl"></div>'
                '<div class="ph">%s</div><div class="nm"><span>%s</span></div></div>' % (cid, x, inner, H.escape(nm)))

    cards = card("ca", xa, na, pa) + "\n" + card("cb", xb, nb, pb)
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, left, L["logo_y"], L["logo_h"]) if luri else ""
    q_div = '<div class="abs" id="q">%s</div>' % H.escape(question) if question else ""
    ans_div = '<div class="abs" id="ans">%s</div>' % H.escape(answer) if answer else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo">DEMO. TROQUE OS NOMES E A RESPOSTA ANTES DE POSTAR.</div>'
    win, lose = ("#ca", "#cb") if pick == "a" else ("#cb", "#ca")

    js = ["tl.set('.fill',{scaleY:0},0);tl.set('.hl',{opacity:0},0);",
          "tl.fromTo('#title',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.15);",
          "tl.fromTo('#q',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.25);",
          "tl.fromTo('.card',{autoAlpha:0,y:50},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out',stagger:0.1},0.3);",
          "tl.fromTo('#ou',{autoAlpha:0,scale:0.3},{autoAlpha:1,scale:1,duration:0.5,ease:'back.out(2)'},0.6);"]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    # hesitação: o contorno troca de lado, cada troca um pouco mais rápida
    seq = ["#ca", "#cb", "#ca", "#cb", "#ca", "#cb"]
    if pick == "a":
        seq = seq[1:] + ["#ca"]
    t = INTRO
    steps = [0.42, 0.36, 0.3, 0.26, 0.24, 0.22, 0.2]
    for k, c in enumerate(seq):
        other = "#cb" if c == "#ca" else "#ca"
        js.append("tl.to('%s .hl',{opacity:1,duration:0.12},%.2f);tl.to('%s .hl',{opacity:0,duration:0.12},%.2f);"
                  "tl.fromTo('#ou',{scale:1.12},{scale:1,duration:0.25,ease:'power2.out',immediateRender:false},%.2f);"
                  % (c, t, other, t, t))
        t += steps[k]
    tc = INTRO + HESIT
    js.append("tl.to('%s .fill',{scaleY:1,duration:0.45,ease:'expo.out'},%.2f);tl.to('%s .nm',{color:'#000',duration:0.3},%.2f);"
              "tl.to('%s .ph',{backgroundColor:'rgba(0,0,0,.82)',color:'rgba(255,255,255,.55)',duration:0.3},%.2f);"
              "tl.fromTo('%s',{scale:1},{scale:1.035,duration:0.16,yoyo:true,repeat:1,ease:'power2.out',immediateRender:false},%.2f);"
              "tl.to('%s .hl',{opacity:0,duration:0.2},%.2f);"
              "tl.to('%s',{opacity:0.42,duration:0.45,ease:'power2.out'},%.2f);tl.to('%s .nm',{color:'#6a6a6a',duration:0.45},%.2f);"
              "tl.to('%s',{borderColor:'rgba(0,194,168,.28)',duration:0.45},%.2f);"
              % (win, tc, win, tc, win, tc, win, tc, win, tc, lose, tc, lose, tc, lose, tc))
    if answer:
        js.append("tl.fromTo('#ans',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.55,ease:'expo.out'},%.2f);" % (tc + LEAD))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)

    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Iou Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Iou Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#title{left:%(left)dpx;top:%(title_y)dpx;width:%(cw)dpx;font:900 %(title_fs)dpx/1.1 'Iou Head',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
#q{left:%(left)dpx;top:%(q_y)dpx;width:%(cw)dpx;font:700 %(q_fs)dpx/1.15 'Iou Label',sans-serif;color:%(P)s;white-space:nowrap;%(shadow)s}
.card{top:%(card_y)dpx;width:%(card_w)dpx;height:%(card_h)dpx;border-radius:24px;border:4px solid rgba(0,194,168,.55);background:#000;overflow:hidden;transform-origin:50%% 50%%}
.fill{position:absolute;inset:0;background:%(P)s;transform-origin:50%% 100%%}
.hl{position:absolute;inset:0;border:8px solid %(P)s;border-radius:20px;box-shadow:inset 0 0 30px rgba(0,194,168,.55)}
.ph{position:absolute;left:50%%;top:%(photo_y)dpx;width:%(photo)dpx;height:%(photo)dpx;margin-left:-%(photo_h)dpx;border-radius:50%%;overflow:hidden;
  background:#1a1a1a;color:rgba(255,255,255,.4);font:700 32px/%(photo)dpx 'Iou Label',sans-serif;text-align:center}
.ph img{width:100%%;height:100%%;object-fit:cover;display:block}
.nm{position:absolute;left:24px;right:24px;top:%(name_top)dpx;bottom:30px;display:flex;align-items:center;justify-content:center;text-align:center;
  font:900 %(name_fs)dpx/1.02 'Iou Head',sans-serif;color:#fff;letter-spacing:-.01em}
#ou{left:%(ou_x)dpx;top:%(ou_y)dpx;width:%(ou)dpx;height:%(ou)dpx;border-radius:50%%;background:#000;border:5px solid #fff;color:#fff;
  font:900 %(ou_fs)dpx/%(ou_lh)dpx 'Iou Head',sans-serif;text-align:center;z-index:3}
#ans{left:%(left)dpx;top:%(ans_y)dpx;width:%(cw)dpx;font:700 %(ans_fs)dpx/1.22 'Iou Label',sans-serif;color:#fff;%(shadow)s}
#demo{left:%(left)dpx;top:%(demo_y)dpx;font:700 %(demo_fs)dpx/1 'Iou Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="iou" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="title" class="abs">%(title)s</div>
%(q_div)s
%(cards)s
<div id="ou" class="abs">OU</div>
%(ans_div)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

document.querySelectorAll('.nm').forEach(function(el){var fs=%(name_fs)d;while((el.scrollHeight>el.clientHeight||el.scrollWidth>el.clientWidth)&&fs>28){fs-=2;el.style.fontSize=fs+'px';}});
['title','q'].forEach(function(id){var t=document.getElementById(id);if(!t)return;var fs=parseFloat(getComputedStyle(t).fontSize);while(t.scrollWidth>t.clientWidth&&fs>24){fs-=2;t.style.fontSize=fs+'px';}});
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['iou']=tl;});</script>
</body></html>""" % dict(W=W, H=Hh, bg=bg, shadow=shadow, P=P, left=left, cw=cw, card_w=card_w, card_y=L["card_y"], card_h=L["card_h"],
                       title_y=L["title_y"], title_fs=L["title_fs"], q_y=L["q_y"], q_fs=L["q_fs"], photo=L["photo"], photo_h=L["photo"] // 2,
                       photo_y=L["photo_y"], name_top=L["photo_y"] + L["photo"] + 20, name_fs=L["name_fs"], ou=L["ou"], ou_x=ou_x, ou_y=ou_y,
                       ou_fs=L["ou"] * 36 // 100, ou_lh=L["ou"] - 10, ans_y=L["card_y"] + L["card_h"] + 44, ans_fs=L["ans_fs"],
                       demo_y=L["demo_y"], demo_fs=L["demo_fs"], TOTAL=TOTAL, FPS=FPS, logo=logo, title=H.escape(title), q_div=q_div,
                       cards=cards, ans_div=ans_div, demo_div=demo_div, js=js)


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--a", default="")
    ap.add_argument("--b", default="")
    ap.add_argument("--pick", choices=["a", "b"])
    ap.add_argument("--question", default="")
    ap.add_argument("--answer", default="")
    ap.add_argument("--photo-a", dest="photo_a", default="")
    ap.add_argument("--photo-b", dest="photo_b", default="")
    ap.add_argument("--title", default="RESPONDE")
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
        a.a = a.a or "JOGADOR A"
        a.b = a.b or "JOGADOR B"
        a.pick = a.pick or "a"
        a.question = a.question or "PERGUNTA DE DEMONSTRAÇÃO"
        a.answer = a.answer or "Resposta de demonstração em uma linha."
    if not a.a or not a.b:
        sys.exit("--a e --b são obrigatórios (ou use --demo)")
    if not a.pick:
        sys.exit("--pick a|b é obrigatório")
    for ph in (a.photo_a, a.photo_b):
        if ph and not os.path.isfile(ph):
            sys.exit("foto não encontrada: " + ph)
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    TOTAL = total()
    html = build_html(a.aspect, a.title, a.question, a.a, a.b, a.pick, a.answer, a.photo_a, a.photo_b, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Isso ou Aquilo %s %s" % (a.aspect, name)
    tc = INTRO + HESIT
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        n = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            at = a.at if a.at >= 0 else TOTAL - 0.8
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.5, INTRO + 0.05, INTRO + 0.45, tc - 0.1, tc + 0.3, TOTAL - 0.8]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "iou_f.png")
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
