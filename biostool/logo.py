"""Сборка OEM-логотипа: 4bpp BMP (400x100) под AMI ROM-hole с бюджетом сжатия.

AMI хранит OEM-лого как 4bpp BMP (16-цветная палитра) в LZMA-секции фикс. размера.
Кастомный лого должен (а) совпадать по формату/размеру файла и (б) сжиматься в
ёмкость секции (capacity). Снижаем число цветов, пока LZMA не уложится в бюджет.

Зависимость: Pillow (опционально, только для рендера из растра).
"""
import lzma
import struct

W, H = 400, 100
FILE_SIZE = 118 + (W // 2) * H  # = 20118: 14+40 заголовки + 64 палитра + пиксели


def pack_4bpp_bmp(rgb_image, n_colors):
    """PIL RGB Image (400x100) -> bytes 4bpp BMP (ровно FILE_SIZE)."""
    from PIL import Image
    pal = rgb_image.quantize(colors=n_colors, method=Image.MEDIANCUT, dither=Image.NONE)
    idx = list(pal.getdata())
    palette = (pal.getpalette() or [])[:48]
    palette += [0] * (48 - len(palette))
    rb = W // 2
    off = 118
    out = bytearray(b"BM" + struct.pack("<IHHI", FILE_SIZE, 0, 0, off))
    out += struct.pack("<IiiHHIIiiII", 40, W, H, 1, 4, 0, rb * H, 2835, 2835, 16, 0)
    for i in range(16):
        out += struct.pack("<BBBB", palette[i * 3 + 2], palette[i * 3 + 1], palette[i * 3], 0)
    for row in range(H - 1, -1, -1):
        ln = idx[row * W:(row + 1) * W]
        for c in range(0, W, 2):
            out.append(((ln[c] & 0xF) << 4) | (ln[c + 1] & 0xF))
    return bytes(out)


def _lzma_min(data):
    best = None
    for lc in (0, 1, 2, 3):
        flt = [{"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME,
                "lc": lc, "lp": 0, "pb": 2, "dict_size": 0x1000000}]
        c = len(lzma.compress(data, format=lzma.FORMAT_ALONE, filters=flt))
        best = c if best is None else min(best, c)
    return best


def build_logo(src_png, out_bmp, budget=None, bg=(0, 0, 0)):
    """Рендерит src_png в 400x100 на фоне bg, подбирает макс. число цветов,
    влезающее в budget (байт LZMA). Пишет out_bmp. Возвращает (n_colors, lzma_size).
    """
    from PIL import Image
    logo = Image.open(src_png).convert("RGBA")
    if logo.height > H - 6:
        s = (H - 6) / logo.height
        logo = logo.resize((int(logo.width * s), H - 6), Image.NEAREST)
    cv = Image.new("RGB", (W, H), bg)
    cv.paste(logo, ((W - logo.width) // 2, (H - logo.height) // 2), logo)
    chosen = None
    for nc in (16, 12, 8, 6, 5, 4, 3):
        bmp = pack_4bpp_bmp(cv, nc)
        sz = _lzma_min(bmp)
        if budget is None or sz <= budget:
            chosen = (nc, sz, bmp)
            break
    if chosen is None:
        raise ValueError("даже 3 цвета не влезают в бюджет")
    nc, sz, bmp = chosen
    with open(out_bmp, "wb") as f:
        f.write(bmp)
    return nc, sz
