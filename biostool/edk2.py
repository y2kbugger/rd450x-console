"""EDK2/UEFI firmware primitives: GUID-defined LZMA sections (AMI Aptio).

Этот образ (RD450X, AMI Aptio V) сжимает каждый DXE-модуль отдельной
GUID-defined LZMA-секцией. Формат полезной нагрузки = LZMA "alone" (.lzma):
  props(1) + dict_size(4 LE) + uncompressed_size(8 LE) + поток.
КРИТИЧНО: EDK2-декодер читает РЕАЛЬНЫЙ размер из заголовка (а не EOS-маркер),
поэтому при рекомпрессии поле размера нужно проставлять вручную — иначе UEFIExtract
и сам BIOS не распакуют секцию (python пишет 0xFFFF..FF = unknown).
"""
import lzma
import struct
import uuid

# GUID GUID-defined секции, которым AMI обёрнуты LZMA-модули в этом образе,
# плюс стандартный Tiano LZMA GUID — пробуем оба.
SECTION_GUIDS = [
    uuid.UUID("EE4E5898-3914-4259-9D6E-DC7BD79403CF").bytes_le,  # AMI (этот образ)
    uuid.UUID("A31280AD-481E-41B6-95E8-127F4C984779").bytes_le,  # Tiano LZMA
]
SECTION_TYPE_GUID_DEFINED = 0x02
HDR_LEN = 24  # 3(size)+1(type)+16(guid)+2(DataOffset)+2(Attributes)


class Section:
    __slots__ = ("offset", "size", "data_offset", "guid")

    def __init__(self, offset, size, data_offset, guid):
        self.offset = offset          # начало секции в образе
        self.size = size              # полный размер секции
        self.data_offset = data_offset
        self.guid = guid

    @property
    def payload_slice(self):
        return slice(self.offset + self.data_offset, self.offset + self.size)

    @property
    def capacity(self):
        """Сколько байт доступно под LZMA-данные (для in-place рекомпрессии)."""
        return self.size - self.data_offset

    def __repr__(self):
        return f"<Section @0x{self.offset:06x} size={self.size} cap={self.capacity}>"


def iter_sections(img):
    """Итерирует все GUID-defined LZMA-секции (по известным GUID)."""
    for guid in SECTION_GUIDS:
        off = 0
        while True:
            j = img.find(guid, off)
            if j < 0:
                break
            s = j - 4
            if s >= 0 and img[s + 3] == SECTION_TYPE_GUID_DEFINED:
                size = img[s] | (img[s + 1] << 8) | (img[s + 2] << 16)
                data_off = struct.unpack_from("<H", img, j + 16)[0]
                if data_off == HDR_LEN and 0 < size <= len(img) - s:
                    yield Section(s, size, data_off, guid)
            off = j + 1


def decompress(img, sec):
    """Декомпрессирует секцию (None если не LZMA-alone).

    Читает ровно uncompressed_size байт из заголовка и останавливается, игнорируя
    хвостовой паддинг — как EDK2-декодер (python иначе ищет EOS и падает на нулях).
    """
    payload = bytes(img[sec.payload_slice])
    if len(payload) < 13:
        return None
    usize = struct.unpack_from("<Q", payload, 5)[0]
    if usize == 0 or usize > (1 << 32):  # неизвестный/мусорный размер
        try:
            return lzma.decompress(payload, format=lzma.FORMAT_ALONE)
        except Exception:
            return None
    try:
        d = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        out = d.decompress(payload, max_length=usize)
        return out if len(out) == usize else None
    except Exception:
        return None


def compress(data, lc=0, lp=0, pb=2, dict_size=0x1000000):
    """EDK2-совместимый LZMA-alone: с реальным размером в заголовке."""
    flt = [{"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME,
            "lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size}]
    comp = bytearray(lzma.compress(data, format=lzma.FORMAT_ALONE, filters=flt))
    comp[5:13] = struct.pack("<Q", len(data))  # EDK2 читает размер отсюда
    return bytes(comp)


def compress_best(data, capacity):
    """Жмёт data, перебирая lc, чтобы влезть в capacity. Возвращает (bytes,lc) или None."""
    for lc in (0, 1, 2, 3):
        comp = compress(data, lc=lc)
        if len(comp) <= capacity:
            return comp, lc
    return None


def repack_inplace(img, sec, new_decompressed):
    """Пересобирает секцию новым содержимым in-place (размер секции сохраняется).

    Возвращает (новый_образ, lc). Бросает, если не влезает.
    """
    res = compress_best(new_decompressed, sec.capacity)
    if res is None:
        mn = len(compress(new_decompressed, lc=0))
        raise ValueError(f"не влезает: min={mn} > capacity={sec.capacity}")
    comp, lc = res
    padded = comp + b"\x00" * (sec.capacity - len(comp))
    out = bytearray(img)
    out[sec.payload_slice] = padded
    return bytes(out), lc
