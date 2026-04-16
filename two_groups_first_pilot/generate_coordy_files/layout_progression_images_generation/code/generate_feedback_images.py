from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Configuration
# ============================================================

ASSETS_DIR = Path("../images")
OUTPUT_DIR = Path("./generated_feedback_images")

GREEN_MONEY = ASSETS_DIR / "green_money.png"
YELLOW_MONEY = ASSETS_DIR / "yellow_money.jpg"
JIGSAW_FITTED = ASSETS_DIR / "jigsaw_fitted.png"
JIGSAW_UNFITTED = ASSETS_DIR / "jigsaw_unfitted.jpg"

# Canvas size
WIDTH = 900
HEIGHT = 1300

# Colors
GREEN = (28, 130, 62, 255)
BLACK = (20, 20, 20, 255)

# Font sizes
TOP_FONT_SIZE = 68
MID_FONT_SIZE = 74
BOTTOM_FONT_SIZE = 64

# Image sizes inside each card
JIGSAW_BOX = (260, 260)
MONEY_BOX = (170, 170)

# Vertical spacing
TOP_MARGIN = 90
GAP_SMALL = 40
GAP_MEDIUM = 65
GAP_LARGE = 85

# Output names
PNG_DIR = OUTPUT_DIR / "png"
WEBP_DIR = OUTPUT_DIR / "webp"


# ============================================================
# Helpers
# ============================================================

def load_font(size: int) -> ImageFont.FreeTypeFont:
    """
    Try a few common fonts. Falls back to PIL default if none are found.
    """
    candidates = [
        "DejaVuSans-Bold.ttf",
        "Arial Bold.ttf",
        "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def crop_white_background(img: Image.Image, threshold: int = 245) -> Image.Image:
    """
    Converts near-white background to transparency by using brightness threshold.
    Useful if the source jpg icons have white backgrounds.
    """
    img = img.convert("RGBA")
    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                pixels[x, y] = (255, 255, 255, 0)

    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def contain(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    """
    Resize image to fit inside box, preserving aspect ratio.
    """
    img = img.copy()
    img.thumbnail(box, Image.LANCZOS)

    canvas = Image.new("RGBA", box, (255, 255, 255, 0))
    x = (box[0] - img.width) // 2
    y = (box[1] - img.height) // 2
    canvas.paste(img, (x, y), img)
    return canvas


def get_text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    return draw.textbbox((0, 0), text, font=font)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    bbox = get_text_bbox(draw, text, font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered_text(draw, y, text, font, fill):
    w, h = text_size(draw, text, font)
    x = (WIDTH - w) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + h


def wrap_text_to_width(draw, text, font, max_width):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word
        w, _ = text_size(draw, test, font)
        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def draw_centered_multiline_text(draw, y, text, font, fill, max_width, line_spacing=12):
    lines = wrap_text_to_width(draw, text, font, max_width)
    total_height = 0
    sizes = []

    for line in lines:
        w, h = text_size(draw, line, font)
        sizes.append((line, w, h))
        total_height += h

    total_height += line_spacing * (len(lines) - 1)

    current_y = y
    for line, w, h in sizes:
        x = (WIDTH - w) // 2
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += h + line_spacing

    return current_y


def paste_centered(canvas: Image.Image, img: Image.Image, y: int):
    x = (WIDTH - img.width) // 2
    canvas.paste(img, (x, y), img)
    return y + img.height


def paste_right_of_text(canvas, draw, y, text, font, icon_img, text_fill, gap=24):
    text_w, text_h = text_size(draw, text, font)
    total_w = text_w + gap + icon_img.width
    start_x = (WIDTH - total_w) // 2

    draw.text((start_x, y), text, font=font, fill=text_fill)

    icon_y = y + max(0, (text_h - icon_img.height) // 2)
    icon_x = start_x + text_w + gap
    canvas.paste(icon_img, (icon_x, icon_y), icon_img)

    return y + max(text_h, icon_img.height)


def point_text(x: int) -> str:
    return f"You get {x} point" if x == 1 else f"You get {x} points"


# ============================================================
# Asset loading
# ============================================================

def load_assets():
    required = [GREEN_MONEY, YELLOW_MONEY, JIGSAW_FITTED, JIGSAW_UNFITTED]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required asset files:\n" + "\n".join(missing)
        )

    assets = {
        "green_money": contain(crop_white_background(Image.open(GREEN_MONEY)), MONEY_BOX),
        "yellow_money": contain(crop_white_background(Image.open(YELLOW_MONEY)), MONEY_BOX),
        "jigsaw_fitted": contain(crop_white_background(Image.open(JIGSAW_FITTED)), JIGSAW_BOX),
        "jigsaw_unfitted": contain(crop_white_background(Image.open(JIGSAW_UNFITTED)), JIGSAW_BOX),
    }
    return assets


# ============================================================
# Main generator
# ============================================================

def generate_one_image(you: int, partner: int, assets, fonts):
    success = (you + partner) <= 10

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    top_font = fonts["top"]
    mid_font = fonts["mid"]
    bottom_font = fonts["bottom"]

    top_text = f"You = {you}, Partner = {partner}"

    if success:
        middle_text = "You coordinated!"
        bottom_text = point_text(you)
        jigsaw = assets["jigsaw_fitted"]
        money = assets["yellow_money"]
    else:
        middle_text = "You went over 10!"
        bottom_text = "No worries, you get your default reward"
        jigsaw = assets["jigsaw_unfitted"]
        money = assets["green_money"]

    y = TOP_MARGIN

    # Top line
    y = draw_centered_text(draw, y, top_text, top_font, GREEN)
    y += GAP_LARGE

    # Middle line
    y = draw_centered_text(draw, y, middle_text, mid_font, BLACK)
    y += GAP_MEDIUM

    # Jigsaw
    y = paste_centered(canvas, jigsaw, y)
    y += GAP_LARGE

    # Bottom text centered
    max_text_width = int(WIDTH * 0.78)
    y = draw_centered_multiline_text(
        draw=draw,
        y=y,
        text=bottom_text,
        font=bottom_font,
        fill=GREEN,
        max_width=max_text_width,
        line_spacing=12,
    )

    # Money centered below text
    y += 28
    y = paste_centered(canvas, money, y)

    return canvas


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    WEBP_DIR.mkdir(parents=True, exist_ok=True)

    assets = load_assets()
    fonts = {
        "top": load_font(TOP_FONT_SIZE),
        "mid": load_font(MID_FONT_SIZE),
        "bottom": load_font(BOTTOM_FONT_SIZE),
    }

    count = 0
    for you in range(1, 10):
        for partner in range(1, 10):
            img = generate_one_image(you, partner, assets, fonts)

            base_name = f"feedback_you_{you}_partner_{partner}"
            png_path = PNG_DIR / f"{base_name}.png"
            webp_path = WEBP_DIR / f"{base_name}.webp"

            img.save(png_path, format="PNG")
            img.save(webp_path, format="WEBP", lossless=True)

            count += 1

    print(f"Done. Generated {count} image pairs.")
    print(f"PNG files:  {PNG_DIR.resolve()}")
    print(f"WEBP files: {WEBP_DIR.resolve()}")


if __name__ == "__main__":
    main()