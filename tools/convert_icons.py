import os
from pathlib import Path
import cairosvg
import re

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def modify_svg_content(svg_content, color):
    """Modify SVG content to use specific color"""
    # Usuń currentColor i zastąp konkretnym kolorem
    content = svg_content.replace('fill="currentColor"', f'fill="{color}"')
    return content

def convert_svg_to_png(svg_path, png_path, width, height, color=None):
    """Convert SVG file to PNG with specified dimensions and color"""
    # Ensure output directory exists
    ensure_dir(os.path.dirname(png_path))
    
    # Read SVG content
    with open(svg_path, 'r') as f:
        svg_content = f.read()
    
    if color:
        svg_content = modify_svg_content(svg_content, color)
    
    # Create temporary file with modified SVG
    temp_svg = svg_path.replace('.svg', '_temp.svg')
    with open(temp_svg, 'w') as f:
        f.write(svg_content)
    
    try:
        # Convert to PNG
        cairosvg.svg2png(
            url=temp_svg,
            write_to=png_path,
            output_width=width,
            output_height=height
        )
        print(f"Created {png_path}")
    finally:
        # Clean up temporary file
        if os.path.exists(temp_svg):
            os.remove(temp_svg)

if __name__ == '__main__':
    # Define paths
    resources_dir = Path('src/resources/images')
    trays_dir = resources_dir / 'trays'
    ensure_dir(trays_dir)
    
    # Convert main icon - morski niebieski
    convert_svg_to_png(
        str(resources_dir / 'hard-drive-3-fill.svg'),
        str(resources_dir / 'icon.png'),
        256,
        256,
        color='#00ACC1'  # Morski niebieski
    )
    
    # Convert tray icons with specific colors
    icon_mapping = {
        # Stan aktywny - jasny zielony
        ('refresh-fill.svg', 'backup', '#4CAF50'),
        
        # Błąd - czerwony
        ('error-warning-fill.svg', 'error', '#FF5252'),
        
        # Ostrzeżenie - pomarańczowy
        ('alert-fill.svg', 'warning', '#FFA726'),
        
        # Oczekiwanie - fioletowy
        ('box-3-fill.svg', 'waiting', '#7E57C2')
    }
    
    for source, name, color in icon_mapping:
        convert_svg_to_png(
            str(resources_dir / source),
            str(trays_dir / f'tray_{name}.png'),
            24,
            24,
            color=color
        ) 