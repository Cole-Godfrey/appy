# Artwork

`banner.png` (README), `social-preview.png` (1280 × 640, GitHub social preview) and `terminal.png` are screenshots of `scripts/artwork.html` filled with real `shortlist.py` output, so company names reflect the feed on the build date.

Palette: night `#0a0d14`, slate `#131824`, cornflower `#5a9bfc`. Type: [Stack Sans Headline and Stack Sans Text](https://fonts.google.com/specimen/Stack+Sans+Text) (SIL Open Font License), loaded from Google Fonts at build time. Taste direction: The product performs, seed 1090985831; the site in `site/` uses the same system.

Rebuild with Chrome or Chromium installed (set `CHROME` if it is elsewhere):

```sh
python3 scripts/build_assets.py           # live feed
python3 scripts/build_assets.py --sample  # fictional listings
```
