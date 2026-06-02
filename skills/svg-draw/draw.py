#!/usr/bin/env python3
"""
svg-draw: Lightweight SVG generator & converter.
Usage:
  python draw.py --svg '<svg>...</svg>' --output out.svg
  python draw.py --convert in.svg --output out.png
"""
import sys
import os
import argparse
import subprocess

def write_svg(svg_content, output_path):
    with open(output_path, 'w') as f:
        f.write(svg_content)
    print(f'✓ Wrote SVG to {output_path}')

def convert_svg_to_png(svg_path, png_path):
    try:
        subprocess.run(['cairosvg', svg_path, '-o', png_path], check=True)
        print(f'✓ Converted {svg_path} → {png_path}')
    except FileNotFoundError:
        print('⚠ cairosvg not found. Install with: pip install cairosvg')
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f'✗ Conversion failed: {e}')
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='SVG draw & convert tool')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--svg', type=str, help='SVG content string')
    group.add_argument('--convert', type=str, help='Input SVG file path to convert')
    parser.add_argument('--output', type=str, required=True, help='Output file path (.svg or .png)')
    
    args = parser.parse_args()
    
    if args.svg:
        if not args.output.endswith('.svg'):
            print('Error: --output must end with .svg when using --svg')
            sys.exit(1)
        write_svg(args.svg, args.output)
    elif args.convert:
        if not args.output.endswith('.png'):
            print('Error: --output must end with .png when using --convert')
            sys.exit(1)
        convert_svg_to_png(args.convert, args.output)

def generate_flowchart(data, theme='modern'):
    # Validate input
    if 'nodes' not in data or not isinstance(data['nodes'], list):
        raise ValueError('Flowchart JSON must contain "nodes" array')
    
    # Layout: vertical timeline (y = 120 + i * 130), centered x=200..700
    width, height = 900, 850
    margin_top = 90
    node_height = 100
    gap_y = 130
    
    # Build SVG header
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif">
  <style>
    :root {{
      --primary: #4F46E5;
      --success: #10B981;
      --warn: #F59E0B;
      --text: #1E293B;
      --border: #E2E8F0;
      --bg: #F8FAFC;
      --radius: 12px;
      --shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }}
    .card {{ fill: white; rx: var(--radius); ry: var(--radius); filter: url(#shadow); }}
    .icon {{ font-size: 24px; font-weight: bold; }}
    .title {{ font-size: 18px; font-weight: 700; fill: var(--text); }}
    .desc {{ font-size: 14px; fill: #475569; line-height: 1.5; }}
    .badge {{ font-size: 12px; font-weight: 600; px: 8px; py: 3px; rx: 4px; ry: 4px; }}
    .badge-success {{ fill: #ECFDF5; color: var(--success); }}
    .badge-warn {{ fill: #FFFBEB; color: var(--warn); }}
    .connector {{ stroke: var(--border); stroke-width: 2; stroke-linecap: round; }}
    .label {{ font-size: 13px; fill: #64748B; font-weight: 500; }}
    #shadow {{ filter: drop-shadow(0 4px 6px rgba(0,0,0,0.05)); }}
  </style>
  <defs>
    <filter id="shadow">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.05"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="100%" height="100%" fill="var(--bg)" />

  <!-- Title Banner -->
  <rect x="0" y="0" width="{width}" height="90" fill="var(--primary)" />
  <text x="{width//2}" y="55" text-anchor="middle" class="title" fill="white">Agent Skill Execution Flow</text>
  <text x="{width//2}" y="78" text-anchor="middle" class="label" fill="rgba(255,255,255,0.9)">How agents autonomously discover, load, validate, and run skills</text>

  <!-- Vertical timeline -->
  <line x1="120" y1="110" x2="120" y2="{height-70}" stroke="var(--border)" stroke-width="2" stroke-dasharray="4,4"/>
'''
    
    # Render nodes
    for i, node in enumerate(data['nodes']):
        y = margin_top + 120 + i * gap_y
        icon = node.get('icon', '⚙️')
        title = node.get('title', 'Node')
        desc = node.get('desc', '')
        status = node.get('status', 'success')
        
        badge_class = 'badge-success' if status == 'success' else 'badge-warn' if status == 'warn' else 'badge-error'
        badge_text = '✅ Ready' if status == 'success' else '⚠️ Not found?' if status == 'warn' else '❌ Missing'
        
        svg += f'''
  <!-- Node {i+1}: {title} -->
  <g transform="translate(0,{y-120})">
    <rect x="120" y="0" width="660" height="100" class="card"/>
    <text x="160" y="40" class="icon" fill="var(--primary)">{icon}</text>
    <text x="200" y="40" class="title">{title}</text>
    <text x="200" y="68" class="desc">{desc}</text>
    <rect x="600" y="20" width="60" height="24" rx="4" ry="4" class="badge {badge_class}"/>
    <text x="630" y="38" text-anchor="middle" dominant-baseline="middle" class="label">{badge_text}</text>
  </g>
  <!-- Connector {i+1} -->
  <line x1="120" y1="{y-20}" x2="120" y2="{y+10}" class="connector"/>'''
    
    # Fallback path (if warn node exists)
    has_warn = any(n.get('status') == 'warn' for n in data['nodes'])
    if has_warn:
        svg += '''
  <!-- Fallback Path -->
  <path d="M 220 330 Q 300 420 220 510" fill="none" stroke="var(--warn)" stroke-width="2" stroke-dasharray="4,2" marker-end="url(#arrowhead)"/>
  <text x="225" y="425" class="label" fill="var(--warn)" font-weight="600">⚠️ Not found? → Install</text>'''
    
    # Footer
    svg += f'''
  <!-- Footer -->
  <rect x="0" y="{height-70}" width="{width}" height="70" fill="white" stroke="var(--border)" stroke-width="1"/>
  <text x="{width//2}" y="{height-35}" text-anchor="middle" class="label" fill="var(--text)">Built with svg-draw-pro v1.0 • Flowchart DSL</text>
</svg>'''
    
    return svg

def main():
    parser = argparse.ArgumentParser(description='SVG draw & convert tool')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--svg', type=str, help='SVG content string')
    group.add_argument('--flow', type=str, help='JSON flowchart definition: {"nodes":[{{"title":"User Request","desc":"...","icon":"💬","status":"success"}},...]}}')
    group.add_argument('--convert', type=str, help='Input SVG file path to convert')
    parser.add_argument('--output', type=str, required=True, help='Output file path (.svg or .png)')
    parser.add_argument('--theme', type=str, default='modern', help='Theme name (default: modern)')
    
    args = parser.parse_args()
    
    if args.svg:
        if not args.output.endswith('.svg'):
            print('Error: --output must end with .svg when using --svg')
            sys.exit(1)
        write_svg(args.svg, args.output)
    elif args.flow:
        if not args.output.endswith('.svg'):
            print('Error: --output must end with .svg when using --flow')
            sys.exit(1)
        try:
            data = json.loads(args.flow)
            svg_content = generate_flowchart(data, theme=args.theme)
            write_svg(svg_content, args.output)
        except json.JSONDecodeError as e:
            print(f'✗ Invalid JSON in --flow: {e}')
            sys.exit(1)
        except Exception as e:
            print(f'✗ Flowchart generation failed: {e}')
            sys.exit(1)
    elif args.convert:
        if not args.output.endswith('.png'):
            print('Error: --output must end with .png when using --convert')
            sys.exit(1)
        convert_svg_to_png(args.convert, args.output)

if __name__ == '__main__':
    main()