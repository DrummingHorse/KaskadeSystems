# Assay Office explainer video

Reproducible renderer for `assets/assay-office-how-a-check-runs.mp4`: a 28.7-second,
1080×1080, 30 fps H.264 clip that shows how a pilot check runs, for posting on X.

**Implemented:** `anim.html` is a self-contained animation in the site's locked visual
language (Fraunces + IBM Plex Mono from `assay/fonts/`, amber on navy, spectrum rays,
corner brackets). `capture.py` films it frame by frame with headless Chromium and
encodes the frames with ffmpeg.

**Illustration only:** the clip replays the fictional example DEMO-0417 from the Assay
page (five fictional firms, three gold, two pyrite, verdict "fails the spec") and says
so in its caption. It is not a live check and shows no customer result. The pilot claims
in the closing frame (free design-partner pilots, lead lists up to 25 entries, reports up
to 15 cited claims, scope agreed before files are shared, findings in about three
business days) are the same proposals the Assay page makes.

## Re-render

```
pip install playwright && python3 -m playwright install chromium   # once
python3 tools/assay-explainer/capture.py preview 2.9 16.4 20.1      # look at a few moments first
python3 tools/assay-explainer/capture.py render                     # frames -> assets/...mp4
```

Copy, firm names, check names and timings live in the data block at the top of the
script in `anim.html`; the scene anchors are derived from the scan, so changing the
number of entries or checks reflows the later scenes. Open `anim.html` in a browser to
watch it loop; the `#cap` hash disables the loop so the capture script can seek.
