import os
from PIL import Image, ImageDraw, ImageFont

icons_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'icons')
os.makedirs(icons_dir, exist_ok=True)

def create_icon(size):
    # Create image with dark vinotinto background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    radius = int(size * 0.22)
    bg_color = (136, 19, 55, 255) # #881337 (Vinotinto)
    dark_vinotinto = (59, 7, 18, 255) # #3b0712
    
    # Create a gradient effect
    for i in range(size):
        ratio = i / size
        r = int(dark_vinotinto[0] * (1 - ratio) + bg_color[0] * ratio)
        g = int(dark_vinotinto[1] * (1 - ratio) + bg_color[1] * ratio)
        b = int(dark_vinotinto[2] * (1 - ratio) + bg_color[2] * ratio)
        draw.line([(0, i), (size, i)], fill=(r, g, b, 255))
        
    # Apply rounded corner mask
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([(0, 0), (size, size)], radius=radius, fill=255)
    
    output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask)
    draw_out = ImageDraw.Draw(output)
    
    # Draw stylish inner border
    border_margin = int(size * 0.08)
    draw_out.rounded_rectangle(
        [(border_margin, border_margin), (size - border_margin, size - border_margin)],
        radius=int(radius * 0.7),
        outline=(255, 255, 255, 60),
        width=max(2, int(size * 0.02))
    )
    
    # Draw Monogram Emblem "R"
    font_size = int(size * 0.5)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        
    text = "R"
    bbox = draw_out.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    text_x = (size - text_w) // 2
    text_y = (size - text_h) // 2 - int(size * 0.05)
    
    # Draw text shadow
    draw_out.text((text_x + int(size * 0.015), text_y + int(size * 0.015)), text, font=font, fill=(0, 0, 0, 150))
    # Draw main text
    draw_out.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
    
    # Draw sub-dot indicator
    dot_r = int(size * 0.04)
    dot_x = text_x + text_w + int(size * 0.02)
    dot_y = text_y + text_h - int(size * 0.04)
    draw_out.ellipse([(dot_x, dot_y), (dot_x + dot_r*2, dot_y + dot_r*2)], fill=(244, 63, 94, 255)) # rose accent
    
    return output

# Generate icons of various sizes
sizes = [72, 96, 128, 144, 152, 192, 384, 512]
for s in sizes:
    icon_img = create_icon(s)
    path = os.path.join(icons_dir, f'icon-{s}.png')
    icon_img.save(path, 'PNG')
    print(f"Generated {path}")

# Apple touch icon
apple_icon = create_icon(180)
apple_icon.save(os.path.join(icons_dir, 'apple-touch-icon.png'), 'PNG')
print("Generated apple-touch-icon.png")

print("All PWA icons generated successfully!")
