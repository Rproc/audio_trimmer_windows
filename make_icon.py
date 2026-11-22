from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


def generate_icon(out_path: Path) -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo arredondado escuro
    margin = 10
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=48,
        fill=(11, 17, 32, 255),
        outline=(30, 41, 59, 255),
        width=6,
    )

    # Faixa de destaque da seleção no centro
    sel_left = 68
    sel_right = 188
    draw.rectangle([sel_left, 54, sel_right, 202], fill=(56, 189, 248, 36))

    # Barras de forma de onda
    heights = [28, 46, 74, 118, 92, 138, 108, 134, 84, 58, 36]
    bar_w = 10
    gap = 8
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    start_x = (size - total_w) // 2
    mid_y = size // 2

    for i, h in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        x1 = x0 + bar_w
        y0 = mid_y - h // 2
        y1 = mid_y + h // 2
        in_sel = sel_left <= (x0 + x1) / 2 <= sel_right
        color = (56, 189, 248, 255) if in_sel else (71, 85, 105, 255)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=5, fill=color)

    # Marcadores IN (verde) e OUT (âmbar)
    draw.rounded_rectangle([sel_left - 4, 46, sel_left + 4, 210], radius=4, fill=(34, 197, 94, 255))
    draw.rounded_rectangle([sel_right - 4, 46, sel_right + 4, 210], radius=4, fill=(245, 158, 11, 255))

    # Abas superiores dos marcadores
    draw.rounded_rectangle([sel_left - 4, 42, sel_left + 22, 60], radius=4, fill=(34, 197, 94, 255))
    draw.rounded_rectangle([sel_right - 22, 42, sel_right + 4, 60], radius=4, fill=(245, 158, 11, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        out_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )


if __name__ == "__main__":
    generate_icon(Path(__file__).parent / "app_icon.ico")
    print("Icon generated.")
