"""Gera o ícone do aplicativo: nota fiscal com selo de validação.

Uso: python ferramentas/gerar_icone.py   (precisa de Pillow)
Saída: assets/icone.png (512 px) e assets/icone.ico (16 a 256 px)
"""

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
S = 1024  # desenha grande e reduz, para bordas suaves

AZUL = (30, 90, 168, 255)
BRANCO = (255, 255, 255, 255)
CINZA = (176, 190, 207, 255)
AZUL_CLARO = (120, 160, 214, 255)
VERDE = (34, 160, 90, 255)


def desenhar() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # fundo: quadrado arredondado azul
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=200, fill=AZUL)

    # folha da nota com canto dobrado
    x0, y0, x1, y1, dobra = 250, 170, 730, 850, 130
    d.polygon([(x0, y0), (x1 - dobra, y0), (x1, y0 + dobra), (x1, y1), (x0, y1)], fill=BRANCO)
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)], fill=CINZA)

    # cabeçalho e linhas de itens
    d.rounded_rectangle((x0 + 60, y0 + 70, x0 + 260, y0 + 120), radius=20, fill=AZUL_CLARO)
    for i, largura in enumerate((360, 300, 360, 220)):
        y = y0 + 190 + i * 90
        d.rounded_rectangle((x0 + 60, y, x0 + 60 + largura, y + 34), radius=17, fill=CINZA)

    # selo verde de validação
    cx, cy, r = 700, 730, 190
    d.ellipse((cx - r - 24, cy - r - 24, cx + r + 24, cy + r + 24), fill=AZUL)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=VERDE)
    d.line([(cx - 95, cy + 5), (cx - 25, cy + 80), (cx + 105, cy - 70)], fill=BRANCO, width=58, joint="curve")
    for px, py in ((cx - 95, cy + 5), (cx + 105, cy - 70)):
        d.ellipse((px - 29, py - 29, px + 29, py + 29), fill=BRANCO)
    return img


def main() -> None:
    destino = RAIZ / "assets"
    destino.mkdir(exist_ok=True)
    img = desenhar()
    img.resize((512, 512), Image.LANCZOS).save(destino / "icone.png")
    img.resize((256, 256), Image.LANCZOS).save(
        destino / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"Ícone gerado em {destino}")


if __name__ == "__main__":
    main()
