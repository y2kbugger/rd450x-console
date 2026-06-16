"""CLI: python -m biostool <команда> [опции]."""
import argparse
import sys

from . import edk2, modedit, ffs


def _read(p):
    with open(p, "rb") as f:
        return f.read()


def _write(p, b):
    with open(p, "wb") as f:
        f.write(b)


def cmd_sections(a):
    img = _read(a.image)
    n = 0
    for sec in edk2.iter_sections(img):
        dec = edk2.decompress(img, sec)
        n += 1
        print(f"  @0x{sec.offset:06x} size={sec.size:<8} cap={sec.capacity:<8} "
              f"dec={'%d' % len(dec) if dec else 'FAIL'}")
    print(f"всего LZMA-секций: {n}")


def cmd_volumes(a):
    img = _read(a.image)
    for v in ffs.find_volumes(img):
        off, free = ffs.free_space(img, v)
        print(f"  {v}  free=0x{free:x} @0x{off:06x}")


def cmd_replace_body(a):
    img = _read(a.image)
    out, info = modedit.replace_module_body(img, _read(a.old), _read(a.new))
    _write(a.out, out)
    print(f"OK секция {info['section']} lc={info['lc']} comp={info['comp']}/{info['cap']} -> {a.out}")


def cmd_insert_ffs(a):
    img = _read(a.image)
    vols = ffs.find_volumes(img)
    vol = vols[a.volume]
    out, at = ffs.insert_ffs(img, vol, _read(a.ffs))
    _write(a.out, out)
    print(f"OK FFS вставлен в {vol} @0x{at:06x} -> {a.out}")


def cmd_logo(a):
    from . import logo
    nc, sz = logo.build_logo(a.src, a.out, budget=a.budget)
    print(f"OK логотип: {nc} цветов, LZMA={sz}{' <= %d' % a.budget if a.budget else ''} -> {a.out}")


def cmd_verify(a):
    img = _read(a.image)
    bad = 0
    for sec in edk2.iter_sections(img):
        if edk2.decompress(img, sec) is None:
            bad += 1
    print(f"LZMA-секций c ошибкой декомпрессии: {bad}")
    for s in a.expect or []:
        present = any((s.encode("utf-16-le") in (edk2.decompress(img, sec) or b""))
                      for sec in edk2.iter_sections(img))
        print(f"  {'OK' if present else 'НЕТ'}: {s!r}")
    sys.exit(1 if bad else 0)


def main(argv=None):
    p = argparse.ArgumentParser(prog="biostool", description="AMI Aptio BIOS toolkit (RD450X)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sections", help="список LZMA-секций")
    s.add_argument("image"); s.set_defaults(fn=cmd_sections)

    s = sub.add_parser("volumes", help="список FFS-томов и free space")
    s.add_argument("image"); s.set_defaults(fn=cmd_volumes)

    s = sub.add_parser("replace-body", help="заменить тело модуля in-place (size-neutral)")
    s.add_argument("image"); s.add_argument("old"); s.add_argument("new"); s.add_argument("out")
    s.set_defaults(fn=cmd_replace_body)

    s = sub.add_parser("insert-ffs", help="вставить FFS-файл в free space тома")
    s.add_argument("image"); s.add_argument("ffs"); s.add_argument("out")
    s.add_argument("--volume", type=int, default=0, help="индекс тома (из 'volumes')")
    s.set_defaults(fn=cmd_insert_ffs)

    s = sub.add_parser("logo", help="собрать 4bpp BMP OEM-логотип")
    s.add_argument("src"); s.add_argument("out"); s.add_argument("--budget", type=int)
    s.set_defaults(fn=cmd_logo)

    s = sub.add_parser("verify", help="проверить декомпрессию + наличие строк")
    s.add_argument("image"); s.add_argument("--expect", nargs="*")
    s.set_defaults(fn=cmd_verify)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
