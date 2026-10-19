# Artwork

`banner.svg` uses outlined lettering so it renders consistently on GitHub. `social-preview.png` is 1280 × 640 for GitHub's social preview. `demo.gif` records actual output from `scripts/demo.py`; `demo.png` is its still frame. Every company in the demo is fictional.

The palette is olive `#38450f` on bone `#ecebe7`. Display type is [Imbue](https://fonts.google.com/specimen/Imbue); supporting type is [Albert Sans](https://fonts.google.com/specimen/Albert+Sans), both available under the SIL Open Font License. The rendered assets contain no font files. The terminal uses a local monospace font.

Taste direction: Type and nothing else, seed 787438446. The composition is adapted to a shallow GitHub banner; the full page inspector does not apply to static artwork.

To rebuild, install Pillow and fonttools in an isolated environment, obtain the two fonts from their Google Fonts pages, and run:

```sh
python3 scripts/build_assets.py --imbue /path/to/Imbue.ttf \
  --albert /path/to/AlbertSans.ttf --mono /path/to/monospace.ttf
```
