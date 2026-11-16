#!/usr/bin/env python
"""Renderiza a demo de cada peça (MP4 9:16) e gera os GIFs do README em docs/gifs.

    python demo.py                 # todas as peças
    python demo.py 03 08           # só as peças que começam com esses números
    python demo.py --aspect 16x9   # as mesmas demos em 16:9 (GIFs com sufixo -16x9)
    python demo.py --overlay       # WebM transparente da peça 03 sobre um fundo em movimento
    python demo.py --browser CAMINHO_DO_CHROME

Todos os nomes e dados abaixo são fictícios.
"""
import os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
PHOTO = os.path.join(ROOT, "assets", "brand", "foto-demo.png")
DEMOS = [
    ("03-pista-em-queda", "build_pista.py", "Pista em Queda",
     ["--clues", "Nasceu em 1987|Jogou em três ligas diferentes|Camisa 10 em duas Copas"]),
    ("04-revelacao-do-jogador", "build_revelacao.py", "Revelação do Jogador",
     ["--player", "RAFAEL MOURA", "--photo", PHOTO, "--hit", "2"]),
    ("05-escada-as-cegas", "build_escada.py", "Escada às Cegas",
     ["--names", "Lucas Prado|Diego Vaz|Caio Mendes|Bruno Lima|Téo Andrade", "--order", "3,1,4,2,5"]),
    ("06-relogio-10-em-60", "build_relogio.py", "Relógio 10 em 60",
     ["--hits", "7", "--seconds", "20", "--times", "2,4,6,9,12,15,18", "--title", "10 EM 20 S"]),
    ("07-grade-de-dicas", "build_grade.py", "Grade de Dicas", ["--hit", "9", "--step", "0.9"]),
    ("08-veredito-do-juri", "build_veredito.py", "Veredito do Júri",
     ["--case", "O PÊNALTI DO CLÁSSICO", "--score", "62", "--args", "A:Houve contato claro na área|D:O atacante procurou o contato"]),
    ("09-ache-o-infiltrado", "build_infiltrado.py", "Ache o Infiltrado",
     ["--names", "Lucas Prado|Diego Vaz|Caio Mendes|Bruno Lima|Téo Andrade", "--odd", "3",
      "--criterion", "ARTILHEIROS DA TEMPORADA", "--reason", "Caio é zagueiro"]),
    ("10-isso-ou-aquilo", "build_isso.py", "Isso ou Aquilo",
     ["--a", "LUCAS PRADO", "--b", "DIEGO VAZ", "--pick", "a", "--question", "QUEM BATE O PÊNALTI DECISIVO?",
      "--answer", "o mais frio da dupla"]),
    ("11-foto-central", "build_foto.py", "Foto Central", ["--player", "RAFAEL MOURA", "--photo", PHOTO]),
]


def main():
    args = sys.argv[1:]
    browser = []
    if "--browser" in args:
        i = args.index("--browser")
        browser = ["--browser", args[i + 1]]
        del args[i:i + 2]
    aspect = "9x16"
    if "--aspect" in args:
        i = args.index("--aspect")
        aspect = args[i + 1]
        del args[i:i + 2]
    overlay = "--overlay" in args
    if overlay:
        args.remove("--overlay")
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg não encontrado no PATH")
    gifs = os.path.join(ROOT, "docs", "gifs")
    os.makedirs(gifs, exist_ok=True)
    if overlay:
        return overlay_demo(ffmpeg, gifs, browser)
    for slug, script, title, extra in DEMOS:
        if args and not any(slug.startswith(a) for a in args):
            continue
        t0 = time.time()
        builder = os.path.join(ROOT, "pieces", slug, "source", script)
        cmd = [sys.executable, "-I", builder, "render", "--aspect", aspect, "--kind", "mp4", "--demo", "--name", "demo"] + extra + browser
        print("==>", slug, aspect)
        subprocess.run(cmd, check=True)
        mp4 = os.path.join(ROOT, "pieces", slug, aspect, "%s %s demo.mp4" % (title, aspect))
        gif = os.path.join(gifs, slug + ("" if aspect == "9x16" else "-" + aspect) + ".gif")
        width = 360 if aspect == "9x16" else 480
        vf = "fps=12,scale=%d:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" % width
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", mp4, "-vf", vf, gif], check=True)
        print("    %s (%.0f KB) em %.0fs" % (os.path.relpath(gif, ROOT), os.path.getsize(gif) / 1024, time.time() - t0))


def overlay_demo(ffmpeg, gifs, browser):
    """WebM transparente (VP9 com alfa) da peça 03 sobre um fundo em movimento, como entraria na edição."""
    slug, script, title, extra = DEMOS[0]
    builder = os.path.join(ROOT, "pieces", slug, "source", script)
    subprocess.run([sys.executable, "-I", builder, "render", "--aspect", "9x16", "--kind", "webm", "--transparent",
                    "--name", "overlay"] + extra + browser, check=True)
    webm = os.path.join(ROOT, "pieces", slug, "9x16", "%s 9x16 overlay.webm" % title)
    gif = os.path.join(gifs, "overlay-transparente.gif")
    # fundo: degradê animado gerado pelo próprio ffmpeg (no lugar do vídeo gravado)
    fc = ("gradients=s=1080x1920:r=30:c0=0x1d3b53:c1=0x4a2440:n=2:speed=0.01[bg];"
          "[0:v]format=rgba[fg];[bg][fg]overlay=shortest=1,fps=10,scale=300:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=48:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-c:v", "libvpx-vp9", "-i", webm, "-filter_complex", fc, gif], check=True)
    print("    %s (%.0f KB)" % (os.path.relpath(gif, ROOT), os.path.getsize(gif) / 1024))


if __name__ == "__main__":
    main()
