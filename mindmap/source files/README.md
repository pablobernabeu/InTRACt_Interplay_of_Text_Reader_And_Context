# Conceptual framework figure (Figure 1)

The figure embedded in the preregistration (`mindmap/mindmap.png`, shown as Figure 1) is defined
as code in **`mindmap.svg`** — a hand-authored SVG. To change the figure, edit that plain-text
file and regenerate the PNG; no hand-editing of the image.

The SVG gives full control over layout, typography and colour, so the figure can be made
publication-grade while remaining editable and diff-friendly. It is rasterised to PNG with the
Chromium that ships with `puppeteer`, so no system image tools (Inkscape, librsvg, ImageMagick)
are required.

## Edit and regenerate

1. Edit `mindmap.svg` (nodes, labels, colours and the H1–H5 hypothesis arrows are all readable
   inline; coordinates are commented by section).
2. Install the renderer once (downloads a headless Chromium):

   ```sh
   npm install
   ```

3. Regenerate the figure:

   ```sh
   npm run render
   ```

   This runs `node render_svg.js mindmap.svg ../mindmap.png 3`, writing `../mindmap.png` at 3×
   the SVG's intrinsic size for a crisp print raster. Use a different scale or output path by
   calling the script directly, e.g. `node render_svg.js mindmap.svg preview.png 2`.

## Files

- `mindmap.svg` — the figure source (edit this).
- `render_svg.js` — rasterises an SVG to PNG via the puppeteer-bundled Chromium.
- `package.json` — declares the single `puppeteer` dependency and the `render` script.
