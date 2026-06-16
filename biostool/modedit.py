"""Размер-нейтральные правки модулей: замена тела, in-place строки, IFR-ref."""
import struct
import uuid

from . import edk2


def replace_module_body(img, old_body, new_body):
    """Находит LZMA-секцию, чьё декомпресс. содержимое содержит old_body,
    заменяет old_body->new_body (тот же размер) и пересобирает секцию in-place.

    Возвращает (новый_образ, info). Бросает, если секция не найдена.
    """
    if len(old_body) != len(new_body):
        raise ValueError("тело сменило размер — нужна полная пересборка FV")
    for sec in edk2.iter_sections(img):
        dec = edk2.decompress(img, sec)
        if dec is None or old_body not in dec:
            continue
        new_dec = dec.replace(old_body, new_body, 1)
        out, lc = edk2.repack_inplace(img, sec, new_dec)
        return out, {"section": sec, "lc": lc,
                     "comp": len(edk2.compress(new_dec, lc=lc)), "cap": sec.capacity}
    raise LookupError("LZMA-секция с указанным телом не найдена")


def patch_section(img, predicate, transform, label=""):
    """Само-локация: находит LZMA-секцию, для которой predicate(dec) истинно,
    применяет transform(dec)->new_dec (ТОТ ЖЕ размер) и пересобирает её in-place.

    В отличие от replace_module_body не требует заранее извлечённого тела модуля —
    секция ищется по содержимому прямо в образе (база-агностично).
    Возвращает (новый_образ, info). LookupError если секция не найдена,
    ValueError если transform сменил размер.
    """
    for sec in edk2.iter_sections(img):
        dec = edk2.decompress(img, sec)
        if dec is None or not predicate(dec):
            continue
        new_dec = transform(dec)
        if len(new_dec) != len(dec):
            raise ValueError(f"{label}: transform сменил размер {len(dec)}->{len(new_dec)}")
        out, lc = edk2.repack_inplace(img, sec, new_dec)
        return out, {"section": sec, "lc": lc,
                     "comp": len(edk2.compress(new_dec, lc=lc)), "cap": sec.capacity}
    raise LookupError(f"{label or 'patch_section'}: подходящая LZMA-секция не найдена")


def ref_pattern(formset_guid, formid):
    """Байтовая подпись cross-formset Ref-опкода (FormId+0,2+FormSetGuid_le)."""
    return struct.pack("<HH", formid, 0) + uuid.UUID(formset_guid).bytes_le


# FFS-файл OEM-логотипа (Raw-секция с BMP внутри GUID-defined LZMA-секции).
OEM_LOGO_GUID = "63819805-67BB-46EF-AA8D-1524A19A01E4"


def replace_oem_logo(img, new_bmp, file_guid=OEM_LOGO_GUID):
    """Заменяет OEM-логотип БЕЗ извлечения старого: находит FFS-файл лого по GUID,
    его LZMA-секцию (распаковка = raw-хедер + BMP), подменяет тело BMP на new_bmp
    (размер должен совпасть) и пересобирает секцию in-place.

    Возвращает (новый_образ, info). Бросает LookupError/ValueError при несоответствии.
    """
    fg = uuid.UUID(file_guid).bytes_le
    pos = img.find(fg)
    if pos < 0:
        raise LookupError(f"FFS-файл лого {file_guid} в образе не найден")
    # первая LZMA-секция после заголовка файла, чья распаковка = raw-секция с BMP
    for sec in sorted((s for s in edk2.iter_sections(img) if s.offset > pos),
                      key=lambda s: s.offset):
        dec = edk2.decompress(img, sec)
        if dec is None:
            continue
        i = 4 if (len(dec) > 6 and dec[3] == 0x19 and dec[4:6] == b"BM") else dec.find(b"BM")
        if i < 0:
            continue
        old_bmp = dec[i:]
        if len(new_bmp) != len(old_bmp):
            raise ValueError(f"размер лого изменился {len(old_bmp)}->{len(new_bmp)}; "
                             f"нужен BMP ровно {len(old_bmp)} Б (см. logo --budget)")
        new_dec = dec[:i] + new_bmp
        out, lc = edk2.repack_inplace(img, sec, new_dec)
        return out, {"section": sec, "lc": lc, "bmp_len": len(new_bmp),
                     "comp": len(edk2.compress(new_dec, lc=lc)), "cap": sec.capacity}
    raise LookupError("LZMA-секция с BMP-логотипом в файле лого не найдена")


def patch_string_inplace(data, old, new, encoding="utf-16-le"):
    """Перезаписывает строку old->new в data (UTF-16), дополняя пробелами до длины
    old (терминатор сохраняется на месте). Бросает, если new длиннее или old не уникален.
    """
    ob = old.encode(encoding)
    n = data.count(ob)
    if n != 1:
        raise ValueError(f"строка {old!r} встречается {n} раз (нужно 1)")
    if len(new) > len(old):
        raise ValueError(f"{new!r} длиннее {old!r} ({len(new)}>{len(old)})")
    out = bytearray(data)
    j = out.find(ob)
    out[j:j + len(ob)] = new.ljust(len(old)).encode(encoding)
    return bytes(out)


def repoint_ref(data, formset_guid, old_formid, new_formid):
    """Меняет FormId в cross-formset Ref-опкоде (EFI_IFR_REF на formset_guid).

    Ищет паттерн: FormId(2 LE)+RefQuestionId(0,2)+FormSetGuid(16) и патчит FormId.
    """
    g = uuid.UUID(formset_guid).bytes_le
    pat = struct.pack("<HH", old_formid, 0) + g
    n = data.count(pat)
    if n != 1:
        raise ValueError(f"Ref FormId=0x{old_formid:x} на {formset_guid}: {n} вхождений (нужно 1)")
    out = bytearray(data)
    j = out.find(pat)
    struct.pack_into("<H", out, j, new_formid)
    return bytes(out)
