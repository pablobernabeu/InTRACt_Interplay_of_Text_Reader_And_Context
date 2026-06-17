# Conceptual framework figure (Figure 1)

The figure embedded in the preregistration (`mindmap/mindmap.png`, shown as
Figure 1) is defined as code in **`mindmap.mmd`**, a [Mermaid](https://mermaid.js.org)
flowchart. To change the figure, edit that file and regenerate the PNG — no
hand-editing of the image, and no HTML/screenshot step.

## Edit and regenerate

1. Edit `mindmap.mmd` (plain-text Mermaid; node labels, colours and grouping are
   all readable inline).
2. Install the renderer once:

   ```sh
   npm install
   ```

   This installs `@mermaid-js/mermaid-cli`, which renders Mermaid to PNG with a
   bundled headless browser.
3. Regenerate the figure:

   ```sh
   npx mmdc -i mindmap.mmd -o ../mindmap.png -c mermaid-config.json -p puppeteer-config.json -b white -s 3
   ```

## Files

- `mindmap.mmd` — the diagram source (edit this).
- `mermaid-config.json` — theme, fonts and flowchart layout/spacing.
- `puppeteer-config.json` — passes `--no-sandbox` to the headless browser.

`-s 3` renders at 3× for a crisp image; `-b white` sets a white background.
