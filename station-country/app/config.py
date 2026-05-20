"""Konfigurace stanoviště země."""
import os
from pathlib import Path
from typing import Optional


def _load_conf(path: Path) -> dict:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


class Config:
    def __init__(self) -> None:
        conf = {}
        for p in [Path("/boot/station.conf"), Path("/etc/passport/station.conf")]:
            conf.update(_load_conf(p))

        def get(key: str, default: Optional[str] = None) -> str:
            return os.environ.get(f"PASSPORT_{key}", conf.get(key, default))

        # Country index 0..10
        country_idx_str = get("COUNTRY_INDEX", "")
        if not country_idx_str:
            raise RuntimeError(
                "COUNTRY_INDEX musí být nastaven (0-10). "
                "Vytvoř /boot/station.conf nebo nastav env PASSPORT_COUNTRY_INDEX."
            )
        self.country_index: int = int(country_idx_str)
        if not 0 <= self.country_index <= 10:
            raise RuntimeError(f"COUNTRY_INDEX out of range: {self.country_index}")

        self.nfc_device: str = get("NFC_DEVICE", "mock")
        self.kiosk_port: int = int(get("KIOSK_PORT", "8090"))
        self.return_to_default_seconds: float = float(
            get("RETURN_TO_DEFAULT_SECONDS", "20")
        )
        self.completion_show_seconds: float = float(
            get("COMPLETION_SHOW_SECONDS", "45")
        )
        self.debounce_seconds: float = float(get("DEBOUNCE_SECONDS", "2.0"))

        # Cesty
        self.base_dir = Path(__file__).resolve().parent.parent
        self.frontend_dir = self.base_dir / "frontend"
        self.log_dir = Path(get("LOG_DIR", "/var/log/passport"))
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.log_dir = Path("/tmp")


config = Config()
