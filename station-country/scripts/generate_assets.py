#!/usr/bin/env python3
"""Generuje placeholder grafiku pro stanoviště země."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from countries import COUNTRIES

# Barvy pro stylizaci - vlajka/národní barva
COUNTRY_COLORS = {
    "US_HI": ("#0099cc", "#ff9933"),   # ocean + tropic
    "FR":    ("#0055a4", "#ef4135"),
    "JP":    ("#bc002d", "#ffffff"),
    "EG":    ("#ce1126", "#fac807"),
    "IT":    ("#008c45", "#cd212a"),
    "DK":    ("#c8102e", "#ffffff"),
    "AU":    ("#012169", "#e4002b"),
    "CZ":    ("#11457e", "#d7141a"),
    "GB":    ("#012169", "#c8102e"),
    "IN":    ("#ff9933", "#138808"),
    "AQ":    ("#a8c5d8", "#ffffff"),   # ice + snow
}


def logo_svg() -> str:
    """Logo 'Srdcem pro Ondráška'."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300" width="300" height="300">
  <defs>
    <radialGradient id="logo-bg" cx="50%" cy="50%">
      <stop offset="0%" stop-color="#b8dde5" stop-opacity="0.95"/>
      <stop offset="70%" stop-color="#d4ebec" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#e8f3f4" stop-opacity="0.1"/>
    </radialGradient>
  </defs>
  <circle cx="150" cy="150" r="135" fill="url(#logo-bg)"/>
  <!-- Srdce -->
  <path d="M 150 215
           C 150 215, 95 175, 95 135
           C 95 110, 115 95, 132 95
           C 144 95, 150 103, 150 110
           C 150 103, 156 95, 168 95
           C 185 95, 205 110, 205 135
           C 205 175, 150 215, 150 215 Z"
        fill="#7fb6c2" stroke="#5a98a5" stroke-width="2.5"/>
  <text x="150" y="140" font-family="Georgia, serif" font-size="17" font-style="italic"
        text-anchor="middle" fill="#1f3a4a" font-weight="500">Srdcem pro</text>
  <text x="150" y="172" font-family="Brush Script MT, cursive" font-size="30" font-style="italic"
        text-anchor="middle" fill="#1f3a4a" font-weight="700">Ondráška</text>
</svg>'''


def universal_default() -> str:
    """Univerzální placeholder pro výchozí obrazovku."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <defs>
    <radialGradient id="globe">
      <stop offset="0%" stop-color="#7fb6c2"/>
      <stop offset="100%" stop-color="#3a8f9e"/>
    </radialGradient>
  </defs>
  <circle cx="120" cy="120" r="105" fill="url(#globe)"/>
  <circle cx="120" cy="120" r="105" fill="none" stroke="#fff" stroke-width="2" opacity="0.4"/>
  <!-- Meridians -->
  <ellipse cx="120" cy="120" rx="105" ry="35" fill="none" stroke="#fff" stroke-width="2" opacity="0.3"/>
  <ellipse cx="120" cy="120" rx="35" ry="105" fill="none" stroke="#fff" stroke-width="2" opacity="0.3"/>
  <ellipse cx="120" cy="120" rx="70" ry="105" fill="none" stroke="#fff" stroke-width="2" opacity="0.3"/>
  <text x="120" y="135" font-family="serif" font-size="50" text-anchor="middle">🌍</text>
</svg>'''


def universal_custom() -> str:
    """Univerzální placeholder pro 'po scanu'."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120" width="200" height="120">
  <rect x="10" y="20" width="180" height="80" rx="10" fill="#7fb6c2" opacity="0.6"/>
  <text x="100" y="70" font-family="Georgia" font-size="22" text-anchor="middle" fill="#fff" font-weight="700">📍</text>
</svg>'''


def country_default_svg(name: str, code: str, color1: str, color2: str) -> str:
    """Velký kulatý obrázek pro default screen."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
  <defs>
    <radialGradient id="bg-{code}" cx="40%" cy="40%">
      <stop offset="0%" stop-color="{color1}" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="{color1}" stop-opacity="0.7"/>
    </radialGradient>
  </defs>
  <circle cx="120" cy="120" r="105" fill="url(#bg-{code})" stroke="{color2}" stroke-width="6"/>
  <text x="120" y="105" font-family="Georgia, serif" font-size="60" font-weight="bold"
        text-anchor="middle" fill="white" stroke="{color2}" stroke-width="1.5">{code}</text>
  <text x="120" y="160" font-family="Georgia, serif" font-size="22" font-weight="bold"
        text-anchor="middle" fill="white">{name}</text>
</svg>'''


def country_custom_svg(name: str, code: str, color1: str, color2: str) -> str:
    """Menší obrázek pro scan screen."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 130" width="200" height="130">
  <!-- Pozadí -->
  <rect x="0" y="0" width="200" height="130" rx="12" fill="{color1}" opacity="0.85"/>
  <!-- Akcent pruh -->
  <rect x="0" y="0" width="200" height="20" fill="{color2}"/>
  <rect x="0" y="110" width="200" height="20" fill="{color2}"/>
  <!-- Kód -->
  <text x="100" y="78" font-family="Georgia, serif" font-size="44" font-weight="bold"
        text-anchor="middle" fill="white">{code}</text>
  <!-- Název -->
  <text x="100" y="103" font-family="Georgia, serif" font-size="13" font-weight="600"
        text-anchor="middle" fill="white">{name}</text>
</svg>'''


def main(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generuji do: {target_dir}")

    # Logo
    (target_dir / "logo.svg").write_text(logo_svg())
    print("  logo.svg")

    # Univerzální fallbacky
    (target_dir / "country-default.svg").write_text(universal_default())
    (target_dir / "country-custom.svg").write_text(universal_custom())

    # Per země
    for c in COUNTRIES:
        color1, color2 = COUNTRY_COLORS.get(c.code, ("#3a8f9e", "#e85574"))
        code_lc = c.code.lower().replace("_", "-")
        (target_dir / f"country-{code_lc}-default.svg").write_text(
            country_default_svg(c.name_cz, c.code.replace("_", " "), color1, color2)
        )
        (target_dir / f"country-{code_lc}-custom.svg").write_text(
            country_custom_svg(c.name_cz, c.code.replace("_", " "), color1, color2)
        )
        print(f"  {c.code}: {c.name_cz}")

    print(f"Hotovo. {len(list(target_dir.glob('*.svg')))} SVG souborů.")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("frontend/assets")
    main(target)
