"""Сборка кастомного RD450X BIOS-мода через biostool (любая родственная база).

Все правки — размер-нейтральные, in-place; нужные секции находятся ПРЯМО в образе
(само-локация, без пред-извлечённых тел в re/):
  • Setup    : Ref «Advanced Power Management»→IIO Configuration (FormId 0x5) +
               переименование пункта в «PCIe Bifurcation (IIO)» (раскрытие меню
               бифуркации — ОБЯЗАТЕЛЬНЫЙ шаг) + «American Megatrends»→«Anthropic / Claude»
  • AMITSE   : баннер → «RD450X Setup Utility - patched by Claude (C) %04x Anthropic» (vanity)
  • OEM-лого : Claude (vanity, только если переданы --logo-orig/--logo-new)
ReBar (вставка FFS) — отдельной командой `biostool.cli insert-ffs` (не размер-нейтрально).

Механизм бифуркации (доказано разбором RD450NV vs 602): IIO-меню пишет в переменную
IntelSetup (off 0x53x), PEI-оверрайда нет → меню реально управляет железом. См.
build/RD450NV_iio-GUIDE.md.

Примеры (из каталога bios/):
    python -m biostool.build_rd450x img/R450X602_vanilla.rom build/602_claude.rom
    python -m biostool.build_rd450x img/R450X219_bmc_nvme.rom build/219_claude.rom \\
        --logo-orig build/219_oem_logo_orig.bmp --logo-new build/claude_oem_logo.bmp
"""
import argparse
import sys

from . import edk2, modedit

RC_GUID = "EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9"
APM_PROMPT = "Advanced Power Management Configuration"
APM_HELP = "Displays and provides option to change the Power Management Settings"
IIO_HELP = "Intel RC IIO Configuration: per-slot PCIe bifurcation"
BANNER_OLD = "Aptio Setup Utility - Copyright (C) %04x American Megatrends, Inc."
BANNER_NEW = "RD450X Setup Utility  -  patched by Claude  (C) %04x  Anthropic"
EXPECT = ["PCIe Bifurcation (IIO)", "RD450X Setup Utility", "Anthropic / Claude"]

# Подпись главного (видимого) Setup-модуля: единственная секция с cross-formset
# Ref на IntelRCSetup FormId 0xC (Advanced Power Management) — её и репойнтим.
SETUP_SIG = modedit.ref_pattern(RC_GUID, 0xC)


def _r(p):
    with open(p, "rb") as f:
        return f.read()


def _u16(s):
    return s.encode("utf-16-le")


def patch_setup(dec):
    """Раскрыть бифуркацию (обязательно) + перебрендить AMI-строку (vanity)."""
    dec = modedit.repoint_ref(dec, RC_GUID, 0xC, 0x5)          # APM -> IIO Configuration
    dec = modedit.patch_string_inplace(dec, APM_PROMPT, "PCIe Bifurcation (IIO)")
    dec = modedit.patch_string_inplace(dec, APM_HELP, IIO_HELP)
    try:                                                       # vanity, необязательно
        dec = modedit.patch_string_inplace(dec, "American Megatrends", "Anthropic / Claude")
    except ValueError as e:
        print(f"    (AMI-строка не переименована: {e})")
    return dec


def build(base, out, logo_orig=None, logo_new=None):
    """Собрать мод из base в out. Возвращает 0 при успехе (бифуркация на месте)."""
    img = _r(base)
    base_len = len(img)
    print(f"=== база: {base} ===")

    # 1) Setup — раскрытие меню бифуркации (ОБЯЗАТЕЛЬНО, секция ищется в образе)
    img, info = modedit.patch_section(
        img,
        predicate=lambda d: d.count(SETUP_SIG) == 1 and _u16(APM_PROMPT) in d,
        transform=patch_setup, label="Setup (бифуркация)")
    print(f"  ✓ Setup (бифуркация+Claude): @0x{info['section'].offset:06x} "
          f"comp={info['comp']}/{info['cap']} lc={info['lc']}")

    # 2) AMITSE баннер — vanity, само-локация по строке
    try:
        img, info = modedit.patch_section(
            img,
            predicate=lambda d: _u16(BANNER_OLD) in d,
            transform=lambda d: modedit.patch_string_inplace(d, BANNER_OLD, BANNER_NEW),
            label="AMITSE баннер")
        print(f"  ✓ AMITSE баннер: @0x{info['section'].offset:06x} comp={info['comp']}/{info['cap']}")
    except (LookupError, ValueError) as e:
        print(f"  ⚠ AMITSE баннер: ПРОПУЩЕНО ({e})")

    # 3) OEM-лого — vanity, только если переданы оба файла (подмена тела модуля)
    if logo_orig and logo_new:
        try:
            img, info = modedit.replace_module_body(img, _r(logo_orig), _r(logo_new))
            print(f"  ✓ OEM-лого: @0x{info['section'].offset:06x} comp={info['comp']}/{info['cap']}")
        except (LookupError, ValueError, FileNotFoundError) as e:
            print(f"  ⚠ OEM-лого: ПРОПУЩЕНО ({e})")

    with open(out, "wb") as f:
        f.write(img)

    # верификация: 0 LZMA-ошибок + наличие пункта бифуркации + размер сохранён
    bad = sum(1 for s in edk2.iter_sections(img) if edk2.decompress(img, s) is None)
    found = {e: any(_u16(e) in (edk2.decompress(img, s) or b"")
                    for s in edk2.iter_sections(img)) for e in EXPECT}
    core_ok = bad == 0 and found["PCIe Bifurcation (IIO)"] and len(img) == base_len
    print(f"  -> {out} ({len(img)} B); LZMA-ошибок={bad}; патчи: " +
          ", ".join(f"{e.split()[0]}={'OK' if v else '—'}" for e, v in found.items()))
    print("  СБОРКА OK ✓ (бифуркация на месте)\n" if core_ok else "  ПРОБЛЕМА ✗\n")
    return 0 if core_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="biostool.build_rd450x",
        description="Собрать RD450X-мод (раскрытие меню бифуркации + опц. vanity) "
                    "из любой родственной базы. Размер-нейтрально, in-place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Пример:\n  python -m biostool.build_rd450x "
               "img/R450X602_vanilla.rom build/602_claude.rom")
    ap.add_argument("base", help="путь к базовому образу (16 МБ SPI-дамп)")
    ap.add_argument("out", help="путь для выходного образа")
    ap.add_argument("--logo-orig", metavar="BMP",
                    help="исходный OEM-лого (тело модуля для подмены; vanity)")
    ap.add_argument("--logo-new", metavar="BMP",
                    help="новый OEM-лого Claude (требует --logo-orig; vanity)")
    args = ap.parse_args(argv)
    if bool(args.logo_orig) != bool(args.logo_new):
        ap.error("--logo-orig и --logo-new задаются только вместе")
    return build(args.base, args.out, args.logo_orig, args.logo_new)


if __name__ == "__main__":
    sys.exit(main())
