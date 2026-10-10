import os
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

def process_image_to_webp(image_field, max_size=(1024, 1024), quality=80):
    """
    Takes an ImageField (Django), resizes it if it exceeds max_size,
    converts it to WebP format, and updates the image_field with the new content.
    Returns the new filename.
    """
    if not image_field:
        return None

    try:
        # Open the image using Pillow
        img = Image.open(image_field)
        
        # Convert image to RGB if it has an alpha channel or is not in RGB/RGBA
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # Resize image maintaining aspect ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save image to a BytesIO object
        output = BytesIO()
        img.save(output, format='WEBP', quality=quality)
        output.seek(0)

        # Create new filename
        original_name = os.path.basename(image_field.name)
        name_without_ext = os.path.splitext(original_name)[0]
        new_filename = f"{name_without_ext}.webp"

        # Save to the image field
        image_field.save(new_filename, ContentFile(output.read()), save=False)
        return new_filename
    except Exception as e:
        print(f"Error processing image to webp: {e}")
        return None
