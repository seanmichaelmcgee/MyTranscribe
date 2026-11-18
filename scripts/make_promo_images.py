"""
Draw the benchmark images for the README and for sharing (docs/images/).

Every number comes from docs/BENCHMARKS.md; change them there first. Writes one
SVG per image, then renders each to a PNG at twice the size with Microsoft Edge
in headless mode (skipped if Edge is not found).

    python scripts/make_promo_images.py
"""

import html
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"

# Reference palette (light): surface, inks, chrome, one highlight, two neutrals.
SURFACE, PAGE = "#fcfcfb", "#f4f3ef"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
US, REFERENCE, OTHER = "#2a78d6", "#898781", "#c9c7bd"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")          # validated all-pairs (first three slots)
FONT = "Segoe UI, system-ui, -apple-system, Helvetica, Arial, sans-serif"
BRAND = "MyTranscribe Medical · open source · runs on your own PC"


def esc(s):
    return html.escape(str(s), quote=True)


def text(x, y, s, size=14, color=INK2, weight=400, anchor="start", italic=False, halo=False):
    style = ' font-style="italic"' if italic else ""
    if halo:                                               # a surface-coloured edge keeps gridlines off the text
        style += f' stroke="{SURFACE}" stroke-width="6" stroke-linejoin="round" paint-order="stroke"'
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{style}>{esc(s)}</text>')


def bar(x0, x1, y, h, color, r=4):
    """Horizontal bar anchored at x0, rounded only at its data end."""
    r = min(r, (x1 - x0) / 2, h / 2)
    return (f'<path d="M{x0:.1f},{y:.1f} H{x1 - r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} Q{x1:.1f},{y + h:.1f} {x1 - r:.1f},{y + h:.1f} H{x0:.1f} Z" fill="{color}"/>')


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT}" role="img" aria-label="{esc(title)}">'
            f'<title>{esc(title)}</title><rect width="{width}" height="{height}" fill="{SURFACE}"/>'
            + "".join(body) + "</svg>")


def header(width, title, subtitle):
    return [text(56, 64, title, 30, INK, 700), text(56, 98, subtitle, 17, INK2)]


def footer(width, height, note):
    """Source note (one line or several), then the brand line, under a hairline."""
    lines = (note,) if isinstance(note, str) else tuple(note)
    top = height - 54 - 22 * len(lines)
    out = [f'<line x1="56" x2="{width - 56}" y1="{top}" y2="{top}" stroke="{GRID}"/>']
    out += [text(56, top + 28 + 22 * i, line, 13, MUTED) for i, line in enumerate(lines)]
    return out + [text(56, height - 26, BRAND, 13, INK2, 600)]


def axis(x0, x1, y_top, y_bottom, vmax, ticks, fmt):
    """Hairline grid at each tick, a baseline at zero, tick labels under the plot."""
    out = []
    for t in ticks:
        x = x0 + (x1 - x0) * t / vmax
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y_top}" y2="{y_bottom}" '
                   f'stroke="{AXIS if t == 0 else GRID}" stroke-width="1"/>')
        out.append(text(x, y_bottom + 20, fmt(t), 12, MUTED, anchor="middle"))
    return out


def bar_panel(x_label, x0, x1, y, heading, rows, vmax, ticks, fmt, row_h=46, bar_h=20, notes=None):
    """A titled panel of labelled bars: rows = (label, value, colour, emphasised); notes = {row: text}."""
    out = [text(x_label, y, heading, 17, INK, 600)]
    top = y + 18
    for i, (label, value, color, strong) in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        out.append(text(x0 - 16, cy + 5, label, 15, INK if strong else INK2, 600 if strong else 400, "end"))
    bottom = top + len(rows) * row_h
    out += axis(x0, x1, top, bottom, vmax, ticks, fmt)
    for i, (label, value, color, strong) in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        xe = x0 + (x1 - x0) * value / vmax
        out.append(bar(x0, xe, cy - bar_h / 2, bar_h, color))
        out.append(text(xe + 8, cy + 5, fmt(value, 1), 15, INK if strong else INK2, 700 if strong else 400))
        if notes and i in notes:
            width = 7.3 * len(notes[i]) + 16                 # Segoe UI at 14 px averages about 7 px a character
            out.append(f'<rect x="{xe + 56:.1f}" y="{cy - 13:.1f}" width="{width:.0f}" height="26" '
                       f'rx="4" fill="{SURFACE}"/>')
            out.append(text(xe + 64, cy + 5, notes[i], 14, INK2))
    return out, bottom + 28


def pct(v, digits=0):
    return f"{v:.{digits}f}%"


# ── 1. What the app adds to Whisper ──────────────────────────────────────────
def steps_image():
    W, H = 1200, 740
    title = "Half the word errors of Whisper on its own"
    body = header(W, title, "Word errors (lower is better). The same Whisper large-v3 model, then each step "
                            "MyTranscribe Medical adds.")
    labels = ("Whisper large-v3 as it comes", "+ dictated punctuation and commands converted",
              "+ medical clean-up: readings, numbers, drug names",
              "+ medical prompt, pause-aware windows, term correction")
    sets = (("Real clinicians dictating (Corti Med-Dictate, 24 notes)", (44.89, 14.20, 12.25, 7.01)),
            ("Developer's voice, recordings held out from all tuning (23)", (13.87, 5.88, 3.92, 2.86)))
    y = 150
    for heading, values in sets:
        rows = [(lab, v, US if i == 3 else OTHER, i == 3) for i, (lab, v) in enumerate(zip(labels, values))]
        rows[3] = ("MyTranscribe Medical (full build)", values[3], US, True)
        half = f"{100 * (1 - values[3] / values[1]):.0f}% fewer errors than Whisper with punctuation converted"
        part, y = bar_panel(56, 470, 1090, y, heading, rows, 50, (0, 10, 20, 30, 40, 50), pct, notes={3: half})
        body += part
        y += 18
    body += footer(W, H, "Measured November 2026. Word errors ignore case and punctuation. "
                         "Corti used for evaluation only. Details: docs/BENCHMARKS.md")
    return "steps", svg(W, H, body, title)


# ── 2. Head to head ──────────────────────────────────────────────────────────
def head_to_head_image():
    W, H = 1200, 790
    title = "The most accurate open model we tested"
    body = header(W, title, "Word errors (lower is better), the same audio through every system. "
                            "Close to commercial on voices it was never tuned on.")
    systems = (("MyTranscribe Medical (Whisper large-v3)", US, True),
               ("Commercial cloud medical dictation", REFERENCE, False),
               ("MedASR (Google)", OTHER, False),
               ("Parakeet TDT 0.6B v2 (NVIDIA)", OTHER, False),
               ("Canary 1B v2 (NVIDIA)", OTHER, False))
    sets = (("Real clinicians dictating (Corti Med-Dictate, 23 notes)", (7.18, 6.04, 8.90, 12.16, 12.29)),
            ("Developer's voice, recordings held out from all tuning (23)", (3.32, 5.73, 7.23, 6.86, 6.93)))
    y, row_h = 150, 40
    for heading, values in sets:
        rows = [(name, v, color, strong) for (name, color, strong), v in zip(systems, values)]
        part, y = bar_panel(56, 470, 1090, y, heading, rows, 14, (0, 2, 4, 6, 8, 10, 12, 14), pct, row_h, 18)
        body += part
        y += 14
    body += footer(W, H, ("Measured 15 November 2026, local models on an RTX 4070 Ti SUPER, open models through "
                          "the same text options. Corti: the 23 notes",
                          "with a commercial capture (7.0% on all 24). Held-out: today's build scores 2.9%. "
                          "Details: docs/BENCHMARKS.md"))
    return "head_to_head", svg(W, H, body, title)


# ── 3. Difficult audio ───────────────────────────────────────────────────────
def conditions_image():
    W, H = 1200, 720
    title = "Holds up on difficult audio"
    body = header(W, title, "Clinical terms written correctly: drugs, doses, lab values, findings, names. "
                            "462 synthetic recordings, 28 voices.")
    names = ("MyTranscribe Medical", "Whisper large-v3, basic pipeline", "MedASR (Google)")
    rows = (("Clean", (91.5, 85.6, 70.0)), ("Telephone", (91.9, 86.6, 70.7)),
            ("Low-bitrate MP3", (91.7, 85.6, 69.3)), ("Fast speech", (90.2, 84.7, 69.4)),
            ("Busy ward", (81.3, 76.4, 41.4)), ("Fast + ward + MP3 together", (69.7, 65.9, 28.2)))
    # Legend, one row above the plot.
    for lx, name, color in zip((56, 270, 548), names, SERIES):
        body.append(f'<circle cx="{lx + 7}" cy="137" r="7" fill="{color}"/>')
        body.append(text(lx + 22, 142, name, 15, INK if color == US else INK2, 600 if color == US else 400))
    x0, x1, top, row_h = 330, 1090, 176, 62
    bottom = top + len(rows) * row_h
    body += axis(x0, x1, top, bottom, 100, (0, 20, 40, 60, 80, 100), pct)
    for i, (label, values) in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        body.append(text(x0 - 16, cy + 5, label, 15, INK2, 400, "end"))
        xs = [x0 + (x1 - x0) * v / 100 for v in values]
        body.append(f'<line x1="{min(xs):.1f}" x2="{max(xs):.1f}" y1="{cy}" y2="{cy}" stroke="{AXIS}" stroke-width="2"/>')
        for x, color in reversed(list(zip(xs, SERIES))):
            body.append(f'<circle cx="{x:.1f}" cy="{cy}" r="8" fill="{color}" stroke="{SURFACE}" stroke-width="2"/>')
        body.append(text(xs[0] + 16, cy + 5, pct(values[0], 1), 15, INK, 700))
    body += footer(W, H, "Modulate synthetic medical dictation (CC BY 4.0), test split. Synthetic voices: "
                         "for comparing conditions, not a clinical accuracy figure.")
    return "difficult_audio", svg(W, H, body, title)


# ── 4. Share card ────────────────────────────────────────────────────────────
def card_image():
    W, H = 1200, 630
    title = "Accurate medical dictation that stays on your PC"
    body = [text(64, 96, title, 40, INK, 700),
            text(64, 138, "Open-source dictation built on Whisper large-v3. Word error rates similar to or better",
                 20, INK2),
            text(64, 166, "than commercial-grade medical dictation in our testing.", 20, INK2)]
    tiles = (("7.0%", "word errors on real clinicians'", "dictation (Corti Med-Dictate)"),
             ("2.1%", "word errors on the developer's", "reading of consult letters"),
             ("0 bytes", "of audio or text sent", "anywhere"))
    tx, tw = 64, 340
    for big, l1, l2 in tiles:
        body.append(f'<rect x="{tx}" y="206" width="{tw}" height="168" rx="12" fill="{PAGE}"/>')
        body.append(text(tx + 24, 276, big, 52, US if big != "0 bytes" else INK, 700))
        body.append(text(tx + 24, 316, l1, 17, INK2))
        body.append(text(tx + 24, 340, l2, 17, INK2))
        tx += tw + 32
    # Mini comparison: Whisper on its own vs the full build, Corti.
    body.append(text(64, 424, "Real clinicians, word errors (lower is better)", 16, INK, 600))
    x0, x1 = 420, 1000
    for i, (label, v, color, strong) in enumerate((("Whisper large-v3 on its own*", 14.20, OTHER, False),
                                                    ("MyTranscribe Medical", 7.01, US, True))):
        cy = 456 + i * 40
        body.append(text(x0 - 16, cy + 5, label, 16, INK if strong else INK2, 600 if strong else 400, "end"))
        xe = x0 + (x1 - x0) * v / 16
        body.append(bar(x0, xe, cy - 10, 20, color))
        body.append(text(xe + 8, cy + 6, pct(v, 1), 16, INK if strong else INK2, 700 if strong else 400))
    body.append(f'<line x1="{x0}" x2="{x0}" y1="436" y2="516" stroke="{AXIS}"/>')
    body += footer(W, H, "*Dictated punctuation converted. Corti Med-Dictate, 24 notes, November 2026. "
                         "Windows, NVIDIA graphics card with 6 GB or more.")
    return "share_card", svg(W, H, body, title)


def edge():
    for p in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if p and Path(p).is_file():
            return p
    return None


def render_png(svg_path: Path, width: int, height: int, browser: str):
    page = svg_path.with_suffix(".render.html")
    page.write_text(f'<!doctype html><html><body style="margin:0">{svg_path.read_text(encoding="utf-8")}'
                    f"</body></html>", encoding="utf-8")
    png = svg_path.with_suffix(".png")
    png.unlink(missing_ok=True)
    profile = tempfile.mkdtemp(prefix="promo-edge-")      # a fresh profile, so a running Edge is not reused
    try:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        f"--user-data-dir={profile}", "--force-device-scale-factor=2",
                        f"--window-size={width},{height}", f"--screenshot={png}", page.as_uri()],
                       check=True, capture_output=True, timeout=60)
        for _ in range(300):                               # the launcher can return before the page is drawn
            if png.is_file() and png.stat().st_size:
                break
            time.sleep(0.1)
        time.sleep(0.5)
    finally:
        page.unlink()
        shutil.rmtree(profile, ignore_errors=True)
    return png


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    browser = edge()
    for make in (steps_image, head_to_head_image, conditions_image, card_image):
        name, content = make()
        path = OUT / f"{name}.svg"
        path.write_text(content, encoding="utf-8")
        w, h = (int(content.split(f'{k}="')[1].split('"')[0]) for k in ("width", "height"))
        print(path.relative_to(ROOT), "->", render_png(path, w, h, browser).name if browser else "(no Edge: SVG only)")


if __name__ == "__main__":
    main()
