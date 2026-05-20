"""Testy uvítacích vět - chipový model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greeting import build_greeting_for_visit
from passport_chip import PassportChip


def test_first_visit_from_registration():
    """A1: První návštěva po registraci (žádná předchozí země)."""
    chip = PassportChip(first_name="Tomáš", gender="M", birth_year=2014)
    # USA Hawaii = idx 0
    greeting, is_done = build_greeting_for_visit(chip, 0)
    assert "Ahoj Tomáš" in greeting
    assert "na Havaji" in greeting
    assert "začal cestovat" in greeting
    assert not is_done
    print("✓ A1 male:", greeting)


def test_first_visit_female():
    chip = PassportChip(first_name="Eliška", gender="F")
    greeting, _ = build_greeting_for_visit(chip, 0)
    assert "začala cestovat" in greeting
    print("✓ A1 female:", greeting)


def test_first_visit_with_prior():
    """A2: První návštěva této země, ale už byl jinde."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    chip.record_visit(0)  # nejdřív Hawaii
    # Teď jde do Francie (idx 1)
    greeting, is_done = build_greeting_for_visit(chip, 1)
    assert "Ahoj Tomáš" in greeting
    assert "ve Francii" in greeting
    assert "Jak bylo na Havaji" in greeting
    assert not is_done
    print("✓ A2:", greeting)


def test_repeated_visit():
    """B: Návrat do téže země."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    chip.record_visit(2)  # Japonsko
    # Teď zase Japonsko
    greeting, is_done = build_greeting_for_visit(chip, 2)
    assert "Vítej zpět" in greeting
    assert "v Japonsku" in greeting
    assert "byl 2krát" in greeting
    print("✓ B male:", greeting)


def test_repeated_visit_female():
    chip = PassportChip(first_name="Eliška", gender="F")
    chip.record_visit(2)
    chip.record_visit(2)
    # Teď třetí návštěva
    greeting, _ = build_greeting_for_visit(chip, 2)
    assert "byla 3krát" in greeting
    print("✓ B female:", greeting)


def test_completion_male():
    """C: Dokončení."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    # Navštívil 10 zemí (0-9)
    for i in range(10):
        chip.record_visit(i)
    # Teď 11. země (Antarktida = idx 10)
    greeting, is_done = build_greeting_for_visit(chip, 10)
    assert "Gratulujeme, Tomáš" in greeting
    assert "dokončil cestu kolem světa" in greeting
    assert "užil" in greeting
    assert "podpořil" in greeting
    assert "Ondráška" in greeting
    assert is_done
    print("✓ C male:", greeting)


def test_completion_female():
    chip = PassportChip(first_name="Eliška", gender="F")
    for i in range(10):
        chip.record_visit(i)
    greeting, is_done = build_greeting_for_visit(chip, 10)
    assert "dokončila" in greeting
    assert "užila" in greeting
    assert "podpořila" in greeting
    assert is_done
    print("✓ C female:", greeting)


def test_no_double_completion():
    """Pokud už dokončil, druhý průchod 11. zemí nedá completion znovu."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    for i in range(11):
        chip.record_visit(i)
    assert chip.completed
    # Teď znovu přijde na Antarktidu
    greeting, is_done = build_greeting_for_visit(chip, 10)
    # Mělo by to být "Vítej zpět" varianta B, ne dokončení
    assert "Vítej zpět" in greeting
    assert "byl 2krát" in greeting
    assert not is_done
    print("✓ No double completion:", greeting)


def test_all_locatives():
    """Ověř, že všechny lokativy 11 zemí jsou validní (žádný 'v X' kde má být 'na X')."""
    chip = PassportChip(first_name="Test", gender="M")
    from countries import COUNTRIES
    for c in COUNTRIES:
        # Reset chip
        fresh = PassportChip(first_name="Test", gender="M")
        greeting, _ = build_greeting_for_visit(fresh, c.index)
        # Lokativ musí být v greetingu doslova
        assert c.locative_cz in greeting, (
            f"Země {c.name_cz}: lokativ '{c.locative_cz}' "
            f"chybí ve větě: {greeting}"
        )
        print(f"  ✓ {c.name_cz}: {c.locative_cz} → {greeting[:60]}...")


def test_completion_at_correct_country():
    """Dokončení může nastat jen při poslední unikátní zemi."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    # Navštíví 9 zemí
    for i in range(9):
        chip.record_visit(i)
    # 10. země - ještě ne dokončeno
    _, is_done = build_greeting_for_visit(chip, 9)
    assert not is_done
    # Po zápisu 10. země
    chip.record_visit(9)
    # 11. země - teď dokončeno
    _, is_done = build_greeting_for_visit(chip, 10)
    assert is_done
    print("✓ Dokončení přesně při 11. zemi")


def test_completion_not_at_repeated():
    """Návrat do už navštívené země nedá completion, i když je to 11. scan."""
    chip = PassportChip(first_name="Tomáš", gender="M")
    # Navštíví 10 různých
    for i in range(10):
        chip.record_visit(i)
    # 11. scan, ale opakování země 0
    greeting, is_done = build_greeting_for_visit(chip, 0)
    assert not is_done
    assert "Vítej zpět" in greeting
    print("✓ Opakovaný scan nedělá completion:", greeting)


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n✅ Všech {len(tests)} greeting testů prošlo.")
