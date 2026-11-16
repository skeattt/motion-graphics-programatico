#!/usr/bin/env python
"""Peça 06 — Relógio 10 em 60 (direção A: anel de 60 s + contador "7/10" + grade de 10 vagas). Python padrão + Chrome + ffmpeg.

  python build_relogio.py render [--answers "R1|R2|..."] [--hits 7] [--times "4,9,15"] [--seconds 60]
        [--title "10 EM 60 S"] [--label "RESPOSTAS VÁLIDAS"]
        [--aspect 9x16|16x9] [--kind mp4|webm|still|sheet] [--transparent] [--demo] [--scale 1] [--name NOME] [--at 30] [--browser CAMINHO]
  --answers  texto de cada resposta válida, na ordem, separado por "|" (até 10); a vaga mostra "N · TEXTO"
  --hits     só o número de respostas válidas (sem texto; a vaga mostra só o número). Ignorado se houver --answers
  --times    segundo do relógio (0 a --seconds) em que cada resposta foi validada, em ordem; padrão: espalhadas por igual
  --seconds  duração do relógio (padrão 60). Se a 10ª vaga acender antes do fim, o relógio para ali.
  --kind mp4 (fundo preto, com logo) | webm (transparente, sem logo, para pôr sobre vídeo) | still (PNG em --at s) | sheet (folha de contato com zona segura)
Saídas em ../9x16 ou ../16x9: "Relógio 10 em 60 <aspecto> <nome>.<ext>". Duração: 0,9 s + relógio + 1,6 s.
Movimento principal: a vaga acende na cor de destaque e o contador vira. Secundários: o brilho de destaque da vaga e o anel que se esvazia contando os segundos.
"""
import argparse, base64, importlib.util, math, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PIECE = os.path.dirname(HERE)
MOTION = os.path.dirname(PIECE)
BS = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "engine", "render_core.py")  # renderizador próprio (Chrome DevTools)
LOGO = os.path.join(os.path.dirname(os.path.dirname(PIECE)), "assets", "brand", "logo.png")  # marca demo
FPS, P = 30, "#00C2A8"
INTRO, HOLD = 0.9, 1.6
SLOTS = 10

LAYOUT = {
    "9x16": dict(W=1080, H=1920, left=72, right=928, logo_y=265, logo_h=64, lab_y=420, lab_fs=54,
                 ring_cx=213, ring_cy=660, ring_r=128, ring_sw=26, sec_fs=104,
                 cnt_x=420, cnt_y=540, num_fs=250, den_fs=100, sub_y=790, sub_fs=34,
                 grid_x=72, grid_y=880, cell_w=416, cell_h=100, col_gap=24, row_step=122, cell_fs=40,
                 demo_y=1500, demo_fs=26),
    "16x9": dict(W=1920, H=1080, left=160, right=1760, logo_y=70, logo_h=48, lab_y=150, lab_fs=44,
                 ring_cx=360, ring_cy=560, ring_r=176, ring_sw=32, sec_fs=140,
                 cnt_x=600, cnt_y=420, num_fs=260, den_fs=104, sub_y=680, sub_fs=32,
                 grid_x=1060, grid_y=260, cell_w=340, cell_h=104, col_gap=20, row_step=124, cell_fs=38,
                 demo_y=985, demo_fs=24),
}


def end_time(times, seconds):
    return times[SLOTS - 1] if len(times) >= SLOTS else seconds


def total(times, seconds):
    return INTRO + end_time(times, seconds) + HOLD


def build_html(aspect, answers, times, seconds, title, label, transparent, demo):
    L = LAYOUT[aspect]
    W, H = L["W"], L["H"]
    bg = "transparent" if transparent else "#000000"
    shadow = "text-shadow:0 4px 28px rgba(0,0,0,.65),0 1px 3px rgba(0,0,0,.8);" if transparent else ""
    track = "rgba(255,255,255,.2)" if transparent else "#262626"
    luri = "" if transparent else "data:image/png;base64," + base64.b64encode(open(LOGO, "rb").read()).decode()
    END = end_time(times, seconds)
    TOTAL = INTRO + END + HOLD
    r, sw = L["ring_r"], L["ring_sw"]
    C = 2 * math.pi * r
    box = 2 * r + sw
    ring = ('<svg class="abs" id="ring" width="%d" height="%d" viewBox="0 0 %d %d" style="left:%dpx;top:%dpx">'
            '<circle cx="%f" cy="%f" r="%d" fill="none" stroke="%s" stroke-width="%d"/>'
            '<circle id="arc" cx="%f" cy="%f" r="%d" fill="none" stroke="%s" stroke-width="%d" stroke-linecap="butt"'
            ' stroke-dasharray="%.3f" transform="rotate(-90 %f %f)" style="stroke-dashoffset:0"/></svg>'
            % (box, box, box, box, L["ring_cx"] - box / 2, L["ring_cy"] - box / 2,
               box / 2, box / 2, r, track, sw, box / 2, box / 2, r, P, sw, C, box / 2, box / 2))
    secs = "".join('<div class="abs sec" id="s%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%d</div>'
                   % (v, L["ring_cx"] - r, L["ring_cy"] - r, 2 * r, 2 * r, v) for v in range(seconds + 1))
    cnts = "".join('<div class="abs cnt" id="c%d" style="left:%dpx;top:%dpx"><span class="n">%d</span><span class="d">/%d</span></div>'
                   % (k, L["cnt_x"], L["cnt_y"], k, SLOTS) for k in range(SLOTS + 1))
    cells = ""
    for i in range(SLOTS):
        x = L["grid_x"] + (i % 2) * (L["cell_w"] + L["col_gap"])
        y = L["grid_y"] + (i // 2) * L["row_step"]
        txt = "%d" % (i + 1)
        if i < len(answers) and answers[i]:
            txt = "%d · %s" % (i + 1, answers[i])
        words = "".join('<span class="m"><span class="w">%s</span></span> ' % w for w in txt.split())
        cells += ('<div class="abs cell" id="e%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
                  '<div class="abs fill" id="f%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx"></div>'
                  '<div class="abs ct" id="t%d" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">%s</div>'
                  % (i, x, y, L["cell_w"], L["cell_h"], i, x, y, L["cell_w"], L["cell_h"],
                     i, x + 30, y, L["cell_w"] - 48, L["cell_h"], words))
    logo = '<img id="logo" class="abs" alt="" src="%s" style="left:%dpx;top:%dpx;height:%dpx">' % (luri, L["left"], L["logo_y"], L["logo_h"]) if luri else ""
    demo_div = ""
    if demo and not transparent:
        demo_div = '<div class="abs" id="demo" style="left:%dpx;top:%dpx;font-size:%dpx">DEMO. TROQUE AS RESPOSTAS ANTES DE POSTAR.</div>' % (L["left"], L["demo_y"], L["demo_fs"])
    js = ["tl.set('.sec,.cnt,.ct .w',{autoAlpha:0},0);tl.set('.fill',{autoAlpha:0,scaleX:0},0);",
          "tl.fromTo('#lab',{autoAlpha:0,y:20},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out'},0.2);",
          "tl.fromTo('#ring',{autoAlpha:0,scale:0.92},{autoAlpha:1,scale:1,duration:0.7,ease:'expo.out'},0.25);",
          "tl.set('#s%d',{autoAlpha:1},0.3);tl.fromTo('#s%d',{y:24},{y:0,duration:0.6,ease:'expo.out'},0.3);" % (seconds, seconds),
          "tl.set('#c0',{autoAlpha:1},0.35);tl.fromTo('#c0',{y:30},{y:0,duration:0.6,ease:'expo.out'},0.35);",
          "tl.fromTo('#sub',{autoAlpha:0},{autoAlpha:1,duration:0.5},0.45);",
          "tl.fromTo('.cell',{autoAlpha:0,y:24},{autoAlpha:1,y:0,duration:0.6,ease:'expo.out',stagger:0.035},0.4);",
          # o anel se esvazia, linear, do início do relógio até o fim (ou até a 10ª vaga)
          "tl.fromTo('#arc',{strokeDashoffset:0},{strokeDashoffset:%.3f,duration:%.3f,ease:'none'},%.2f);" % (C * END / seconds, END, INTRO)]
    if luri:
        js.append("tl.fromTo('#logo',{opacity:0},{opacity:1,duration:0.6},0.1);")
    for j in range(1, int(math.floor(END + 1e-6)) + 1):
        v = seconds - j
        if v < 0:
            break
        js.append("tl.set('#s%d',{autoAlpha:0},%.2f);tl.set('#s%d',{autoAlpha:1},%.2f);" % (v + 1, INTRO + j, v, INTRO + j))
    for k, c in enumerate(times[:SLOTS]):
        t = INTRO + c
        js.append("tl.set('#f%d',{autoAlpha:1},%.3f);tl.to('#f%d',{scaleX:1,duration:0.4,ease:'expo.out'},%.3f);" % (k, t, k, t))
        js.append("tl.fromTo('#f%d',{boxShadow:'0 0 0px 0px rgba(0,194,168,0.9)'},{boxShadow:'0 0 46px 6px rgba(0,194,168,0)',duration:0.9,ease:'power2.out'},%.3f);" % (k, t + 0.05))
        js.append("tl.set('#t%d .w',{autoAlpha:1},%.3f);tl.fromTo('#t%d .w',{yPercent:115},{yPercent:0,duration:0.55,ease:'expo.out',stagger:0.05},%.3f);" % (k, t + 0.12, k, t + 0.12))
        js.append("tl.set('#c%d',{autoAlpha:0},%.3f);tl.set('#c%d',{autoAlpha:1},%.3f);tl.fromTo('#c%d .n',{yPercent:35,opacity:0},{yPercent:0,opacity:1,duration:0.45,ease:'expo.out'},%.3f);"
                  % (k, t + 0.1, k + 1, t + 0.1, k + 1, t + 0.1))
    js.append("tl.to('#scene',{opacity:0,duration:0.4,ease:'power2.in'},%.2f);tl.set({},{},%.2f);" % (TOTAL - 0.4, TOTAL))
    js = "\n".join(js)
    html = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=%(W)d, height=%(H)d">
<style>
@font-face{font-family:'Rel Head';src:url('../../../assets/fonts/Inter-Black.ttf') format('truetype');font-weight:1 1000;font-display:block}
@font-face{font-family:'Rel Label';src:url('../../../assets/fonts/Inter-Bold.ttf') format('truetype');font-weight:1 1000;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}
#root{position:relative;width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:%(bg)s}.abs{position:absolute}
#scene{position:absolute;inset:0}
#ring{transform-origin:50%% 50%%}
#lab{left:%(left)dpx;top:%(lab_y)dpx;font:700 %(lab_fs)dpx/1 'Rel Label',sans-serif;color:#fff;white-space:nowrap;%(shadow)s}
.sec{display:flex;align-items:center;justify-content:center;font:900 %(sec_fs)dpx/1 'Rel Head',sans-serif;color:#fff;font-variant-numeric:tabular-nums;letter-spacing:-.02em;%(shadow)s}
.cnt{white-space:nowrap;line-height:1;%(shadow)s}
.cnt .n{display:inline-block;font:900 %(num_fs)dpx/1 'Rel Head',sans-serif;color:%(P)s;letter-spacing:-.03em}
.cnt .d{display:inline-block;font:900 %(den_fs)dpx/1 'Rel Head',sans-serif;color:#fff;margin-left:.08em}
#sub{left:%(cnt_x)dpx;top:%(sub_y)dpx;font:700 %(sub_fs)dpx/1 'Rel Label',sans-serif;color:rgba(255,255,255,.62);white-space:nowrap;letter-spacing:.01em;%(shadow)s}
.cell{border:3px solid rgba(0,194,168,.38);border-radius:18px}
.fill{background:%(P)s;border-radius:18px;transform-origin:0 50%%}
.ct{display:flex;align-items:center;gap:.25em;font:700 %(cell_fs)dpx/1 'Rel Label',sans-serif;color:#000;white-space:nowrap;overflow:visible}
.m{display:inline-block;overflow:hidden;vertical-align:top;padding:.08em .02em .14em;line-height:1.1}.w{display:inline-block}
#demo{font:700 %(demo_fs)dpx/1 'Rel Label',sans-serif;color:rgba(255,255,255,.55);letter-spacing:.12em}
</style></head><body>
<div id="root" data-composition-id="rel" data-start="0" data-width="%(W)d" data-height="%(H)d" data-duration="%(TOTAL).2f" data-fps="%(FPS)d">
<div id="scene">
%(logo)s
<div id="lab" class="abs">%(title)s</div>
%(ring)s
%(secs)s
%(cnts)s
<div id="sub" class="abs">%(label)s</div>
%(cells)s
%(demo_div)s
</div></div>
<script src="../../../assets/vendor/gsap.min.js"></script>
<script>document.fonts.ready.then(function(){  // mede o texto só com a fonte final carregada

document.querySelectorAll('.ct').forEach(function(el){var fs=%(cell_fs)d;while(el.scrollWidth>el.clientWidth&&fs>22){fs-=2;el.style.fontSize=fs+'px';}});
var tl=gsap.timeline({paused:true});
%(js)s
window.__timelines=window.__timelines||{};window.__timelines['rel']=tl;});</script>
</body></html>""" % dict(W=W, H=H, bg=bg, shadow=shadow, P=P, left=L["left"], lab_y=L["lab_y"], lab_fs=L["lab_fs"], sec_fs=L["sec_fs"],
                       num_fs=L["num_fs"], den_fs=L["den_fs"], cnt_x=L["cnt_x"], sub_y=L["sub_y"], sub_fs=L["sub_fs"], cell_fs=L["cell_fs"],
                       demo_fs=L["demo_fs"], TOTAL=TOTAL, FPS=FPS, logo=logo, title=title, label=label, ring=ring, secs=secs, cnts=cnts,
                       cells=cells, demo_div=demo_div, js=js)
    return html


def load_bs():
    spec = importlib.util.spec_from_file_location("bs", BS)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--answers", default="")
    ap.add_argument("--hits", type=int, default=-1)
    ap.add_argument("--times", default="")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--title", default="10 EM 60 S")
    ap.add_argument("--label", default="RESPOSTAS VÁLIDAS")
    ap.add_argument("--aspect", default="9x16", choices=list(LAYOUT))
    ap.add_argument("--kind", default="mp4", choices=["mp4", "webm", "still", "sheet"])
    ap.add_argument("--transparent", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--name", default="")
    ap.add_argument("--at", type=float, default=-1)
    ap.add_argument("--browser")
    a = ap.parse_args()
    if a.seconds < 5 or a.seconds > 300:
        sys.exit("--seconds precisa ficar entre 5 e 300")
    answers = [s.strip() for s in a.answers.split("|")] if a.answers.strip() else []
    if answers:
        n = len(answers)
    elif a.hits >= 0:
        n = a.hits
    else:
        sys.exit("dê --answers \"R1|R2|...\" ou --hits N")
    if n > SLOTS:
        sys.exit("no máximo %d respostas" % SLOTS)
    if a.times.strip():
        times = [float(x) for x in a.times.split(",") if x.strip()]
        if len(times) != n:
            sys.exit("--times precisa ter um tempo por resposta (%d)" % n)
        if any(t2 <= t1 for t1, t2 in zip(times, times[1:])) or any(t < 0.5 or t > a.seconds for t in times):
            sys.exit("--times precisa ser crescente, entre 0,5 e %d" % a.seconds)
    else:
        times = [round(a.seconds * (k + 1) / (n + 1), 2) for k in range(n)]
    if a.kind == "webm":
        a.transparent = True
    tag = "transp" if a.transparent else "preto"
    name = a.name or tag
    TOTAL = total(times, a.seconds)
    html = build_html(a.aspect, answers, times, a.seconds, a.title, a.label, a.transparent, a.demo)
    comp = "comp-%s-%s.html" % (a.aspect, tag)
    open(os.path.join(HERE, comp), "w", encoding="utf-8").write(html)
    bs = load_bs()
    L = LAYOUT[a.aspect]
    bs.W, bs.H = L["W"], L["H"]
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado")
    outdir = os.path.join(PIECE, a.aspect)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "qa"), exist_ok=True)
    base = "Relógio 10 em 60 %s %s" % (a.aspect, name)
    sess = bs.Session(HERE, a.scale, a.browser)
    try:
        if a.transparent:
            sess.cdp.call("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        info = sess.open(comp)
        nf = int(round(info["dur"] * info["fps"]))
        if a.kind == "still":
            at = a.at if a.at >= 0 else TOTAL - HOLD + 0.8
            out = os.path.join(outdir, base + " quadro.png")
            open(out, "wb").write(sess.frame(info["id"], at, "png"))
            print(out)
            return
        if a.kind == "sheet":
            from PIL import Image, ImageDraw
            ts = [0.5]
            if times:
                ts += [INTRO + times[0] + 0.25, INTRO + times[len(times) // 2] + 0.8]
            else:
                ts += [INTRO + 2, INTRO + a.seconds / 2]
            ts += [INTRO + end_time(times, a.seconds) * 0.85, TOTAL - HOLD + 0.3, TOTAL - 0.5]
            ims = []
            for t in ts:
                p = os.path.join(os.environ.get("TEMP", "."), "rel_f.png")
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
