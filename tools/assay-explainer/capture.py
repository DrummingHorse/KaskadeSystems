#!/usr/bin/env python3
"""Film anim.html frame by frame with headless Chromium, then encode it with ffmpeg.

    python3 capture.py preview 2.9 16.4 20.1   # stills at those seconds -> preview_<t>.jpg
    python3 capture.py render                  # frames/f_%04d.jpg at 30 fps, then the .mp4

Needs: pip install playwright && python3 -m playwright install chromium; ffmpeg on PATH.
Set CHROME=/path/to/chrome to film with an installed Chrome instead of Playwright's build.
The fonts come from ../../assay/fonts/, so run this from a checkout of the repo.
"""
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
URL = 'file://' + os.path.join(HERE, 'anim.html') + '#cap'
FPS = 30
OUT = os.path.join(HERE, '..', '..', 'assets', 'assay-office-how-a-check-runs.mp4')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'render'
    launch = {'args': ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--font-render-hinting=none']}
    if os.environ.get('CHROME'):
        launch['executable_path'] = os.environ['CHROME']
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': 1080, 'height': 1080}, device_scale_factor=1)
        page.goto(URL)
        page.wait_for_function("document.fonts.status === 'loaded' && typeof window.seek === 'function'")
        page.wait_for_timeout(300)
        end = page.evaluate('window.END')
        if mode == 'preview':
            for ts in sys.argv[2:]:
                page.evaluate(f'window.seek({float(ts)})')
                page.wait_for_timeout(60)
                page.screenshot(path=os.path.join(HERE, f'preview_{ts}.jpg'), type='jpeg', quality=92)
                print('wrote preview', ts)
            browser.close()
            return
        n = int(round(end * FPS))
        frames = os.path.join(HERE, 'frames')
        os.makedirs(frames, exist_ok=True)
        t0 = time.time()
        for i in range(n):
            page.evaluate(f'window.seek({i / FPS})')
            page.screenshot(path=os.path.join(frames, f'f_{i:04d}.jpg'), type='jpeg', quality=92)
            if i % 150 == 0:
                print(f'{i}/{n} frames, {time.time() - t0:.0f}s', flush=True)
        browser.close()
    tmp = OUT + '.tmp.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(frames, 'f_%04d.jpg'),
                    '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp], check=True)
    os.replace(tmp, OUT)
    print('wrote', os.path.normpath(OUT), f'({n} frames, {end}s)')


if __name__ == '__main__':
    main()
