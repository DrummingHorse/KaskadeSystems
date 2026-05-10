KASKADE / EVOLUTION — DROP-IN BUNDLE
=====================================

These files are ADDITIONS to your existing kaskade.systems repo.
Do NOT replace your root index.html.

File tree (merge into your repo, preserving paths):

  evolution/index.html          — the spine page
  evolution/001/index.html      — Loop 001
  styles/evolution.css          — section stylesheet
  fonts/Fraunces.woff2          — Fraunces variable (wght axis)
  fonts/IBMPlexMono-Regular.woff2
  fonts/IBMPlexMono-Medium.woff2

Notes:

- If you already have a /fonts/ directory with Fraunces or Plex Mono,
  check the filenames in styles/evolution.css @font-face blocks and
  adjust to match what you've got. Keep the names you already use.

- If you have an existing /styles/ directory, just drop evolution.css
  alongside whatever's already there. It does not conflict with other
  stylesheets — only pages under /evolution/ will load it.

- The Fraunces in this bundle is the wght-axis variable from fontsource.
  If you want the full SOFT + WONK variable axes, replace Fraunces.woff2
  with the file from github.com/undercase/Fraunces/tree/main/fonts/variable
  and update the @font-face filename in styles/evolution.css to match.

Local preview before pushing:

  cd /path/to/your/repo
  python3 -m http.server 8000
  open http://localhost:8000/evolution/

After push, the section is live at:

  https://kaskade.systems/evolution/
  https://kaskade.systems/evolution/001/

— Built May 2026
