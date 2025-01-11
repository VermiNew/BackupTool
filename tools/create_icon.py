from PIL import Image, ImageDraw
from pathlib import Path

def create_icon(size=256):
    # Create new image with transparency
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Calculate dimensions
    padding = size // 8
    inner_size = size - (2 * padding)
    center = size // 2
    radius = inner_size // 3
    
    # Draw rounded rectangle background
    draw.rounded_rectangle(
        [padding, padding, size-padding, size-padding],
        radius=size//10,
        fill=(52, 152, 219)  # #3498db (niebieski)
    )
    
    # Draw circle
    draw.ellipse(
        [center-radius, center-radius, center+radius, center+radius],
        outline='white',
        width=size//16
    )
    
    # Draw cross (plus sign)
    line_length = radius
    line_width = size // 16
    
    # Horizontal line
    draw.line(
        [center-line_length, center, center+line_length, center],
        fill='white',
        width=line_width
    )
    
    # Vertical line
    draw.line(
        [center, center-line_length, center, center+line_length],
        fill='white',
        width=line_width
    )
    
    # Save icon
    icon_path = Path(__file__).parent.parent / 'src' / 'resources' / 'icon.png'
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(icon_path)

if __name__ == '__main__':
    create_icon() 