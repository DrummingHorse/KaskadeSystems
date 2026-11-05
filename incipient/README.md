# Incipient Artistic Ventures — site

The umbrella site for Graham Benjamin Higgins's music, writing and visual work and the ventures around them. Hand-written HTML and CSS, one stylesheet, one script, no build step, no dependencies, nothing loaded from another server.

**Unlisted preview.** Every page carries `noindex`, and `robots.txt` disallows everything at a root deployment. The site is served unlisted from the Kaskade host, behind one unmarked door; nothing links to it, and it is not in any sitemap. The door is announced only when the Operator says so.

Open `index.html` in a browser. Everything is relative, so the folder works from disk or from any static host.

## Pages

| File | Room |
|---|---|
| `index.html` | The house: emblem, the rooms index, the featured player |
| `music.html` | Pure Audio: the listening room (three players), the house of sound, spectra, process |
| `infinite-jazz.html` | Infinite Jazz: Root 001, how a lineage grows, the rules of the room |
| `pages.html` | Pages: screenplays, prose, the desk |
| `gallery.html` | Gallery: six studies, the portrait, the mark |
| `studio.html` | Studio: web design as a service, portfolio, rate card, process |
| `store.html` | Store: releases to own, with a preview cart (nothing is charged) |
| `exchange.html` | Exchange: instrument classifieds with sample listings and a detail view |
| `journal.html` | Journal: dated entries; the one portal to the Kaskade Evolution |
| `about.html` | About: who makes the work, the rooms, where things stand |

`assets/css/incipient.css` holds the whole system (palette, type, components, responsive rules). `assets/js/incipient.js` adds the menu, the audio players, the store's preview cart and the exchange's filters and detail dialog; the pages read fine without it.

## What is real and what is placeholder

- **Real:** titles and descriptions of the music, the screenplays, the novel and the essay; the logo and the aurora portrait; the Bandcamp link; the Evolution link in the journal.
- **Placeholder, labelled on the page:** the six gallery studies (drawn in code for this build; replace the files in `assets/img/gallery/`); the release art in `assets/img/releases/` (drawn in code); every price in the store and on the studio rate card; every exchange listing; the two "proposed" store items (*The Field Archive, volume one* and *Perpetua, vault edition*).
- **Not connected:** store checkout, exchange contact and listing, studio inquiries. Each page says so where the control would be.
- **Not in the repository:** the preview MP3s (`previews/README.txt` lists the expected names).

## Lineage

`archive/artist-site-v0.8/` is the Graham Benjamin Higgins artist site as received on 2026-11-04, byte-for-byte, with hashes in `PROVENANCE.md`. The new `music.html` descends from it. Its logo and portrait are reused; its copy was rewritten for the new house.

## Before the door is announced

1. Upload the preview files.
2. Decide the store's payment provider and replace the preview cart.
3. Replace sample listings with real ones and add a way to reach the seller.
4. Confirm the studio rate card and add an inquiry route.
5. Hang real visual work on the gallery wall.
6. Remove `noindex`, link the door openly, and announce it.
