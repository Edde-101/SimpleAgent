# svg-draw

**Author**: lijy2015 (via openclaw)
**Description**: Generate and convert SVG graphics to PNG without external GUI libraries. Ideal for programmatic diagrams, icons, avatars, and technical illustrations.

## Usage
- Input: Valid SVG source (string or file path)
- Output: `.svg` file (optional), `.png` file (if conversion requested)
- Tools used: `write_file`, `shell` (for cairosvg), `read_file`

## Requirements
- `cairosvg` Python package (install via `pip install cairosvg`)
- System fonts (for text rendering)

## Templates
- `assets/blank.svg`: Minimal SVG template with viewBox="0 0 200 200"

## Example Workflow
1. Compose SVG string (e.g., `<svg>...</svg>`)
2. Call `draw.py --svg "<svg>..." --output diagram.svg`
3. Call `draw.py --convert diagram.svg --output diagram.png`