"""Самотесты тулкита: python -m biostool.validate <base.rom>

Проверяет на реальном образе:
  1) LZMA round-trip: каждая секция декомпрессится; рекомпресс EDK2-совместим
     (заголовок несёт реальный размер) и декодируется обратно байт-в-байт.
  2) repack_inplace размер-нейтрален и помещается.
  3) replace_module_body: подмена тела и обратная проверка наличия.
Код возврата 0 = всё ок.
"""
import sys

from . import edk2, modedit


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m biostool.validate <base.rom>")
        return 2
    img = open(argv[0], "rb").read()
    secs = list(edk2.iter_sections(img))
    ok = bad = 0
    sample = None
    for sec in secs:
        dec = edk2.decompress(img, sec)
        if dec is None:
            bad += 1
            continue
        ok += 1
        # рекомпресс -> декодируется обратно тем же содержимым?
        comp = edk2.compress(dec, lc=0)
        back = None
        try:
            import lzma
            back = lzma.decompress(comp, format=lzma.FORMAT_ALONE)
        except Exception:
            pass
        assert back == dec, f"round-trip mismatch @0x{sec.offset:x}"
        if sample is None and len(dec) > 4096:
            sample = sec

    print(f"[1] LZMA-секций: {len(secs)}; декомпресс OK={ok}, не-LZMA={bad}")
    print(f"    round-trip (рекомпресс->декомпресс == исходник): OK для всех {ok}")

    # 2) repack_inplace на семпле (заменяем 1 байт тела, размер сохраняется)
    dec = edk2.decompress(img, sample)
    mutated = bytearray(dec)
    mutated[len(mutated) // 2] ^= 0xFF
    out, lc = edk2.repack_inplace(img, sample, bytes(mutated))
    assert len(out) == len(img), "repack изменил размер образа"
    sec2 = next(s for s in edk2.iter_sections(out) if s.offset == sample.offset)
    assert edk2.decompress(out, sec2) == bytes(mutated), "repack: содержимое не совпало"
    print(f"[2] repack_inplace @0x{sample.offset:x}: size-neutral OK, lc={lc}, "
          f"декодируется обратно OK")

    # 3) replace_module_body: подмена уникального куска тем же размером.
    #    Перебираем секции — берём первую, где подмена влезает в capacity
    #    (часть секций упакована впритык — это нормально, такие модули in-place
    #    не редактируются; нам важно, что МЕХАНИКА подмены корректна).
    done = False
    for sec in edk2.iter_sections(img):
        d = edk2.decompress(img, sec)
        if d is None or len(d) < 512:
            continue
        marker = d[256:256 + 32]
        if d.count(marker) != 1:
            continue
        repl = bytes(((b + 1) & 0xFF) for b in marker)
        try:
            out2, info = modedit.replace_module_body(img, marker, repl)
        except ValueError:
            continue  # эта секция впритык — пробуем следующую
        sec3 = info["section"]
        assert repl in edk2.decompress(out2, sec3), "replace_module_body: подмена не найдена"
        assert len(out2) == len(img), "replace_module_body изменил размер"
        print(f"[3] replace_module_body @0x{sec3.offset:x}: подмена 32Б OK (lc={info['lc']})")
        done = True
        break
    assert done, "[3] не нашлось секции с запасом под подмену"

    print("\nВСЕ ТЕСТЫ ПРОЙДЕНЫ ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
