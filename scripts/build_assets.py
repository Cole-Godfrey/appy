#!/usr/bin/env python3
"""Rebuild README artwork with Pillow/fonttools and local Imbue/Albert Sans fonts."""
import argparse
from html import escape
from pathlib import Path
import subprocess
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'docs/assets'
BONE, OLIVE, SURFACE = '#ecebe7', '#38450f', '#e1dfd9'


def outlined(text, source, x, baseline, width, color, size=None):
    font = TTFont(source)
    if 'fvar' in font:
        axes = {a.axisTag: (400 if a.axisTag == 'wght' else a.defaultValue) for a in font['fvar'].axes}
        font = instantiateVariableFont(font, axes)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    advances = [font['hmtx'][cmap[ord(c)]][0] for c in text]
    scale = size / font['head'].unitsPerEm if size else width / sum(advances)
    paths, position = [], 0
    for letter, advance in zip(text, advances):
        pen = SVGPathPen(glyphs)
        glyphs[cmap[ord(letter)]].draw(pen)
        paths.append(f'<path transform="translate({position} 0)" d="{pen.getCommands()}"/>')
        position += advance
    return f'<g fill="{color}" transform="translate({x} {baseline}) scale({scale} {-scale})">' + ''.join(paths) + '</g>'


def svg(path, width, height, background, content, title):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title><rect width="{width}" height="{height}" fill="{background}"/>{content}</svg>\n')


def font(path, size):
    return ImageFont.truetype(str(path), size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imbue', type=Path, required=True)
    parser.add_argument('--albert', type=Path, required=True)
    parser.add_argument('--mono', type=Path, required=True, help='Local monospace TTF/TTC for real terminal output')
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    content = outlined('appy', args.imbue, 44, 274, 420, OLIVE)
    content += outlined('Find the role.', args.albert, 568, 202, None, OLIVE, size=76)
    content += outlined('Keep the thread.', args.albert, 568, 286, None, OLIVE, size=76)
    svg(ASSETS / 'banner.svg', 1280, 420, BONE, content, 'Appy. Find the role. Keep the thread.')

    social = Image.new('RGB', (1280, 640), OLIVE)
    draw = ImageDraw.Draw(social)
    face = font(args.imbue, 520)
    draw.text((48, 399), 'appy', font=face, fill=BONE, anchor='ls')
    draw.text((702, 202), 'Find the role.', font=font(args.albert, 54), fill=BONE)
    draw.text((702, 266), 'Keep the thread.', font=font(args.albert, 54), fill=BONE)
    draw.text((706, 397), 'A local agent workflow', font=font(args.albert, 30), fill=BONE)
    draw.text((706, 437), 'for job applications.', font=font(args.albert, 30), fill=BONE)
    social.save(ASSETS / 'social-preview.png', optimize=True)

    output = subprocess.check_output([sys.executable, str(ROOT / 'scripts/demo.py')], text=True).splitlines()
    command = '$ python3 scripts/demo.py'
    mono = font(args.mono, 24)
    title = font(args.albert, 27)

    def frame(typed, lines):
        canvas = Image.new('RGB', (1200, 820), OLIVE)
        d = ImageDraw.Draw(canvas)
        d.text((48, 32), 'Appy / offline demo', font=title, fill=BONE)
        d.text((48, 102), typed, font=mono, fill=BONE)
        for i, line in enumerate(lines):
            d.text((48, 158 + i * 31), line, font=mono, fill=BONE)
        return canvas

    frames, durations = [frame('$ ', [])], [650]
    for i in range(3, len(command) + 1, 2):
        frames.append(frame(command[:i], []))
        durations.append(55)
    for i in range(1, len(output) + 1):
        frames.append(frame(command, output[:i]))
        durations.append(170 if output[i - 1] else 70)
    durations[-1] = 4200
    frames[0].save(ASSETS / 'demo.gif', save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=1)
    frame(command, output).save(ASSETS / 'demo.png', optimize=True)
    print('Built banner, social image, and demo GIF/still from actual CLI output.')


if __name__ == '__main__':
    main()
