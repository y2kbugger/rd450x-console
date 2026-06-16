"""biostool — тулкит для редактирования AMI Aptio BIOS (RD450X).

Модули:
  edk2    — GUID-defined LZMA-секции (декомпресс/рекомпресс EDK2-совместимо)
  modedit — замена тела модуля in-place, патч UTF-16 строк, repoint IFR-ref
  ffs     — FFSv2 тома: поиск, free space, вставка FFS-файлов (DXE-драйверы)
  logo    — сборка 4bpp BMP OEM-логотипа под ROM-hole с бюджетом сжатия

CLI: python -m biostool <команда>   (см. biostool/cli.py)
Самотесты: python -m biostool.validate <base.rom>
"""
from . import edk2, modedit, ffs  # noqa: F401

__all__ = ["edk2", "modedit", "ffs", "logo"]
