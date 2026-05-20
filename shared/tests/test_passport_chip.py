"""Testy pro passport_chip - kritická komponenta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passport_chip import (
    CHIP_SIZE,
    MAGIC_BYTE,
    MAX_COUNTRIES,
    NO_LAST_COUNTRY,
    ChipDataError,
    PassportChip,
    _crc8,
    is_blank_chip,
)


def test_crc8_basic():
    # Známé hodnoty CRC-8 (poly 0x07, init 0x00)
    assert _crc8(b"") == 0
    assert _crc8(b"A") == 0xC0
    # Self-consistency
    assert _crc8(b"hello") == _crc8(b"hello")
    print("✓ CRC8 funguje")


def test_blank_chip_serialization():
    """Blank chip se musí dát serializovat a deserializovat."""
    chip = PassportChip.blank()
    data = chip.to_bytes()
    assert len(data) == CHIP_SIZE
    assert data[0] == MAGIC_BYTE
    
    # Round-trip
    restored = PassportChip.from_bytes(data)
    assert restored.first_name == ""
    assert restored.gender == "M"
    assert restored.unique_countries_visited == 0
    print("✓ Blank chip round-trip funguje")


def test_full_passport_serialization():
    """Pas s daty - kompletní round-trip."""
    chip = PassportChip(
        first_name="Eliška",
        gender="F",
        birth_year=2014,
    )
    chip.record_visit(0)  # Japonsko
    chip.record_visit(1)  # Brazílie
    chip.record_visit(0)  # zpět do Japonska

    data = chip.to_bytes()
    assert len(data) == CHIP_SIZE

    restored = PassportChip.from_bytes(data)
    assert restored.first_name == "Eliška"
    assert restored.gender == "F"
    assert restored.birth_year == 2014
    assert restored.visits_to(0) == 2
    assert restored.visits_to(1) == 1
    assert restored.visits_to(2) == 0
    assert restored.last_country_idx == 0
    assert restored.unique_countries_visited == 2
    assert restored.total_scans == 3
    assert not restored.completed
    print("✓ Pas s daty round-trip funguje:", restored.first_name)


def test_utf8_name_with_haceks():
    """České jméno s háčky se musí vejít a správně dekódovat."""
    chip = PassportChip(first_name="Žofie", gender="F", birth_year=2015)
    data = chip.to_bytes()
    restored = PassportChip.from_bytes(data)
    assert restored.first_name == "Žofie"
    print("✓ UTF-8 jméno Žofie funguje")

    chip = PassportChip(first_name="Štěpán", gender="M", birth_year=2014)
    data = chip.to_bytes()
    restored = PassportChip.from_bytes(data)
    assert restored.first_name == "Štěpán"
    print("✓ UTF-8 jméno Štěpán funguje")


def test_long_name_gets_truncated():
    """Dlouhé jméno se musí oříznout, ale ne uprostřed UTF-8 sekvence (TBD)."""
    chip = PassportChip(first_name="Aleksandrina", gender="F", birth_year=2014)
    data = chip.to_bytes()
    restored = PassportChip.from_bytes(data)
    # Jméno bude oříznuto na max 15 bajtů
    assert len(restored.first_name) > 0
    assert restored.first_name.startswith("Aleksand")
    print(f"✓ Dlouhé jméno oříznuto: '{restored.first_name}'")


def test_completion_detection():
    """Po 11 unikátních zemích completed = True."""
    chip = PassportChip(first_name="Pavel", gender="M", birth_year=2014)
    for i in range(11):
        chip.record_visit(i)
    assert chip.completed
    assert chip.unique_countries_visited == 11

    data = chip.to_bytes()
    restored = PassportChip.from_bytes(data)
    assert restored.completed
    print("✓ Dokončení detekováno")


def test_repeated_visits_counter():
    """Counter musí saturovat na 255."""
    chip = PassportChip(first_name="X", gender="M")
    for _ in range(300):
        chip.record_visit(5)
    assert chip.visits_to(5) == 255
    print("✓ Visit counter saturuje na 255")


def test_invalid_magic_byte():
    """Cizí čip musí vyhodit chybu."""
    bad_data = bytes([0xAA] * CHIP_SIZE)
    try:
        PassportChip.from_bytes(bad_data)
        assert False, "Měla nastat ChipDataError"
    except ChipDataError as e:
        assert "magic" in str(e).lower()
    print("✓ Cizí čip správně odmítnut")


def test_corrupted_crc():
    """Poškozený CRC musí být detekován."""
    chip = PassportChip(first_name="Pavel", gender="M", birth_year=2014)
    data = bytearray(chip.to_bytes())
    # Změň jeden byte v jméně, ale ne CRC
    data[24] = (data[24] + 1) & 0xFF
    try:
        PassportChip.from_bytes(bytes(data))
        assert False, "Mělo selhat CRC"
    except ChipDataError as e:
        assert "crc" in str(e).lower()
    print("✓ Porušený CRC detekován")


def test_blank_chip_detection():
    """is_blank_chip detekuje nezapsaný NTAG."""
    assert is_blank_chip(b"\x00" * 64)
    assert is_blank_chip(b"\xFF" * 64)
    assert not is_blank_chip(PassportChip(first_name="X", gender="M").to_bytes())
    print("✓ Detekce prázdného čipu funguje")


def test_business_flow():
    """Simulace celé cesty cestovatele."""
    # 1. Registrace
    chip = PassportChip(first_name="Tomáš", gender="M", birth_year=2014)
    assert chip.is_registered
    assert chip.unique_countries_visited == 0

    # 2. První stanoviště (Japonsko = index 0)
    chip.record_visit(0)
    assert chip.visits_to(0) == 1
    assert chip.last_country_idx == 0

    # 3. Druhé (Brazílie = 1)
    chip.record_visit(1)
    assert chip.last_country_idx == 1
    assert chip.unique_countries_visited == 2

    # 4. Návrat do Japonska
    chip.record_visit(0)
    assert chip.visits_to(0) == 2
    assert chip.last_country_idx == 0  # nyní zase Japonsko
    assert chip.unique_countries_visited == 2  # stále 2 unikátní

    # 5. Dokončení - zbývajících 9 zemí
    for i in range(2, 11):
        chip.record_visit(i)
    assert chip.completed
    assert chip.unique_countries_visited == 11

    # 6. Round-trip přes bajty
    data = chip.to_bytes()
    restored = PassportChip.from_bytes(data)
    assert restored.completed
    assert restored.visits_to(0) == 2
    assert restored.last_country_idx == 10  # poslední byla Antarktida
    print("✓ Kompletní business flow")


def test_size_check():
    """Buffer musí být přesně 64 B."""
    chip = PassportChip(first_name="Žofie", gender="F", birth_year=2014)
    assert len(chip.to_bytes()) == CHIP_SIZE
    # I prázdný
    assert len(PassportChip.blank().to_bytes()) == CHIP_SIZE
    print(f"✓ Velikost dat vždy {CHIP_SIZE} B")


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n✅ Všech {len(tests)} testů prošlo.")
