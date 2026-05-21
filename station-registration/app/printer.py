"""
Tisk fotky cestovatele pro vlepení do papírového pasu.

Postup:
1. Přijatá fotka z webcam (base64 JPEG/PNG)
2. Oříznutí na požadovaný poměr stran (35:45)
3. Resize na cílové rozlišení (300 DPI)
4. Uložení JPG pro audit + samostatný tisk
5. CUPS print pomocí 'lp' příkazu

Pokud CUPS_PRINTER není nastaven, jen uloží soubor a tisk přeskočí
(užitečné pro vývoj/testování).
"""
import asyncio
import base64
import io
import logging
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def _crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Ořízne obrázek na cílový poměr stran (centrované)."""
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Obrázek je širší - ořízni vlevo/vpravo
        new_w = int(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        box = (offset, 0, offset + new_w, src_h)
    else:
        # Obrázek je vyšší - ořízni nahoře/dole
        new_h = int(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        box = (0, offset, src_w, offset + new_h)

    return img.crop(box)


def process_photo(
    photo_base64: str,
    target_w_mm: int = 35,
    target_h_mm: int = 45,
    dpi: int = 300,
) -> bytes:
    """
    Zpracuje base64 fotku - ořízne, resize, vrátí JPEG bytes.
    """
    # Odstraň data URL prefix pokud je
    if "," in photo_base64 and photo_base64.startswith("data:"):
        photo_base64 = photo_base64.split(",", 1)[1]

    raw_bytes = base64.b64decode(photo_base64)
    img = Image.open(io.BytesIO(raw_bytes))

    # Konverze do RGB (pro JPEG)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Ořez na poměr stran
    cropped = _crop_to_aspect(img, target_w_mm, target_h_mm)

    # Resize na cílové rozlišení
    target_w_px = int(target_w_mm * dpi / 25.4)
    target_h_px = int(target_h_mm * dpi / 25.4)
    resized = cropped.resize((target_w_px, target_h_px), Image.Resampling.LANCZOS)

    # Output JPEG
    out = io.BytesIO()
    resized.save(out, format="JPEG", quality=92, dpi=(dpi, dpi))
    return out.getvalue()


async def save_photo(
    photo_jpeg: bytes,
    nfc_uid: str,
    photos_dir: Path,
) -> Path:
    """Uloží zpracovanou fotku do photos_dir/<uid>.jpg."""
    photos_dir.mkdir(parents=True, exist_ok=True)
    path = photos_dir / f"{nfc_uid}.jpg"
    path.write_bytes(photo_jpeg)
    logger.info(f"Foto uloženo: {path}")
    return path


async def print_photo(
    photo_path: Path,
    printer_name: str,
    copies: int = 1,
) -> bool:
    """
    Pošle fotku do tisku přes CUPS (příkaz 'lp').

    Pokud printer_name je prázdný řetězec, tisk se přeskočí.
    Vrátí True/False podle úspěchu.
    """
    if not printer_name:
        logger.info(f"Tisk přeskočen (printer není nakonfigurován): {photo_path}")
        return True

    cmd = [
        "lp",
        "-d", printer_name,
        "-n", str(copies),
        "-o", "media=Custom.35x45mm",
        "-o", "fit-to-page",
        str(photo_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(
                f"Tisk selhal (rc={proc.returncode}): "
                f"stdout={stdout.decode()!r} stderr={stderr.decode()!r}"
            )
            return False
        logger.info(f"Foto odesláno do tisku: {photo_path} → {printer_name}")
        return True
    except FileNotFoundError:
        logger.error("Příkaz 'lp' nenalezen. Nainstaluj CUPS: apt install cups cups-client")
        return False
    except Exception as e:
        logger.error(f"Tisk chyba: {e}")
        return False


async def process_and_print_photo(
    photo_base64: str,
    nfc_uid: str,
    photos_dir: Path,
    printer_name: str,
    photo_width_mm: int = 35,
    photo_height_mm: int = 45,
    photo_dpi: int = 300,
) -> tuple[bool, Optional[Path]]:
    """
    Kompletní pipeline: dekód, zpracuj, ulož, vytiskni.
    Vrací (success, photo_path).
    """
    try:
        jpeg = process_photo(
            photo_base64,
            target_w_mm=photo_width_mm,
            target_h_mm=photo_height_mm,
            dpi=photo_dpi,
        )
    except Exception as e:
        logger.error(f"Zpracování fotky selhalo: {e}")
        return False, None

    photo_path = await save_photo(jpeg, nfc_uid, photos_dir)

    print_ok = await print_photo(photo_path, printer_name)
    return print_ok, photo_path
