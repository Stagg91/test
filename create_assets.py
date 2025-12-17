from PIL import Image, ImageDraw, ImageFont
import os
import random

def create_icon():
    # Create a 256x256 icon
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background Circle (Gold/Yellow for Hectic Wealth)
    draw.ellipse((10, 10, 246, 246), fill="#FFD700", outline="#000000", width=5)

    # Dollar Sign / S for Staggs
    # Draw simple lines
    draw.rectangle((100, 50, 156, 206), fill="#000000") # Vertical
    # S Curves
    draw.arc((80, 50, 176, 128), 90, 270, fill="#000000", width=20)

    img.save("app_icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    img.save("app_icon.png", format="PNG")
    print("app_icon.ico and app_icon.png created.")

def create_splash():
    # Create a 600x400 splash screen
    # "Men in banana suits wearing winnie blues" -> Abstract representation
    img = Image.new('RGB', (600, 400), (20, 20, 30)) # Dark background
    draw = ImageDraw.Draw(img)

    # Draw Banana Suits (Yellow Ovals)
    for i in range(5):
        x = 50 + (i * 110)
        y = 150
        # Suit
        draw.ellipse((x, y, x+80, y+200), fill="#FFE135", outline="black")
        # Face hole
        draw.ellipse((x+25, y+30, x+55, y+60), fill="#FFCCAA")
        # Winnie Blue (Blue Rectangle in hand)
        draw.rectangle((x+60, y+100, x+85, y+130), fill="#0033CC", outline="white")

    # Text "Staggs Hectic Trader"
    # Using simple drawing for text effect
    # S T A G G S
    draw.rectangle((50, 50, 550, 100), fill="#222222")
    # We don't have font load logic robustly, so we rely on the user knowing what it is.
    # We will draw a "Loading..." progress bar that looks like a burning dart

    # Cigarette progress bar
    draw.rectangle((100, 320, 500, 340), fill="white") # Paper
    draw.rectangle((100, 320, 140, 340), fill="orange") # Filter
    draw.ellipse((490, 315, 510, 345), fill="red") # Cherry (Burning end)

    # Smoke
    draw.arc((500, 300, 550, 350), 180, 270, fill="gray", width=2)

    img.save("splash.png")
    print("splash.png created (Hectic style).")

if __name__ == "__main__":
    create_icon()
    create_splash()
