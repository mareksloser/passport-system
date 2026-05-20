"""
Passport chip - serializace/deserializace dat z/do NTAG213.

Layout (64 bytů):
  offset  size  field
  0x00    1     magic byte (0x53 = 'S')
  0x01    1     verze formátu (0x01)
  0x02    1     pohlaví (0x01=M, 0x02=F)
  0x03    1     CRC8 přes bajty 4..63
  0x04    2     rok narození (LE uint16)
  0x06    2     visited countries bitmask (LE uint16, bity 0..10)
  0x08    1     last visited country index (0xFF = none)
  0x09    1     completed flag
  0x0A    2     total scan count (LE uint16)
  0x0C    11    per-country visit counter (uint8 × 11)
  0x17    16    first_name (UTF-8, null-terminated)
  0x27    25    reserved (FF padding)

NTAG213 user memory: 144 B, my používáme prvních 64.
"""
from dataclasses import dataclass, field
from typing import List, Optional

CHIP_SIZE = 64
MAGIC_BYTE = 0x53          # 'S'
FORMAT_VERSION = 0x01
GENDER_M = 0x01
GENDER_F = 0x02
NO_LAST_COUNTRY = 0xFF
MAX_COUNTRIES = 11
NAME_FIELD_SIZE = 16       # bytes (UTF-8) - efektivně ~7-15 znaků s háčky

# Indexy zemí - musí odpovídat lokální DB
# (definované v shared/countries.py)


class ChipDataError(Exception):
    """Data na čipu jsou neplatná nebo poškozená."""


def _crc8(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """CRC-8 (poly 0x07, init 0x00) - jednoduchý a běžný."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


@dataclass
class PassportChip:
    """Data uložená na NFC čipu."""
    first_name: str = ""
    gender: str = "M"  # 'M' nebo 'F'
    birth_year: int = 0
    visited_mask: int = 0           # bity 0..10 = země 0..10
    last_country_idx: int = NO_LAST_COUNTRY  # 0xFF = žádná
    completed: bool = False
    total_scans: int = 0
    visit_counters: List[int] = field(
        default_factory=lambda: [0] * MAX_COUNTRIES
    )

    # --- Business logic helpers ---

    @property
    def is_registered(self) -> bool:
        """Pas je zaregistrovaný, pokud má vyplněné jméno."""
        return bool(self.first_name)

    @property
    def unique_countries_visited(self) -> int:
        return bin(self.visited_mask).count("1")

    def visits_to(self, country_idx: int) -> int:
        if not 0 <= country_idx < MAX_COUNTRIES:
            return 0
        return self.visit_counters[country_idx]

    def has_visited(self, country_idx: int) -> bool:
        return bool(self.visited_mask & (1 << country_idx))

    def record_visit(self, country_idx: int) -> None:
        """Zaznamenej návštěvu této země. Vrací aktualizovaná data."""
        if not 0 <= country_idx < MAX_COUNTRIES:
            raise ValueError(f"Invalid country index: {country_idx}")

        # Inkrementuj counter (saturace na 255)
        self.visit_counters[country_idx] = min(
            255, self.visit_counters[country_idx] + 1
        )
        # Označ v bitmasce
        self.visited_mask |= (1 << country_idx)
        # Last visited
        self.last_country_idx = country_idx
        # Total scans (saturace na 65535)
        self.total_scans = min(65535, self.total_scans + 1)
        # Completion check
        if self.unique_countries_visited == MAX_COUNTRIES:
            self.completed = True

    # --- (De)serializace ---

    def to_bytes(self) -> bytes:
        """Serializuje strukturu do 64 bajtů pro zápis na čip."""
        if self.gender not in ("M", "F"):
            raise ValueError(f"Invalid gender: {self.gender}")
        if not 0 <= self.birth_year <= 0xFFFF:
            raise ValueError(f"Birth year out of range: {self.birth_year}")
        if not 0 <= self.visited_mask <= 0x07FF:  # 11 bitů
            raise ValueError("visited_mask out of range")
        if len(self.visit_counters) != MAX_COUNTRIES:
            raise ValueError("visit_counters must have 11 items")

        name_bytes = self.first_name.encode("utf-8")[:NAME_FIELD_SIZE - 1]
        name_padded = name_bytes + b"\x00" * (NAME_FIELD_SIZE - len(name_bytes))

        buf = bytearray(CHIP_SIZE)
        buf[0] = MAGIC_BYTE
        buf[1] = FORMAT_VERSION
        buf[2] = GENDER_M if self.gender == "M" else GENDER_F
        buf[3] = 0  # CRC placeholder
        buf[4:6] = self.birth_year.to_bytes(2, "little")
        buf[6:8] = self.visited_mask.to_bytes(2, "little")
        buf[8] = self.last_country_idx & 0xFF
        buf[9] = 1 if self.completed else 0
        buf[10:12] = self.total_scans.to_bytes(2, "little")
        buf[12:23] = bytes(self.visit_counters)
        buf[23:39] = name_padded
        # Bytes 39..63 zůstanou jako 0x00 (rezerva)
        # Pro vizuální čistotu vyplníme 0xFF
        for i in range(39, CHIP_SIZE):
            buf[i] = 0xFF

        # Spočítej CRC8 přes 4..63 a vlož na index 3
        crc = _crc8(bytes(buf[4:CHIP_SIZE]))
        buf[3] = crc

        return bytes(buf)

    @classmethod
    def from_bytes(cls, data: bytes) -> "PassportChip":
        """Načte strukturu z bajtů. Vyhodí ChipDataError pokud jsou data neplatná."""
        if len(data) < CHIP_SIZE:
            raise ChipDataError(
                f"Příliš málo dat: {len(data)} B, potřeba {CHIP_SIZE}"
            )

        # Magic byte check
        if data[0] != MAGIC_BYTE:
            raise ChipDataError(
                f"Neplatný magic byte: 0x{data[0]:02X} (očekáván 0x{MAGIC_BYTE:02X}). "
                "Tento čip nepatří k naší akci."
            )

        # Verze
        version = data[1]
        if version != FORMAT_VERSION:
            raise ChipDataError(
                f"Nepodporovaná verze formátu: {version} (očekávána {FORMAT_VERSION})"
            )

        # CRC check
        stored_crc = data[3]
        computed_crc = _crc8(bytes(data[4:CHIP_SIZE]))
        if stored_crc != computed_crc:
            raise ChipDataError(
                f"CRC nesedí: uloženo 0x{stored_crc:02X}, "
                f"spočítáno 0x{computed_crc:02X}. Data jsou poškozená."
            )

        gender_byte = data[2]
        if gender_byte == GENDER_M:
            gender = "M"
        elif gender_byte == GENDER_F:
            gender = "F"
        else:
            raise ChipDataError(f"Neplatné pohlaví: 0x{gender_byte:02X}")

        birth_year = int.from_bytes(data[4:6], "little")
        visited_mask = int.from_bytes(data[6:8], "little")
        last_country = data[8]
        completed = bool(data[9])
        total_scans = int.from_bytes(data[10:12], "little")
        visit_counters = list(data[12:23])

        # Name - oříznout na první null byte
        name_bytes = bytes(data[23:39])
        null_idx = name_bytes.find(b"\x00")
        if null_idx >= 0:
            name_bytes = name_bytes[:null_idx]
        try:
            first_name = name_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise ChipDataError("Jméno není validní UTF-8")

        return cls(
            first_name=first_name,
            gender=gender,
            birth_year=birth_year,
            visited_mask=visited_mask,
            last_country_idx=last_country,
            completed=completed,
            total_scans=total_scans,
            visit_counters=visit_counters,
        )

    @classmethod
    def blank(cls) -> "PassportChip":
        """Prázdný pas - jak vypadá nově registrovaný pas před vyplněním."""
        return cls()


def is_blank_chip(data: bytes) -> bool:
    """
    Detekuje, zda je čip prázdný (nikdy nezapsaný).
    Prázdný NTAG213 má v user memory typicky 0x00 bajty.
    """
    if not data:
        return True
    # Pokud první 4 byty (kde má být magic + version) jsou 0x00 nebo 0xFF
    head = data[:4]
    return head == b"\x00\x00\x00\x00" or head == b"\xFF\xFF\xFF\xFF"
