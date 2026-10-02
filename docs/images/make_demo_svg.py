"""Render docs/images/demo.svg from the real output of ``python3 -m praxis_core demo``.

The README's demo picture must be real output, not a drawing. Run this from the
repository root after any change to the demo, then render the PNG beside it:

    python3 docs/images/make_demo_svg.py
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \\
        --screenshot=docs/images/demo.png --window-size=WIDTH,HEIGHT \\
        --force-device-scale-factor=2 docs/images/demo.svg

The script prints the WIDTH and HEIGHT to use. Standard library only.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "images" / "demo.svg"
COMMAND = "python3 -m praxis_core demo"
FONT, LINE, PAD, CHAR = 13, 18, 20, 7.83  # px; CHAR is one Menlo glyph at 13 px

GREY, TEXT, GREEN, YELLOW, ORANGE = "#9a9a9a", "#d4d4d4", "#6a9955", "#dcdcaa", "#ce9178"


def keep_spaces(line: str) -> str:
    """Escape for XML and make every space non-breaking: SVG renderers collapse runs of
    ordinary spaces, and the demo's table is aligned with them."""
    return escape(line).replace(" ", "\u00a0")


def colour(line: str) -> str:
    if line.startswith(("praxis demo:", "support.extract:")):
        return YELLOW
    if line.startswith("stage "):
        return GREY
    if line.startswith(("verdict: ready", "loop closed")):
        return GREEN
    if line.startswith(("verdict: stays", "canary: refused")) or "stopped at the readiness gate" in line:
        return ORANGE
    return TEXT


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "praxis_core", "demo"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    lines = proc.stdout.rstrip("\n").split("\n")
    width = int(2 * PAD + CHAR * max(len(COMMAND) + 2, *(len(line) for line in lines)) + 0.5)
    height = 40 + LINE * (len(lines) + 2) + PAD
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Menlo, Consolas, \'DejaVu Sans Mono\', monospace" '
        f'font-size="{FONT}">',
        f'  <rect width="{width}" height="{height}" rx="10" fill="#1e1e1e"/>',
        '  <circle cx="22" cy="20" r="6" fill="#ff5f56"/><circle cx="42" cy="20" r="6" fill="#ffbd2e"/>'
        '<circle cx="62" cy="20" r="6" fill="#27c93f"/>',
        f'  <text x="{width // 2}" y="25" text-anchor="middle" fill="{GREY}" font-size="12">'
        f"{escape(COMMAND)} (real output)</text>",
        "  <g>",
        f'    <text x="{PAD}" y="{40 + LINE}" fill="{TEXT}"><tspan fill="{GREEN}">$</tspan> {escape(COMMAND)}</text>',
    ]
    for i, line in enumerate(lines, start=2):
        if line:
            out.append(f'    <text x="{PAD}" y="{40 + LINE * i}" fill="{colour(line)}">{keep_spaces(line)}</text>')
    out += ["  </g>", "</svg>", ""]
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(lines)} lines, WIDTH={width} HEIGHT={height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
