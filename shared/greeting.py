"""
Generování uvítacích vět na základě dat z čipu.

Hlavní rozdíl oproti síťové verzi: nemáme přístup k centrální DB scanů.
Vše vychází z dat na čipu (last_country_idx, visit_counters, visited_mask).

Pravidla:
  A) Pokud cestovatel ještě nebyl v žádné zemi a poprvé na této zemi:
       "Ahoj {jméno}, vítej {kde}! Jsme rádi, že si začal/a cestovat s námi."

  A2) Pokud cestovatel už byl v jiné zemi, ale poprvé v této:
       "Ahoj {jméno}, vítej {kde}! Jak bylo {kde předchozí}?"

  B) Opakovaná návštěva téže země:
       "Vítej zpět {kde}, {jméno}. Letos už si u nás byl/a {X}krát."

  C) Dokončení (právě navštívil 11. unikátní zemi):
       "Gratulujeme, {jméno}! Úspěšně si dokončil/a cestu kolem světa.
        Doufáme, že sis to moc užil/a a navíc si podpořil/a malého Ondráška,
        za což ti patří velké díky. Užij si zbytek dne. Tým Srdcem pro…"
"""
from typing import Optional

from countries import COUNTRIES, Country, get_country_by_index
from passport_chip import NO_LAST_COUNTRY, PassportChip


def _verb_past(gender: str, masculine: str, feminine: str) -> str:
    return masculine if gender == "M" else feminine


def build_greeting_for_visit(
    chip: PassportChip,
    current_country_idx: int,
) -> tuple[str, bool]:
    """
    Vrátí (greeting_text, is_completion).

    DŮLEŽITÉ: tato funkce se volá PŘED zápisem na čip, takže `chip` stále
    odráží stav před touto návštěvou. To je správně - potřebujeme to vědět
    pro rozhodnutí, zda je to první/opakovaná/dokončující návštěva.
    """
    country = get_country_by_index(current_country_idx)
    if country is None:
        raise ValueError(f"Invalid country index: {current_country_idx}")

    first_name = chip.first_name
    gender = chip.gender
    visits_before = chip.visits_to(current_country_idx)
    unique_before = chip.unique_countries_visited

    # Bude tato návštěva dokončující?
    # = je to první návštěva této země (přidá +1 do unique) a unique_before == 10
    is_new_country = visits_before == 0
    will_be_completion = (
        is_new_country
        and unique_before + 1 == len(COUNTRIES)
        and not chip.completed  # ještě nikdy nedokončil
    )

    if will_be_completion:
        return _greeting_completion(first_name, gender), True

    # Opakovaná návštěva
    if visits_before > 0:
        visit_count = visits_before + 1
        return (
            _greeting_repeated(first_name, gender, country, visit_count),
            False,
        )

    # První návštěva této země
    if chip.last_country_idx == NO_LAST_COUNTRY:
        # Cestovatel přichází přímo z registrace
        return _greeting_first_no_prior(first_name, gender, country), False
    else:
        prev_country = get_country_by_index(chip.last_country_idx)
        if prev_country is None:
            # Pokud byl nějaký invalid index, chovej se jako bez předchozí
            return _greeting_first_no_prior(first_name, gender, country), False
        return (
            _greeting_first_with_prior(first_name, country, prev_country),
            False,
        )


def _greeting_first_no_prior(first_name: str, gender: str, country: Country) -> str:
    started = _verb_past(gender, "začal", "začala")
    return (
        f"Ahoj {first_name}, vítej {country.locative_cz}! "
        f"Jsme rádi, že si {started} cestovat s námi."
    )


def _greeting_first_with_prior(
    first_name: str, country: Country, prev_country: Country
) -> str:
    return (
        f"Ahoj {first_name}, vítej {country.locative_cz}! "
        f"Jak bylo {prev_country.locative_cz}?"
    )


def _greeting_repeated(
    first_name: str, gender: str, country: Country, visit_count: int
) -> str:
    been = _verb_past(gender, "byl", "byla")
    return (
        f"Vítej zpět {country.locative_cz}, {first_name}. "
        f"Letos už si u nás {been} {visit_count}krát."
    )


def _greeting_completion(first_name: str, gender: str) -> str:
    completed = _verb_past(gender, "dokončil", "dokončila")
    enjoyed = _verb_past(gender, "užil", "užila")
    supported = _verb_past(gender, "podpořil", "podpořila")
    return (
        f"Gratulujeme, {first_name}! Úspěšně si {completed} cestu kolem světa. "
        f"Doufáme, že sis to moc {enjoyed} a navíc si {supported} malého Ondráška, "
        f"za což ti patří velké díky. Užij si zbytek dne. Tým Srdcem pro…"
    )
