from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # Create a 256x256 icon
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a simple crypto-like logo (Circle with 'J')
    draw.ellipse((20, 20, 236, 236), fill="#1a1a1a", outline="#00ff00", width=10)

    # Draw 'J'
    # We don't have many fonts, so just draw lines or use default
    # Simple J shape
    draw.rectangle((110, 60, 146, 180), fill="#00ff00")
    draw.pieslice((80, 140, 146, 200), 0, 180, fill="#00ff00")

    img.save("app_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.save("app_icon.png", format="PNG") # For webview usage
    print("app_icon.ico and app_icon.png created.")

def create_splash():
    # Create a 600x400 splash screen
    img = Image.new('RGB', (600, 400), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    # Background pattern (optional grid)
    for x in range(0, 600, 40):
        draw.line((x, 0, x, 400), fill=(50, 50, 50))
    for y in range(0, 400, 40):
        draw.line((0, y, 600, y), fill=(50, 50, 50))

    # Text "JulesBot"
    # Loading fonts is tricky without external files, using default
    # Drawing large pixelated text or just simple lines?
    # Let's just center some text roughly

    # Mocking text by drawing shapes or relying on default font (very small)
    # Better to just have a big green circle
    draw.ellipse((250, 100, 350, 200), fill="#00ff00")

    # "Loading..." bar
    draw.rectangle((100, 300, 500, 320), outline="#ffffff")
    draw.rectangle((105, 305, 300, 315), fill="#00ff00") # Partial fill

    img.save("splash.png")
    print("splash.png created.")

if __name__ == "__main__":
    create_icon()
    create_splash()
