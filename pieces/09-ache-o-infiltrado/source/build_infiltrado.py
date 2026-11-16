#!/usr/bin/env python
"""Peça 09 — Ache o Infiltrado (opção B: grade 2x3 com o cartão do critério). Python padrão + Chrome + ffmpeg.

  python build_infiltrado.py render --names "N1|N2|N3|N4|N5" --odd 3 --criterion "O CRITÉRIO" [--reason "o motivo em uma linha"]
        [--title "ACHE O INFILTRADO"] [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet]
        [--transparent] [--demo] [--scale 1] [--name NOME] [--at 7] [--browser CAMINHO]
  --names     os 5 nomes, na ordem da grade (de cima para baixo, da esquerda para a direita, depois do critério).
  --odd       qual dos 5 é o infiltrado (1 a 5).
  --criterion o critério que os outros 4 cumprem (vai no cartão de contorno de destaque).
  --reason    opcional: o que falta ao infiltrado, em uma linha, sobe embaixo da grade no fim.
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Ache o Infiltrado <aspecto> <nome>.<ext>".
Movimento principal: cada cartão que pertence acende na cor de destaque com o visto; o infiltrado vira branco, o nome é riscado
e o carimbo INFILTRADO bate. Secundários: o risco que se desenha, o brilho de destaque do carimbo e o motivo subindo.
"""
import argparse, base64, html as H, importlib.util, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, STEP, BEAT, HOLD = 1.3, 0.85, 0.35, 2.8

# grade: 6 cartões (o 0 é o critério); cols x rows
LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=928, cols=2, cell_h=270, gap=20, logo_y=265, logo_h=64, title_y=420,
                 title_fs=58, grid_y=520, name_fs=56, crit_fs=40, clab_fs=28, chk=46, stamp_fs=48, reason_fs=36,
                 demo_y=1528, demo_fs=22),
    "16x9": dict(W=1920, H=1080, left=160, right=1760, cols=3, cell_h=250, gap=20, logo_y=60, logo_h=48, title_y=130,
                 title_fs=54, grid_y=210, name_fs=60, crit_fs=38, clab_fs=26, chk=46, stamp_fs=50, reason_fs=36,
                 demo_y=960, demo_fs=24),
}

CHECK = ('<svg viewBox="0 0 24 24" width="%d" height="%d"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="#000" '
         'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def total(n):
    return INTRO + STEP * (n - 1) + BEAT + 0.6 + HOLD


def build_html(aspect, title, criterion, names, odd, reason, transparent, demo):
    L = LAYOUT[aspect]
    W, Hh = L["W"], L["H"]
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    TOTAL = total(len(names))
    left, cw = L["left"], L["right"] - L["left"]
    cols, gap = L["cols"], L["gap"]
    cell_w = (cw - gap * (cols - 1)) // cols
    rows = (len(names) + 1 + cols - 1) // cols
    grid_bottom = L["grid_y"] + rows * L["cell_h"] + (rows - 1) * gap

    def pos(i):
        r, c = divmod(i, cols)
        return left + c * (cell_w + gap), L["grid_y"] + r * (L["cell_h"] + gap)

    cells = []
    x, y = pos(0)
    cells.append('<div class="abs cell crit" id="c0" style="left:%dpx;top:%dpx"><div class="clab">CRITÉRIO</div><div class="ctx">%s</div></div>'
                 % (x, y, H.escape(criterion)))
    for k, nm in enumerate(names, 1):
        x, y = pos(k)
        extra = ('<div class="stamp" id="stamp">INFILTRADO</div>' if k == odd else
                 '<div class="chk" id="k%d">%s</div>' % (k, CHECK % (L["chk"], L["chk"])))
        cells.append('<div class="abs cell nm" id="c%d" style="left:%dpx;top:%dpx"><div class="bgw"></div><div class="nmw">'
                     '<span class="nmt">%s<i class="st"></i></span></div>%s</div>' % (k, x, y, H.escape(nm), extra))
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, left, L["logo_y"], L["logo_h"]) if luri else ""
    reason_div = '<div class="abs" id="reason">%s</div>' % H.escape(reason) if reason else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo">DEMO. TROQUE OS NOMES ANTES DE POSTAR.</div>'

    js = ["tl.set('.bgw',{opacity:0},0);tl.set('.st',{scaleX:0},0);tl.set('.chk',{autoAlpha:0,scale:0.4},0);tl.set('#stamp',{autoAlpha:0},0);",
          "tl.fromTo('#title',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.15);",
          "tl.fromTo('#c0',{autoAlpha:0,y:30},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.3);",
          "tl.fromTo('.nm',{autoAlpha:0,y:30},{autoAlpha:1,y:0,duration:0.55,ease:'expo.out',stagger:0.08},0.45);"]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    t = INTRO
    for k in range(1, len(names) + 1):
        if k == odd:
            continue
        js.append("tl.to('#c%d',{borderColor:'%s',duration:0.25},%.2f);tl.to('#c%d .bgw',{opacity:1,duration:0.3,ease:'power2.out'},%.2f);"
                  "tl.to('#c%d .nmt',{color:'#000',duration:0.3},%.2f);"
                  "tl.fromTo('#c%d',{scale:1},{scale:1.04,duration:0.14,yoyo:true,repeat:1,ease:'power2.out',immediateRender:false},%.2f);"
                  "tl.to('#k%d',{autoAlpha:1,scale:1,duration:0.4,ease:'back.out(2.2)'},%.2f);"
                  % (k, P, t, k, t, k, t, k, t, k, t + 0.12))
        t += STEP
    ti = t - STEP + 0.6 + BEAT
    js.append("tl.to('#c%d',{backgroundColor:'#fff',borderColor:'#fff',duration:0.3,ease:'power2.out'},%.2f);"
              "tl.to('#c%d .nmt',{color:'#8a8a8a',duration:0.3},%.2f);"
              "tl.to('#c%d .st',{scaleX:1,duration:0.4,ease:'power3.out'},%.2f);"
              "tl.fromTo('#stamp',{autoAlpha:0,scale:1.7,rotation:-14},{autoAlpha:1,scale:1,rotation:-6,duration:0.38,ease:'expo.out',immediateRender:false},%.2f);"
              "tl.fromTo('#glow',{opacity:0.9},{opacity:0,duration:0.7,ease:'power2.out',immediateRender:false},%.2f);"
              % (odd, ti, odd, ti, odd, ti + 0.25, ti + 0.55, ti + 0.75))
    gx, gy = pos(odd)
    if reason:
        js.append("tl.fromTo('#reason',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.55,ease:'expo.out'},%.2f);" % (ti + 1.0))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)

    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Inf Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Inf Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#title{left:%(left)dpx;top:%(title_y)dpx;width:%(cw)dpx;font:900 %(title_fs)dpx/1.1 'Inf Head',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
.cell{width:%(cell_w)dpx;height:%(cell_h)dpx;border-radius:24px;border:4px solid rgba(255,255,255,.28);background:#000;overflow:hidden;transform-origin:50%% 50%%}
.crit{border-color:%(P)s;padding:30px 30px;display:flex;flex-direction:column;gap:14px}
.clab{font:700 %(clab_fs)dpx/1 'Inf Label',sans-serif;color:%(P)s;letter-spacing:.04em}
.ctx{font:900 %(crit_fs)dpx/1.15 'Inf Head',sans-serif;color:#fff}
.bgw{position:absolute;inset:0;background:%(P)s}
.nmw{position:absolute;left:18px;right:18px;top:0;bottom:0;display:flex;align-items:center;justify-content:center}
.nmt{position:relative;display:inline-block;font:900 %(name_fs)dpx/1 'Inf Head',sans-serif;color:#fff;white-space:nowrap;letter-spacing:-.01em}
.st{position:absolute;left:-6px;right:-6px;top:52%%;height:7px;border-radius:4px;background:#8a8a8a;transform-origin:0 50%%}
.chk{position:absolute;left:0;right:0;bottom:24px;display:flex;justify-content:center}
.stamp{position:absolute;left:50%%;top:62%%;margin-left:-%(stamp_hw)dpx;width:%(stamp_w)dpx;text-align:center;padding:8px 0 10px;border:6px solid %(P)s;
  border-radius:16px;font:900 %(stamp_fs)dpx/1 'Inf Head',sans-serif;color:%(P)s;letter-spacing:.01em;background:#fff;white-space:nowrap}
#glow{left:%(gx)dpx;top:%(gy)dpx;width:%(cell_w)dpx;height:%(cell_h)dpx;border-radius:24px;box-shadow:0 0 40px 10px %(P)s;opacity:0;pointer-events:none}
#reason{left:%(left)dpx;top:%(reason_y)dpx;width:%(cw)dpx;font:700 %(reason_fs)dpx/1.25 'Inf Label',sans-serif;color:#fff;%(shadow)s}
#demo{left:%(left)dpx;top:%(demo_y)dpx;font:700 %(demo_fs)dpx/1 'Inf Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="inf" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="title" class="abs">%(title)s</div>
<div id="glow" class="abs"></div>
%(cells)s
%(reason_div)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

document.querySelectorAll('.nmt').forEach(function(el){var max=el.closest('.cell').clientWidth-44,fs=parseFloat(getComputedStyle(el).fontSize);
 while(el.scrollWidth>max&&fs>26){fs-=2;el.style.fontSize=fs+'px';}});
document.querySelectorAll('.ctx').forEach(function(el){var box=el.closest('.cell'),fs=%(crit_fs)d;while(box.scrollHeight>box.clientHeight&&fs>22){fs-=2;el.style.fontSize=fs+'px';}});
var t=document.getElementById('title'),fs=%(title_fs)d;while(t.scrollWidth>t.clientWidth&&fs>30){fs-=2;t.style.fontSize=fs+'px';}
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['inf']=tl;});</script>
</body></html>""" % dict(W=W, H=Hh, bg=bg, shadow=shadow, P=P, left=left, cw=cw, cell_w=cell_w, cell_h=L["cell_h"], title_y=L["title_y"],
                       title_fs=L["title_fs"], clab_fs=L["clab_fs"], crit_fs=L["crit_fs"], name_fs=L["name_fs"], stamp_fs=L["stamp_fs"],
                       stamp_w=cell_w - 96, stamp_hw=(cell_w - 96) // 2, gx=gx, gy=gy, reason_y=grid_bottom + 34, reason_fs=L["reason_fs"],
                       demo_y=L["demo_y"], demo_fs=L["demo_fs"], TOTAL=TOTAL, FPS=FPS, logo=logo, title=H.escape(title),
                       cells="\n".join(cells), reason_div=reason_div, demo_div=demo_div, js=js)


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--names", default="")
    ap.add_argument("--odd", type=int, default=0)
    ap.add_argument("--criterion", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--title", default="ACHE O INFILTRADO")
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
        a.names = a.names or "JOGADOR A|JOGADOR B|JOGADOR C|JOGADOR D|JOGADOR E"
        a.odd = a.odd or 3
        a.criterion = a.criterion or "DEMONSTRAÇÃO DO CRITÉRIO"
        a.reason = a.reason or "Motivo de demonstração: o que falta a ele no critério."
    names = [n.strip() for n in a.names.split("|") if n.strip()]
    if len(names) != 5:
        sys.exit('--names: dê exatamente 5 nomes, "N1|N2|N3|N4|N5" (ou use --demo)')
    if not 1 <= a.odd <= 5:
        sys.exit("--odd vai de 1 a 5")
    if not a.criterion:
        sys.exit("--criterion é obrigatório (ou use --demo)")
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    TOTAL = total(len(names))
    html = build_html(a.aspect, a.title, a.criterion, names, a.odd, a.reason, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Ache o Infiltrado %s %s" % (a.aspect, name)
    ti = TOTAL - STEP - HOLD  # momento em que o infiltrado vira branco
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
            ts = [0.5, INTRO + 0.2, INTRO + STEP * 1.5, ti - 0.3, ti + 0.4, TOTAL - 0.8]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "inf_f.png")
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
