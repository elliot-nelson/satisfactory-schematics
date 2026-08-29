# satisfactory-schematics

> Pre-rendered images of Satisfactory buildings, for use in your favorite diagramming tools.

![Blender from the rear in Excalidraw Blue](./docs/blender_back.png)

## Disclaimer

This project is completely independent and is not endorsed by, sponsored by, or affiliated with the game Satisfactory or its developers, Coffee Stain Studios. All game titles, logos, and assets belong to their respective copyright and trademark owners.

## Getting started

1. Go to the [Releases page](https://github.com/elliot-nelson/satisfactory-schematics/releases) and select the most recent release.
2. Pick one of the available themes and download the matching ZIP file.
3. Unzip and open the `preview.html` in your local browser to view available images.
4. Drag and drop the SVG file(s) or PNG file(s) into your diagramming tool of choice.

That's it!

## Themes

There are a number of prebaked themes available for you to choose from.

### Blue Schematic

- Simple blue lines with a faded fill, green/red port markers, faint orange collision ticks.
- Drawn at `1m = 20px`.

### Blue Schematic (Clean)

- Same as Blue Schematic, but no port or collision tick annotations.
- Drawn at `1m = 20px`.

### Blue Excalidraw

- Similar to Blue Schematic.
- Lines are drawn slightly thicker and have some randomized jitter, to match Excalidraw's hand-drawn look.
- Drawn at `1m = 20px`.

### Blue Excalidraw (Clean)

- Blue Excalidraw, but no port or collision tick annotations.
- Drawn at `1m = 20px`.

## Scale

The original idea behind this project was to create building schematics I could arrange in Excalidraw (https://excalidraw.com/). Excalidraw uses `20px X 20px` grid markers, so the current themes are rendered at `1m = 20px`. For best results, go to Preferences > Canvas & Shape > Grid step and adjust to 8, then turn on Toggle Grid. Now the major grid markers will represent 1 foundation (8m x 8m) from the top (or 2 wall heights from the side).

Draw.io (https://draw.io/) happens to use `10px X 10px` grids by default, so the same scale works well in Draw.io as well; note that you cannot change the major grid step so 1 foundation will be 2 "squares".

## Annotations: Port markers

For ease of use, input connectors for belts and pipes are marked in red on each building; output connectors are marked in green.

![Foundries and mergers showing port markers in Excalidraw](./docs/excalidraw_foundries_ports.png)

## Annotations: Collision boxes

Each building includes small corner ticks rendered in FICSIT orange, showing where they will collide with other buildings in the game. This is to make it a bit easier to line up e.g. assemblers, where it "looks like" you can tile them next to each other, but the game requires a bit more breathing room.

![Assemblers showing tick markers in draw.io](./docs/drawio_assembler_ticks.png)

## Views

- Most buildings have 5 orthographic views (top, front, back, left, right).
  - Top-down view is oriented with inputs at the bottom, outputs at top.
  - Front view is facing the output port(s).
  - Back view is facing the input port(s).
  - Left view is oriented with inputs on the left, outputs on the right.
  - Right view is oriented with inputs on the right, outputs on the left.

- Some shapes e.g. belts, pipes, architectural elements, only need 2 views.
  - Top-down view (looking head-on at a beam or pipe from above).
  - Front view (looking at a beam or pipe from the side).

## Developer's Guide

Want to make your own theme, or enhance the look of the schematics some other way? Feel free to
clone this repo locally and hack away. The [Developer Guide](DEVELOPER_GUIDE.md) covers setup,
getting the game data, and how the pipeline works.
