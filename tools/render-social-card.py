"""Render the site's typographic social preview from the bundled font assets."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import types
from PIL import Image, ImageDraw, ImageFont

# fontTools can use Python Brotli; Node's built-in decoder is a fallback.
try:
    import brotli
except ImportError:
    brotli = types.ModuleType('brotli')
    def decode_brotli(data):
        return subprocess.run(
            ['node', '-e', "process.stdout.write(require('node:zlib').brotliDecompressSync(require('node:fs').readFileSync(0)))"],
            input=data, stdout=subprocess.PIPE, check=True,
        ).stdout
    brotli.decompress = decode_brotli
    sys.modules['brotli'] = brotli

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
SCALE = 2


def render():
    with TemporaryDirectory() as temp:
        font = TTFont(ROOT / 'assay/fonts/fraunces-normal.woff2')
        requested = {'wght': 390, 'opsz': 72, 'SOFT': 65, 'WONK': 0}
        axes = {a.axisTag: requested[a.axisTag] for a in font['fvar'].axes if a.axisTag in requested}
        display = instantiateVariableFont(font, axes, inplace=False)
        display.flavor = None
        display_path = Path(temp) / 'display.ttf'
        display.save(display_path)
        mono = TTFont(ROOT / 'fonts/IBMPlexMono-Regular.woff2')
        mono.flavor = None
        mono_path = Path(temp) / 'mono.ttf'
        mono.save(mono_path)

        image = Image.new('RGB', (1200*SCALE, 630*SCALE), '#060b18')
        draw = ImageDraw.Draw(image)
        def face(path, size): return ImageFont.truetype(str(path), size*SCALE)
        def text(x, y, value, size, fill, path=display_path):
            draw.text((x*SCALE, y*SCALE), value, font=face(path, size), fill=fill)
        def line(coords, fill, width=1):
            draw.line(tuple(int(v*SCALE) for v in coords), fill=fill, width=width*SCALE)

        for i, color in enumerate(('#b7a5ef', '#8ed7da', '#8db9e3', '#dfa2cd', '#f3c560')):
            line((82+i*5, 62+i*7, 106+i*5, 62+i*7), color, 3)
        text(154, 58, 'KASKADE', 24, '#f3eee3', mono_path)
        text(80, 160, 'A second look at', 82, '#f3eee3')
        text(80, 257, 'AI-made work.', 88, '#f3c560')
        text(84, 386, 'Independent checks of lead lists and research.', 30, '#b5bfce')
        line((80, 485, 1120, 485), '#283247')
        text(82, 523, 'PILOT PROPOSAL  /  HUMAN-REVIEWED', 18, '#8ed7da', mono_path)
        text(833, 523, 'kaskade.systems', 18, '#b5bfce', mono_path)
        image.resize((1200, 630), Image.Resampling.LANCZOS).save(ROOT / 'assets/kaskade-review.png', optimize=True)


if __name__ == '__main__':
    render()
