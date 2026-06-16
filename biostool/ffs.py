"""FFSv2 firmware volumes: поиск томов, свободного места и вставка FFS-файлов.

Используется для добавления DXE-драйверов (например ReBarDxe) в свободное
место DXE-тома без изменения размера тома (free space = 0xFF поглощает файл).
"""
import struct
import uuid

FVH_SIG = b"_FVH"
EFI_FVB2_ERASE_POLARITY = 0x00000800


class Volume:
    __slots__ = ("base", "length", "hdr_len", "attributes", "erase_polarity")

    def __init__(self, base, length, hdr_len, attributes):
        self.base = base
        self.length = length
        self.hdr_len = hdr_len
        self.attributes = attributes
        self.erase_polarity = 1 if (attributes & EFI_FVB2_ERASE_POLARITY) else 0

    @property
    def erase_byte(self):
        return 0xFF if self.erase_polarity else 0x00

    def __repr__(self):
        return f"<FV @0x{self.base:06x} len=0x{self.length:x} pol={self.erase_polarity}>"


def find_volumes(img):
    """Все FFSv2-тома (по сигнатуре _FVH на +0x28)."""
    vols = []
    off = 0
    while True:
        j = img.find(FVH_SIG, off)
        if j < 0:
            break
        base = j - 0x28
        if base >= 0:
            length = struct.unpack_from("<Q", img, base + 0x20)[0]
            attributes = struct.unpack_from("<I", img, base + 0x2C)[0]
            hdr_len = struct.unpack_from("<H", img, base + 0x30)[0]
            if 0 < length <= len(img) - base and 0 < hdr_len < length:
                vols.append(Volume(base, length, hdr_len, attributes))
        off = j + 1
    return vols


def iter_files(img, vol):
    """Итерирует FFS-файлы тома: (offset, guid, ftype, size, state). Стоп на free space."""
    pos = vol.base + vol.hdr_len
    end = vol.base + vol.length
    erase = vol.erase_byte
    while pos + 24 <= end:
        # пустой заголовок (всё erase) -> начало free space
        if all(img[pos + k] == erase for k in range(24)):
            break
        guid = uuid.UUID(bytes_le=bytes(img[pos:pos + 16]))
        ftype = img[pos + 18]
        size = img[pos + 20] | (img[pos + 21] << 8) | (img[pos + 22] << 16)
        state = img[pos + 23]
        if size < 24 or pos + size > end:
            break
        yield (pos, guid, ftype, size, state)
        pos += (size + 7) & ~7  # 8-byte align


def free_space(img, vol):
    """(offset, length) хвостового свободного места (0xFF/0x00) тома."""
    pos = vol.base + vol.hdr_len
    for (off, guid, ftype, size, state) in iter_files(img, vol):
        pos = off + ((size + 7) & ~7)
    end = vol.base + vol.length
    return pos, end - pos


def insert_ffs(img, vol, ffs_bytes, fix_state=True):
    """Вставляет готовый FFS-файл в свободное место тома (размер тома сохраняется).

    Возвращает (новый_образ, offset). Бросает, если не хватает места.
    """
    start, avail = free_space(img, vol)
    need = (len(ffs_bytes) + 7) & ~7
    if need > avail:
        raise ValueError(f"мало места: нужно {need}, свободно {avail}")
    blob = bytearray(ffs_bytes)
    if fix_state:
        # State валидного файла: при polarity=1 биты HEADER/DATA/VALID -> 0,
        # остальное 1 => 0xF8. При polarity=0 — инверсия (0x07).
        blob[23] = 0xF8 if vol.erase_polarity else 0x07
    out = bytearray(img)
    out[start:start + len(blob)] = blob
    # хвост остаётся erase-байтами (уже такие)
    return bytes(out), start
