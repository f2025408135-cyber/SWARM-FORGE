# Swarm-Forge — Logo Assets

Six inward-pointing chevrons arranged in hexagonal symmetry around a central node.

- **Swarm** — six independent chevrons, each an autonomous agent
- **Forge** — the cross-section of hex-stock steel, of bee comb, of an anvil flat
- **Compilation** — every chevron converges on a single central node (the deterministic compiled DAG)
- **Zero-trust** — nothing reaches the centre without passing through the negative space between gates

## Files

| File | Purpose |
|---|---|
| `swarm-forge-mark.svg` | Primary mark, uses `currentColor` so it adapts to surrounding theme |
| `swarm-forge-mark-black.svg` | Hardcoded black `#0E0E12` — for light backgrounds |
| `swarm-forge-mark-white.svg` | Hardcoded white `#FFFFFF` — for dark backgrounds |
| `swarm-forge-mark-ember.svg` | Black chevrons with ember-orange `#E6603A` central node — active/firing state |
| `swarm-forge-wordmark.svg` | Mark + lowercase `swarm-forge` text, horizontal layout |

## Brand Colours

| Role | Hex | Use |
|---|---|---|
| Iron Black | `#0E0E12` | Primary mark on light surfaces |
| Pure White | `#FFFFFF` | Primary mark on dark surfaces |
| Ember Orange | `#E6603A` | Active-state accent only — central node when the forge is "firing" |
| Iron Blue | `#1A2A40` | Enterprise / institutional skin (use sparingly) |

## Converting SVG to PNG

For social media, video editors that don't ingest SVG (CapCut, mobile apps), or static thumbnails:

**Inkscape (recommended, free, lossless):**
```bash
inkscape -w 1024 -h 1024 swarm-forge-mark-black.svg -o swarm-forge-mark-1024.png
```

**ImageMagick:**
```bash
magick -background none -density 300 swarm-forge-mark-black.svg -resize 1024x1024 swarm-forge-mark-1024.png
```

**Browser (no install required):** open the SVG in any modern browser, screenshot at high zoom, crop the result.

**Online (zero install):** drop the SVG into [convertio.co/svg-png](https://convertio.co/svg-png/) or [cloudconvert.com](https://cloudconvert.com/svg-to-png).

## Usage Rules

- Do not stretch, skew, or recolour the chevrons individually. They are a single radially symmetric unit.
- Maintain a clear-space margin of at least one chevron's width around the mark.
- Minimum size: 24px tall (the central node disappears below this).
- The ember variant signals an active state. Do not use it for static branding contexts.
