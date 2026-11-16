#!/usr/bin/env python
"""Checa se uma peça renderiza de forma determinística (mesmo quadro em qualquer render).

    python verify.py 03-pista-em-queda [--frames 8] [--browser CAMINHO]
    python verify.py all

Para cada composição gerada (pieces/<peça>/source/comp-*.html):
  1. análise estática: avisa de relógio real (Date.now, performance.now), Math.random,
     setTimeout/setInterval e animação CSS, que escapam do seek da timeline;
  2. renderiza os mesmos instantes em dois navegadores novos e compara os SHA-256 dos PNGs.
Sai com código 2 se algum quadro diferir.
"""
import argparse, glob, hashlib, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import render_core  # noqa: E402

RISKS = {
    r"Date\.now|new Date\(": "relógio real",
    r"performance\.now": "relógio real",
    r"Math\.random": "aleatório sem semente",
    r"setTimeout|setInterval": "timer fora da timeline",
    r"@keyframes|animation\s*:": "animação CSS (não obedece ao seek)",
}


def hashes(src_dir, comp, times, scale, browser):
    s = render_core.Session(src_dir, scale, browser)
    try:
        info = s.open(comp)
        return info, [hashlib.sha256(s.frame(info["id"], t, "png")).hexdigest() for t in (times or [])]
    finally:
        s.close()


def size_of(path):
    html = open(path, encoding="utf-8").read()
    m = re.search(r'data-width="(\d+)"\s+data-height="(\d+)"', html)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920), html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("piece")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--browser")
    a = ap.parse_args()
    pieces = sorted(os.listdir(os.path.join(ROOT, "pieces"))) if a.piece == "all" else [a.piece]
    failed = 0
    for p in pieces:
        src = os.path.join(ROOT, "pieces", p, "source")
        comps = sorted(glob.glob(os.path.join(src, "comp-*.html")))
        if not comps:
            print("%s: nenhuma composição gerada ainda (rode um render antes)" % p)
            continue
        for path in comps:
            comp = os.path.basename(path)
            (render_core.W, render_core.H), html = size_of(path)
            warns = [msg for pat, msg in RISKS.items() if re.search(pat, html.replace(open(os.path.join(ROOT, "assets", "vendor", "gsap.min.js"), encoding="utf-8").read(), ""))]
            info, _ = hashes(src, comp, [], a.scale, a.browser)
            n = max(2, a.frames)
            times = [round(info["dur"] * k / (n - 1) * 0.999, 3) for k in range(n)]
            _, h1 = hashes(src, comp, times, a.scale, a.browser)
            _, h2 = hashes(src, comp, times, a.scale, a.browser)
            diff = [t for t, x, y in zip(times, h1, h2) if x != y]
            status = "OK" if not diff else "DIFERENTE em %s s" % ", ".join("%.2f" % t for t in diff)
            print("%-28s %-24s %d quadros: %s%s" % (p, comp, n, status, ("  | avisos: " + "; ".join(sorted(set(warns)))) if warns else ""))
            failed += bool(diff)
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
