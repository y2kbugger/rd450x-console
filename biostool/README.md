# biostool — тулкит редактирования AMI Aptio BIOS (RD450X)

Чистая замена инлайн-скриптам. Делает то, что **UEFITool NE не умеет** (его GUI —
read-only вьюер, Replace body/Insert серые), а старый UEFITool 0.28 портит на этом
образе non-empty pad-файлы. Работает прямой бинарной хирургией FV.

## Зачем
Образ RD450X (AMI Aptio V) сжимает каждый DXE-модуль **отдельной GUID-defined
LZMA-секцией**. Большинство наших правок **размер-нейтральны** (строки/опкоды той же
длины) → секцию можно пересобрать **in-place** (рекомпресс + паддинг до исходного
размера), не трогая раскладку FV. ReBar (новый DXE-драйвер) — вставкой FFS в
свободное место тома.

Критично: EDK2-декодер читает РЕАЛЬНЫЙ размер из LZMA-заголовка (не EOS). Python
пишет «размер неизвестен» + EOS → BIOS/UEFIExtract не распакуют. Тулкит проставляет
размер вручную (`edk2.compress`). Эта тонкость и ломала ранние попытки.

## Модули
- `edk2`    — GUID-defined LZMA-секции: `iter_sections`, `decompress`, `compress`
  (EDK2-совместимо), `repack_inplace` (size-neutral).
- `modedit` — `replace_module_body` (подмена тела модуля in-place),
  `patch_section` (само-локация: найти секцию по предикату → transform → repack,
  без пред-извлечённого тела), `patch_string_inplace` (UTF-16 строка ≤ длины),
  `repoint_ref` / `ref_pattern` (FormId в cross-formset IFR-Ref).
- `ffs`     — `find_volumes`, `free_space`, `insert_ffs` (DXE-драйвер в free space).
- `logo`    — `build_logo` (растр → 4bpp BMP 400×100 под ROM-hole с бюджетом сжатия).

## CLI
```sh
PY=logo/venv/bin/python      # venv с Pillow (lzma — stdlib); запускать из bios/
$PY -m biostool.cli sections   img/R450X219_bmc_nvme.rom      # список LZMA-секций
$PY -m biostool.cli volumes    build/219_claude.rom           # тома + free space
$PY -m biostool.cli replace-body IMG OLD.efi NEW.efi OUT.rom  # подмена модуля
$PY -m biostool.cli insert-ffs   IMG ReBarDxe.ffs OUT --volume 2
$PY -m biostool.cli logo         src.svg.png out.bmp --budget 2652
$PY -m biostool.cli verify       OUT --expect "PCIe Bifurcation (IIO)"
```

## Сборка RD450X-мода и валидация
```sh
$PY -m biostool.validate    img/R450X602_vanilla.rom    # самотесты (round-trip и т.д.)

# база и выход — позиционные аргументы (см. --help):
$PY -m biostool.build_rd450x img/R450X602_vanilla.rom build/602_claude.rom
$PY -m biostool.build_rd450x img/R450X219_bmc_nvme.rom build/219_claude.rom \
      --logo build/claude_oem_logo.bmp

# + ReBar (опц.):
$PY -m biostool.cli insert-ffs build/602_claude.rom build/ReBarDxe.ffs build/602_rc_rebar.rom --volume 2
```

`build_rd450x BASE OUT [--logo BMP]` находит и Setup-модуль, и FFS-файл лого **прямо
в образе** (Setup — по подписи cross-formset Ref на IntelRCSetup; лого — по GUID файла
`63819805-67BB-…`), поэтому работает на любой родственной базе (219 / 231 / 602 /
RD450NV) без пред-извлечённых тел в `re/`. Обязательный шаг — раскрытие меню IIO;
баннер AMITSE, AMI-строка и лого — vanity (необязательны). Новый лого задаётся одним
файлом `--logo` (BMP того же размера, что в ROM-hole — 400×100 4bpp, 20118 Б; см.
`cli logo`); старое лого извлекать не нужно. Баннер на 231/602/nv пропускается —
секция упакована под завязку.

Проверено независимо `tools/UEFIExtract` (EDK2-декодер): 0 ошибок, все патчи на месте.
