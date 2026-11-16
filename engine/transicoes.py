#!/usr/bin/env python
"""Transições com easing no ffmpeg (filtro xfade com expressão própria), no look da marca demo.

Ideia vinda do repositório scriptituk/xfade-easing (MIT): o `xfade` do ffmpeg aceita `transition=custom`
com uma expressão, e dá para trocar o progresso linear P por uma curva de easing. Nada do repositório
foi instalado nem copiado: as expressões abaixo foram escritas aqui. Só precisa de python e ffmpeg (>= 5).

Regras de look aplicadas: sem bounce nem elástico; entra rápido, desacelera e para firme
(ease-out); duração de painel 0,56 a 0,88 s (padrão 0,64 s); cada transição tem um movimento principal
e um traço na cor de destaque #00C2A8 como movimento secundário; só preto, branco e a cor de destaque.

USO (linha de comando)
  python transicoes.py list
  python transicoes.py junta A.mp4 B.mp4 -t varredura -o saida.mp4 [--dur 0.64] [--fps 30]
  python transicoes.py previa A.mp4 B.mp4 --out-dir PASTA      (folha jpg + gif com as 4 transições)

USO (em Python)
  import transicoes
  transicoes.junta(["a.mp4", "b.mp4", "c.mp4"], "empurra", "saida.mp4")   # n clipes, mesma transição
  transicoes.filtro("flash", 0.64, offset=3.0)                              # só a string do xfade

"""
import argparse
import json
import os
import shutil
import subprocess
import sys

# cor de destaque #00C2A8 = R0 G194 B168. O xfade roda em gbrp, onde os planos são G, B, R (0, 1, 2).
DESTAQUE = "if(eq(PLANE,0),194,if(eq(PLANE,1),168,0))"


def _pa(x, y):
    """Pixel do clipe A no plano atual, na posição (x,y)."""
    return "if(eq(PLANE,0),a0(%s,%s),if(eq(PLANE,1),a1(%s,%s),a2(%s,%s)))" % ((x, y) * 3)


def _pb(x, y):
    return "if(eq(PLANE,0),b0(%s,%s),if(eq(PLANE,1),b1(%s,%s),b2(%s,%s)))" % ((x, y) * 3)


# ---- easings (todos terminam firmes; nenhum passa de 1, então sem bounce) --------------------------
EASINGS = {
    "quad-out": "(1-pow(1-({p}),2))",
    "cubic-out": "(1-pow(1-({p}),3))",
    "quint-out": "(1-pow(1-({p}),5))",
    "quad-in-out": "if(lt(({p}),0.5),2*pow({p},2),1-pow(-2*({p})+2,2)/2)",
    "cubic-in-out": "if(lt(({p}),0.5),4*pow({p},3),1-pow(-2*({p})+2,3)/2)",
}


# No xfade, P vai de 1 (início) a 0 (fim); Q = 1-P é o progresso de 0 a 1.
Q = "(1-P)"


def ease(name, p=Q):
    return EASINGS[name].replace("{p}", p)


# ---- as transições ---------------------------------------------------------------------------------
def _varredura():
    """B entra da esquerda por uma varredura; um traço de destaque vai na frente da borda."""
    e = ease("quint-out")
    xe = "(W*%s)" % e
    return ("if(lt(abs(X-%s),9),%s,if(lt(X,%s),B,A))" % (xe, DESTAQUE, xe))


def _borda():
    """Variante escolhida na rodada de opções A/B/C: a borda de destaque que varre esconde o texto
    velho e revela o novo, e os dois textos andam no sentido da varredura no mesmo easing (nada parado no corte).
    A anda para a direita até 14% da largura enquanto é coberto; B chega 14% atrás e assenta junto com a borda."""
    e = ease("quint-out")
    xe = "(W*%s)" % e
    s = "(W*0.14)"
    return ("if(lt(abs(X-%s),9),%s,if(lt(X,%s),%s,%s))"
            % (xe, DESTAQUE, xe, _pb("X+%s*(1-%s)" % (s, e), "Y"), _pa("X-%s*%s" % (s, e), "Y")))


def _empurra():
    """A sobe e sai, B entra por baixo empurrando; fio de destaque na emenda."""
    off = "(H*%s)" % ease("cubic-out")
    seam = "(H-%s)" % off
    return ("if(lt(abs(Y-%s),5),%s,if(lt(Y,%s),%s,%s))"
            % (seam, DESTAQUE, seam, _pa("X", "Y+" + off), _pb("X", "Y-" + seam)))


def _flash():
    """A apaga na cor de destaque e B acende saindo dele (a cor que acende). Sem corte brusco."""
    k_in = "pow(2*%s,2)" % Q
    k_out = "pow(2-2*%s,2)" % Q
    return ("if(gt(P,0.5),A*(1-%s)+%s*%s,B*(1-%s)+%s*%s)" % (k_in, DESTAQUE, k_in, k_out, DESTAQUE, k_out))


def _abre():
    """B abre em faixa horizontal a partir do centro; dois traços de destaque nas bordas da faixa."""
    r = "(H/2*%s)" % ease("cubic-out")
    d = "abs(Y-H/2)"
    return ("if(lt(abs(%s-%s),6),%s,if(lt(%s,%s),B,A))" % (d, r, DESTAQUE, d, r))


TRANSICOES = {
    "varredura": {"expr": _varredura, "dur": 0.64, "descricao": "B varre da esquerda para a direita (quint-out), traço de destaque na frente"},
    "borda": {"expr": _borda, "dur": 0.64, "descricao": "opção B: borda de destaque varre, esconde o texto velho e revela o novo; textos andam junto (quint-out)"},
    "empurra": {"expr": _empurra, "dur": 0.72, "descricao": "B sobe empurrando A (cubic-out), fio de destaque na emenda"},
    "flash": {"expr": _flash, "dur": 0.56, "descricao": "A apaga na cor de destaque e B acende dele (quad), sem corte"},
    "abre": {"expr": _abre, "dur": 0.80, "descricao": "B abre em faixa a partir do centro (cubic-out), traços de destaque nas bordas"},
}


def filtro(nome, dur=None, offset=0.0):
    """String do filtro xfade pronta para o filter_complex (entradas em gbrp, mesmo tamanho e fps)."""
    if nome not in TRANSICOES:
        raise SystemExit("transição desconhecida: %s (opções: %s)" % (nome, ", ".join(TRANSICOES)))
    t = TRANSICOES[nome]
    dur = t["dur"] if dur is None else dur
    return "xfade=transition=custom:duration=%.3f:offset=%.3f:expr='%s'" % (dur, offset, t["expr"]())


def _need(tool):
    p = shutil.which(tool)
    if not p:
        raise SystemExit("%s não encontrado no PATH" % tool)
    return p


def duracao(path):
    out = subprocess.run([_need("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def junta(clipes, nome, saida, dur=None, fps=30, largura=None, altura=None, crf=16, extra_args=None):
    """Junta n clipes com a mesma transição. Todos viram o tamanho do primeiro (ou largura x altura)."""
    if len(clipes) < 2:
        raise SystemExit("preciso de pelo menos 2 clipes")
    t = TRANSICOES[nome]
    dur = t["dur"] if dur is None else dur
    ff = _need("ffmpeg")
    if not (largura and altura):
        o = subprocess.run([_need("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "json", clipes[0]], capture_output=True, text=True, check=True).stdout
        s = json.loads(o)["streams"][0]
        largura, altura = s["width"], s["height"]
    durs = [duracao(c) for c in clipes]
    cmd = [ff, "-y", "-loglevel", "error"]
    for c in clipes:
        cmd += ["-i", c]
    partes = []
    for i in range(len(clipes)):
        partes.append("[%d:v]fps=%d,scale=%d:%d:flags=lanczos,setsar=1,format=gbrp,settb=AVTB[v%d]" % (i, fps, largura, altura, i))
    atual, acum = "v0", durs[0]
    for i in range(1, len(clipes)):
        off = acum - dur
        rot = "x%d" % i
        partes.append("[%s][v%d]%s[%s]" % (atual, i, filtro(nome, dur, off), rot))
        atual = rot
        acum = off + durs[i]
    partes.append("[%s]scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[fim]" % atual)
    cmd += ["-filter_complex", ";".join(partes), "-map", "[fim]", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-movflags", "+faststart"]
    cmd += (extra_args or []) + [saida]
    subprocess.run(cmd, check=True)
    return saida


def previa(a, b, out_dir, nomes=None, largura=540, altura=960):
    """Folha de contato (jpg) e GIF em loop (360x640) com cada transição entre os clipes a e b."""
    ff = _need("ffmpeg")
    os.makedirs(out_dir, exist_ok=True)
    nomes = nomes or list(TRANSICOES)
    da = duracao(a)
    # pega só o final de A e o começo de B (1,2 s de cada) para a prévia ser curta
    ta, tb = min(1.2, da), 1.2
    partes_gif = []
    linhas = []
    for n in nomes:
        d = TRANSICOES[n]["dur"]
        mp4 = os.path.join(out_dir, "tmp_%s.mp4" % n)
        cmd = [ff, "-y", "-loglevel", "error", "-sseof", "-%.3f" % ta, "-i", a, "-t", "%.3f" % tb, "-i", b]
        graph = ("[0:v]fps=30,scale=%d:%d,setsar=1,format=gbrp,settb=AVTB[a];[1:v]fps=30,scale=%d:%d,setsar=1,format=gbrp,settb=AVTB[b];"
                 "[a][b]%s[o];[o]format=yuv420p[f]" % (largura, altura, largura, altura, filtro(n, d, ta - d)))
        subprocess.run(cmd + ["-filter_complex", graph, "-map", "[f]", "-c:v", "libx264", "-crf", "14", mp4], check=True)
        partes_gif.append(mp4)
        # 5 quadros: antes, 25%, 50%, 75%, depois
        t0 = ta - d
        ts = [t0 - 0.1, t0 + d * 0.25, t0 + d * 0.5, t0 + d * 0.75, t0 + d + 0.1]
        jpgs = []
        for i, t in enumerate(ts):
            jp = os.path.join(out_dir, "tmp_%s_%d.jpg" % (n, i))
            subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "%.3f" % max(t, 0), "-i", mp4, "-frames:v", "1", "-q:v", "3",
                            "-vf", "scale=216:-2", jp], check=True)
            jpgs.append(jp)
        linha = os.path.join(out_dir, "tmp_linha_%s.jpg" % n)
        cmd2 = [ff, "-y", "-loglevel", "error"]
        for jp in jpgs:
            cmd2 += ["-i", jp]
        cmd2 += ["-filter_complex", "hstack=inputs=5", "-frames:v", "1", "-q:v", "3", linha]
        subprocess.run(cmd2, check=True)
        linhas.append(linha)
        for jp in jpgs:
            os.remove(jp)
    folha = os.path.join(out_dir, "transicoes-folha.jpg")
    cmd3 = [ff, "-y", "-loglevel", "error"]
    for l in linhas:
        cmd3 += ["-i", l]
    subprocess.run(cmd3 + ["-filter_complex", ("vstack=inputs=%d" % len(linhas)) if len(linhas) > 1 else "null", "-frames:v", "1", "-q:v", "3", folha], check=True)
    # GIF: concatena as 4 prévias, 360x640, 15 fps
    gif = os.path.join(out_dir, "transicoes-previa.gif")
    cmd4 = [ff, "-y", "-loglevel", "error"]
    for m in partes_gif:
        cmd4 += ["-i", m]
    n_in = len(partes_gif)
    ins = "".join("[%d:v]" % i for i in range(n_in))
    cmd4 += ["-filter_complex", "%sconcat=n=%d:v=1:a=0,fps=12,scale=360:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=32[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" % (ins, n_in),
             "-loop", "0", gif]
    subprocess.run(cmd4, check=True)
    for m in partes_gif:
        os.remove(m)
    for l in linhas:
        os.remove(l)
    return folha, gif


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd")
    sp.add_parser("list")
    j = sp.add_parser("junta")
    j.add_argument("clipes", nargs="+")
    j.add_argument("-t", "--transicao", required=True, choices=list(TRANSICOES))
    j.add_argument("-o", "--saida", required=True)
    j.add_argument("--dur", type=float)
    j.add_argument("--fps", type=int, default=30)
    p = sp.add_parser("previa")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    if args.cmd == "list":
        for n, t in TRANSICOES.items():
            print("%-10s %.2f s  %s" % (n, t["dur"], t["descricao"]))
    elif args.cmd == "junta":
        print(junta(args.clipes, args.transicao, args.saida, args.dur, args.fps))
    elif args.cmd == "previa":
        print(*previa(args.a, args.b, args.out_dir), sep="\n")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
