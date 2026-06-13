from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = ROOT / "assets" / "brand" / "Icon.png"
ASSET_DIR = ROOT / "assets" / "generated"
RUNTIME_PNG_PATH = ASSET_DIR / "freelaboard.png"
ICO_PATH = ASSET_DIR / "freelaboard.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    if not SOURCE_ICON.exists():
        raise SystemExit(f"Icon source not found: {SOURCE_ICON}")

    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Pillow is required at build time to convert Icon.png into a Windows .ico file."
        ) from exc

    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    with Image.open(SOURCE_ICON) as source:
        icon = source.convert("RGBA")
        icon.thumbnail((256, 256), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        x = (256 - icon.width) // 2
        y = (256 - icon.height) // 2
        canvas.alpha_composite(icon, (x, y))

        canvas.save(RUNTIME_PNG_PATH, "PNG")
        canvas.save(ICO_PATH, format="ICO", sizes=[(size, size) for size in ICON_SIZES])

    print(f"source {SOURCE_ICON}")
    print(f"wrote {RUNTIME_PNG_PATH}")
    print(f"wrote {ICO_PATH}")


if __name__ == "__main__":
    main()
