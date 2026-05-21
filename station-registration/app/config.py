"""Konfigurace registrační stanice."""
import os
from pathlib import Path


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

        def get(key: str, default: str = "") -> str:
            return os.environ.get(f"PASSPORT_{key}", conf.get(key, default))

        self.nfc_device: str = get("NFC_DEVICE", "mock")
        self.http_port: int = int(get("HTTP_PORT", "8000"))
        self.debounce_seconds: float = float(get("DEBOUNCE_SECONDS", "0.5"))

        self.base_dir = Path(__file__).resolve().parent.parent
        self.frontend_dir = self.base_dir / "frontend"
        self.log_dir = Path(get("LOG_DIR", "/var/log/passport"))
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.log_dir = Path("/tmp/passport-logs")
            self.log_dir.mkdir(parents=True, exist_ok=True)


config = Config()
