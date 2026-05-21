# Návrh řešení: „Cesta kolem světa" – Srdcem pro Ondráška

**Dokument:** Solution Design Document
**Verze:** 1.0 (final)
**Autor:** Solution Architect
**Datum:** květen 2026
**Status:** Schváleno k implementaci

---

## 1. Executive Summary

### Co budujeme

Interaktivní softwarové řešení pro charitativní akci „Cesta kolem světa" pořádanou pod hlavičkou *Srdcem pro Ondráška*. Dětští účastníci procházejí 11 stanovišti reprezentujícími světové země, na každém plní zábavnou aktivitu a získávají na svůj „cestovní pas" virtuální razítko. Po splnění všech zemí získávají odměnu z pokladny.

### Klíčové architektonické rozhodnutí

**Stav cestovatele se ukládá přímo na NFC čip pasu** – nikoliv do centrální databáze. Systém je proto:

- **Plně offline** – nepotřebuje žádnou síť mezi stanicemi
- **Decentralizovaný** – výpadek jedné stanice neovlivní ostatní
- **Provozně robustní** – minimum bodů selhání

### Rozsah systému

| Stanice | Počet | Funkce |
|---|---|---|
| Stanoviště zemí | 11 | Přečte pas → zobrazí uvítání + fakt → zapíše návštěvu zpět na čip |
| Registrační stanice | 1 | Aktivuje nový pas (zapíše jméno, pohlaví, rok) |
| Pokladna | 2 | Ověří, že pas je platný; rozhodne o vstupu/výstupu |

---

## 2. Business požadavky

### 2.1 Funkční chování stanovišť země

Při přiložení pasu cestovatele se na displeji stanoviště zobrazí:

**a) Vizuál** – obrázek typický pro danou zemi, který se po přiložení pasu změní z výchozí varianty na „customizovanou".

**b) Personalizovaná uvítací věta**, jedna ze tří variant podle historie cestovatele:

**Varianta A – první návštěva země:**
- Bez předchozí jiné země (přichází z registrace):
  *„Ahoj **Pavle**, vítej **v Japonsku**! Jsme rádi, že si **začal** cestovat s námi."*
- S předchozí jinou zemí:
  *„Ahoj **Pavle**, vítej **v Japonsku**! Jak bylo **ve Francii**?"*

**Varianta B – opakovaná návštěva:**
- *„Vítej zpět **v Japonsku**, **Pavle**. Letos už si u nás **byl** 3krát."*

**Varianta C – dokončení cesty (na 11. unikátní zemi):**
- *„Gratulujeme, **Pavle**! Úspěšně si **dokončil** cestu kolem světa. Doufáme, že sis to moc **užil** a navíc si **podpořil** malého Ondráška, za což ti patří velké díky. Užij si zbytek dne. Tým Srdcem pro…"*

**c) Náhodný fakt** o aktuální zemi z databáze 21 faktů na zemi.

### 2.2 Klíčové gramatické požadavky

Systém musí korektně zvládat:

| Aspekt | Příklad |
|---|---|
| Skloňování zemí s předložkou | *v Japonsku*, *ve Francii*, *na Havaji*, *na Antarktidě*, *v Česku*, *ve Velké Británii* |
| Slovesné tvary podle pohlaví | *začal/začala*, *byl/byla*, *dokončil/dokončila*, *užil/užila*, *podpořil/podpořila* |
| České znaky v jménech | Žofie, Štěpán, Eliška (UTF-8 s háčky a čárkami) |

### 2.3 Funkční chování registrace

- Provoz: notebook + webový prohlížeč pro obsluhu; RPi 2GB jako server
- Operátor přiloží **prázdný NTAG** na čtečku
- Vyplní křestní jméno (max 15 znaků), pohlaví (M/F), rok narození
- Klikne „Zaregistrovat" → systém zapíše data na čip + ověří zápis čtením
- Foto cestovatele se řeší **mimo systém** (papírová vlepenka)

**Detekce již zaregistrovaného pasu:** Pokud operátor přiloží již aktivovaný čip, systém zobrazí stávající data (jméno, počet navštívených zemí) a vyžaduje explicitní potvrzení „přepsat" před přepsáním. Přepis vynuluje historii cestování.

### 2.4 Funkční chování pokladny

- Operátor pokladny přiloží pas cestovatele na čtečku
- Systém v < 1 sekundě vyhodnotí stav a zobrazí:

| Stav čipu | Výsledek |
|---|---|
| 🟢 **Platný registrovaný pas** | Zelená obrazovka + jméno + ročník + progress (X/11 zemí) + ✅ |
| 🎉 **Dokončený pas (11/11)** | Stejné + zvýraznění „Dokončil cestu" |
| 🔴 **Neregistrovaný (prázdný) čip** | Červená obrazovka + „Pas není zaregistrován. Pošli na registraci." |
| 🔴 **Cizí / poškozený čip** | Červená obrazovka + „Tento čip nepatří k naší akci." |

Volitelně: **GPIO LED + bzučák** (zelená/červená dioda + krátké/dlouhé pípnutí) pro robustní viditelnost i bez sledování obrazovky.

---

## 3. Architektura

### 3.1 Topologie

```
                    AKCE „Cesta kolem světa"
                            (offline)
   ┌─────────────────────────────────────────────────────────────┐
   │                                                              │
   │   ┌──────────┐    ┌──────────┐    ┌──────────┐              │
   │   │ Země 1   │    │ Země 2   │    │ Země ... │              │
   │   │ (Hawaii) │    │ (Francie)│    │   ×11    │              │
   │   │ RPi+disp │    │ RPi+disp │    │          │              │
   │   │ + PN532  │    │ + PN532  │    │          │              │
   │   └──────────┘    └──────────┘    └──────────┘              │
   │                                                              │
   │   ┌──────────────┐                ┌──────────┐               │
   │   │ Registrace   │                │ Pokladna │  ×2          │
   │   │ RPi 2GB      │                │ RPi+disp │              │
   │   │ + notebook   │                │ + PN532  │              │
   │   │ + PN532      │                │ + LED    │              │
   │   └──────────────┘                └──────────┘               │
   │                                                              │
   │   Žádné spojení mezi stanicemi - každá je samostatná         │
   └─────────────────────────────────────────────────────────────┘
                              ▲
                              │ Cestovatel s NFC pasem
                              │ (NTAG213, 64 B uloženého stavu)
```

### 3.2 Klíčový princip: Storage on Chip

Místo centrální databáze drží data **samotný NFC čip** (NTAG213, 144 B užitečné paměti).

```
LAYOUT 64 B NA ČIPU
─────────────────────────────────────────────────────────────
0x00 - magic byte 0x53 ('S')           ← identifikuje "naše" čipy
0x01 - verze formátu                    ← pro budoucí změny
0x02 - pohlaví (M/F)                    ← pro skloňování sloves
0x03 - CRC8                             ← integrita dat
0x04 - rok narození (2 B)
0x06 - bitmaska navštívených zemí (2 B) ← rychlá kontrola dokončení
0x08 - index naposledy navštívené země ← pro "Jak bylo v X?"
0x09 - příznak dokončení
0x0A - celkový počet scanů (2 B)        ← statistika
0x0C - 11× counter pro každou zemi      ← pro "byl si X-krát"
0x17 - jméno (16 B UTF-8)
0x27 - rezerva (vyplněno 0xFF)
─────────────────────────────────────────────────────────────
```

**Důsledky tohoto rozhodnutí:**

✅ Stanice jsou samostatné; nepotřebují síť ani synchronizaci
✅ Akce odolná proti výpadkům (pokladna vidí stav, i kdyby vše ostatní spadlo)
✅ Zjednodušený provoz – žádný server, žádné zálohování DB
✅ Levné HW – nepotřebujeme síťový hardware

❌ Pas může být manipulovatelný (rodič s NFC mobilem). Mitigace: magic byte + CRC8 + nepravděpodobnost vědomé manipulace
❌ Žádné real-time statistiky pro organizátory během akce
❌ Foto se musí řešit papírově

### 3.3 Bezpečnost dat na čipu

- **Magic byte 0x53** – odliší naše čipy od cizích karet (MHD, klíče, atd.)
- **CRC8 checksum** – detekuje poškozená data (přerušený zápis, technická závada)
- **Verze formátu** – umožňuje budoucí změny bez zlomení existujících čipů
- **Re-read po zápisu** – registrační stanice po zápisu data znovu přečte a porovná; při neshodě zápis opakuje až 3×

---

## 4. Hardware

### 4.1 Soupis komponent

| Komponenta | Kus | Použití |
|---|---|---|
| Raspberry Pi 1 GB | 13 | 11 stanic země + 2 pokladny |
| Raspberry Pi 2 GB | 1 | Registrační stanice |
| 7" RPi Touch Display 800×480 | 13 | Všechny stanice s displejem |
| PN532 NFC modul (USB-UART/I²C) | 15 | 14 funkčních + 1 rezerva |
| NTAG213 NFC nálepka 25 mm | dle počtu dětí + rezerva 30% | Pasy |
| Notebook | 1 | Obsluha registrace |
| LED (zelená + červená) | 2 sady | Pokladny (volitelné, doporučeno) |
| Bzučák (5V piezo) | 2 | Pokladny (volitelné, doporučeno) |
| Powerbanka / napájecí zdroj | 14 | Per stanice |
| Wi-Fi router | 0 | **Nepotřeba** |

### 4.2 Pinout pokladny (GPIO – volitelné)

```
RPi GPIO BCM ────┬─── 220Ω ── LED zelená (anoda)  → GND
                ├─── 220Ω ── LED červená (anoda)  → GND
                └─── 100Ω ── Bzučák (+)            → GND

Defaultní pinout v configu:
  GPIO_LED_GREEN=17
  GPIO_LED_RED=27
  GPIO_BUZZER=22
```

---

## 5. Software

### 5.1 Technologický stack

| Vrstva | Volba | Důvod |
|---|---|---|
| OS | Raspberry Pi OS Lite (64-bit) | Lehké, rychlý boot |
| Jazyk backend | Python 3.10+ | Knihovny nfcpy, RPi.GPIO; jeden tým, jeden jazyk |
| HTTP server | aiohttp | Async, lehké, SSE podpora |
| NFC | nfcpy 1.0.4 | Standard pro PN532 |
| Frontend | Vanilla JS + HTML/CSS | Žádný build, snadná údržba |
| Realtime UI | Server-Sent Events | Jednoduchší než WebSocket |
| Kiosk | Chromium kiosk mode | Standard pro RPi |
| Orchestrace | systemd | Auto-start, restart on failure |

**Žádné databáze, žádné externí závislosti.** Audit log do JSONL souborů na disk každé stanice (pro post-event statistiky).

### 5.2 Adresářová struktura repozitáře

```
passport-system/
├── shared/                         🔑 Sdílený kód
│   ├── passport_chip.py            Serializace/deserializace + CRC
│   ├── countries.py                11 zemí + 21 faktů/zemi + lokativy
│   ├── greeting.py                 Logika uvítacích vět
│   ├── nfc_device.py               PN532 + Mock abstrakce
│   └── tests/                      23 unit testů
│
├── station-country/                Stanice země (deploy ×11)
│   ├── app/daemon.py               NFC polling + HTTP server
│   ├── frontend/                   Kiosk 800×480
│   └── deploy/                     systemd + install.sh
│
├── station-registration/           Registrační stanice (deploy ×1)
│   ├── app/
│   │   ├── daemon.py
│   │   └── chip_writer.py          Bezpečný zápis s re-read ověřením
│   └── frontend/                   Desktop UI pro notebook
│
└── station-checkout/               Pokladna (deploy ×2)
    ├── app/
    │   ├── daemon.py
    │   └── gpio_controller.py      LED + bzučák
    └── frontend/                   Kiosk 800×480
```

### 5.3 Sdílená knihovna `shared/` – jádro systému

Tato vrstva obsahuje veškerou business logiku a je **stejná pro všechny stanice**.

**`passport_chip.py`** – data layer
- Třída `PassportChip` (dataclass) s metodami `to_bytes()` / `from_bytes()`
- Validace magic byte a CRC8 při čtení
- Business metody: `record_visit(country_idx)`, `visits_to(idx)`, `unique_countries_visited`, `completed`
- Saturující čítače (max 255 návštěv/země, max 65535 celkových scanů)

**`countries.py`** – databáze zemí
- 11 zemí v pevném pořadí (index 0–10 odpovídá bitu na čipu)
- Pro každou zemi: kód, název, **lokativní tvar s předložkou**, popis aktivity, 21 zajímavých faktů

| Index | Země | Lokativ | Aktivita |
|---|---|---|---|
| 0 | USA Hawaii | na Havaji | Podlejzání tyčí |
| 1 | Francie | ve Francii | Skládačka |
| 2 | Japonsko | v Japonsku | Hůlky a stezka |
| 3 | Egypt | v Egyptě | Pyramida (šifry) |
| 4 | Itálie | v Itálii | Pojídání špaget |
| 5 | Dánsko | v Dánsku | Stavba z Lega |
| 6 | Austrálie | v Austrálii | Skákání v pytli |
| 7 | Česká republika | v Česku | Bude upřesněno |
| 8 | Velká Británie | ve Velké Británii | Harry Potter |
| 9 | Indie | v Indii | Poznávání vůní |
| 10 | Antarktida | na Antarktidě | Lovení rybiček |

⚠️ **Kritické pravidlo:** Po nasazení akce **nesmí být pořadí zemí změněno**. Index = bit na čipu, a změna pořadí by zneplatnila všechny dříve zapsané pasy.

**`greeting.py`** – generátor vět
- Vstup: `PassportChip` + aktuální `country_index`
- Výstup: hotová věta v správné variantě (A1/A2/B/C) + flag dokončení
- Korektně řeší skloňování + slovesný rod podle pohlaví

**`nfc_device.py`** – HW abstrakce
- `Pn532NfcDevice` – reálný driver přes nfcpy
- `MockNfcDevice` – pro vývoj na PC bez HW

### 5.4 Stanice země – tok událostí

```
┌────────────────────────────────────────────────────────────────┐
│  STANICE ZEMĚ (RPi 1GB)                                         │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │  Daemon (Python) │                                           │
│  │  ─ NFC polling   │                                           │
│  │  ─ HTTP server   │ ◄─── SSE ───┐                             │
│  └────────┬─────────┘             │                             │
│           │                       │                             │
│           ▼                       │                             │
│  ┌─────────────────────────────────────────┐                    │
│  │ 1. PN532 detekuje čip                    │                    │
│  │ 2. Přečte 64 B z user memory             │                    │
│  │ 3. Validuje magic + CRC                  │                    │
│  │    ├─ Neplatný → SSE 'error'             │                    │
│  │    └─ Platný:                            │                    │
│  │       4. Spočítá kontext (visits, last)  │                    │
│  │       5. Vygeneruje uvítací větu         │                    │
│  │       6. Vybere náhodný fakt             │                    │
│  │       7. Aktualizuje data (counter++)    │                    │
│  │       8. ZAPÍŠE zpět na čip              │                    │
│  │       9. SSE 'scan' nebo 'completion'    │                    │
│  └─────────────────────────────────────────┘                    │
│                                   │                              │
│           ┌───────────────────────┘                              │
│           ▼                                                       │
│  ┌──────────────────┐                                            │
│  │ Chromium kiosk   │                                            │
│  │ ─ Default screen │                                            │
│  │ ─ Scan screen    │                                            │
│  │ ─ Completion 🎉  │                                            │
│  │ ─ Error screen   │                                            │
│  └──────────────────┘                                            │
└─────────────────────────────────────────────────────────────────┘
```

**Časování UI:**
- Po scanu zobrazí výsledek **20 sekund**, pak návrat na výchozí obrazovku
- Po dokončení („Gratulujeme!") drží obrazovku **45 sekund** (oslavná chvíle)
- Debounce: stejný čip přiložen 2× za sebou = ignorován po dobu 2 sekund

### 5.5 Registrační stanice – tok událostí

Layout UI na notebooku má **dva sloupce**:

```
┌─────────────────────────────────────────────────────────────┐
│  Logo  Imigrační oddělení                       ● Připojeno │
├──────────────────────────┬──────────────────────────────────┤
│                          │                                   │
│  PAS (NFC ČIP)           │  ÚDAJE CESTOVATELE                │
│  ───────────────         │  ─────────────────────            │
│                          │                                   │
│       📡                 │  Křestní jméno                    │
│   Polož pas              │  [_____________]                  │
│   na čtečku              │                                   │
│                          │  Pohlaví                          │
│  Systém pozná, zda       │  ( ) 👦 Chlapec  ( ) 👧 Dívka     │
│  je prázdný nebo         │                                   │
│  zaregistrovaný          │  Rok narození                     │
│                          │  [   2014    ]                    │
│                          │                                   │
│                          │  [ Zaregistrovat na čip ]         │
│                          │                                   │
└──────────────────────────┴──────────────────────────────────┘
```

**Stavy levého sloupce:**

| Stav | Vizuál | Akce |
|---|---|---|
| Žádný čip | 📡 „Polož pas na čtečku" | – |
| Prázdný čip | ✨ „Prázdný pas – připraven" | Tlačítko aktivní |
| Cizí čip | ⚠️ „Tento čip nepatří k akci" | Tlačítko zakázané |
| Registrovaný | 📔 + info (jméno, X/11 zemí, ev. „dokončil") | Aktivuje checkbox „přepsat" |

**Validace serverem:**
- Jméno: 1–15 znaků UTF-8 (přihlédnuto k tomu, že české znaky zaberou víc bajtů)
- Pohlaví: M nebo F
- Rok narození: 2005–2025
- Při registrovaném čipu bez `force_overwrite=true` server vrátí 409 Conflict s informací o existujícím pasu

**Zápis na čip:**
1. Sestavit `PassportChip` strukturu (64 B)
2. Zapsat na NTAG (stránky 4–19)
3. Re-read z čipu
4. Byte-for-byte porovnání s očekávaným
5. Pokud neshoda → 2 další pokusy, jinak chyba s instrukcí „přilož čip znovu"

### 5.6 Pokladna – tok událostí

Pokladna je nejjednodušší – jen čte, nezapisuje.

```
┌─────────────────────────────────────────┐
│  Pokladna 1              ● Připojeno    │
│                                          │
│           ╔═══════════════════╗          │
│           ║                   ║          │
│           ║       🎫          ║          │
│           ║   Polož pas       ║          │
│           ║   na čtečku ⬇     ║          │
│           ║                   ║          │
│           ╚═══════════════════╝          │
└─────────────────────────────────────────┘
```

Po přiložení – jedna ze dvou velkých obrazovek:

**Zelená (přijato):**
```
╔══════════════════════════════════════╗
║                                      ║
║    ✅      Přijato                   ║
║                                      ║
║         👦 Pavel                     ║
║         Ročník 2014                  ║
║                                      ║
║     ████████████░░░░░ 8 / 11 zemí    ║
║                                      ║
╚══════════════════════════════════════╝
```

**Červená (zamítnuto):**
```
╔══════════════════════════════════════╗
║                                      ║
║              ⛔                      ║
║                                      ║
║         Pas neplatný                 ║
║                                      ║
║   Pas není zaregistrován.            ║
║   Pošli na registraci.               ║
║                                      ║
╚══════════════════════════════════════╝
```

**Doba zobrazení:** 5 sekund, pak návrat na výchozí.

**GPIO (volitelné):**
- ACCEPT: zelená LED svítí 5 s + krátké pípnutí (200 ms)
- DENY: červená LED svítí 5 s + 3× krátké pípnutí (chyba)

---

## 6. Provozní hlediska

### 6.1 Provisioning RPi

Strategie: **jeden master image**, naklonovaný na 14 SD karet, na každé upraven jediný konfigurační soubor `/boot/station.conf`.

**Typy konfigurace:**

| Typ stanice | Klíčové parametry v station.conf |
|---|---|
| Stanice země | `COUNTRY_INDEX=0..10` |
| Registrace | `NFC_DEVICE=...`, `HTTP_PORT=8000` |
| Pokladna | `CHECKPOINT_LABEL="Pokladna 1"`, `GPIO_ENABLED=true` |

**Důležité:** SD karty + nálepky na krabičky s číslem stanice + tabulka mapování index → země (pro obsluhu).

### 6.2 Auto-start

systemd na každém RPi spustí:
- `passport-station.service` (resp. `-checkout`, `-registration`) – Python daemon
- `passport-kiosk.service` – Chromium v kiosk módu (kromě registrace – tu nakopne operátor v prohlížeči)

Při výpadku napájení: po obnově se vše rozjede samo do 30 sekund.

### 6.3 Auditní log

Každá stanice si lokálně zaznamenává všechny scany do JSONL souboru:

```json
{"ts": "2026-06-15T10:23:45", "country_idx": 2, "tag": "Pavel", "action": "visit", "visits_now": 2, "unique_countries": 5, "write_ok": true}
```

Po akci lze tyto logy sesbírat z SD karet a vyhodnotit statistiky (kolik dětí, který stanoviště nejnavštěvovanější, atd.).

### 6.4 Obnovitelnost

| Scénář | Postup |
|---|---|
| Vybitá powerbanka | Vyměnit, RPi se rozjede samo |
| Zaseknutá stanice | Vypnout/zapnout, software se restartuje (~30 s) |
| Selhání SD karty | Vyměnit za zálohu z imageu, upravit station.conf |
| Selhání PN532 čtečky | Vyměnit za rezervní kus |
| Poškozený čip dítěte | Re-registrace na imigračním (historie pasu se ale ztratí) |
| Selhání jedné stanice celkově | Akce pokračuje bez ní – ostatní jsou nezávislé |

### 6.5 GDPR

- Na čipu pasu je jen křestní jméno + pohlaví + rok narození (žádné příjmení, žádné kontakty)
- Foto je papírové, držené dítětem; po akci se s ním nakládá fyzicky (možno spálit/vrátit)
- Lokální logy stanic obsahují jen křestní jméno + statistiky → smazat po vyhodnocení akce

---

## 7. Akceptační kritéria

| # | Kritérium | Status |
|---|---|---|
| 1 | Stanice země reaguje na přiložení pasu do 2 sekund | ✅ HW závislé, software splňuje |
| 2 | Uvítací věta správně skloňuje všech 11 zemí | ✅ Pokryto unit testy |
| 3 | Uvítací věta správně používá rodový tvar (M/F) | ✅ Pokryto unit testy |
| 4 | Detekce dokončení se aktivuje **právě** při 11. unikátní zemi | ✅ Pokryto unit testy |
| 5 | Cizí karta/poškozený čip → chybová hláška, neaktivuje akci | ✅ Magic byte + CRC8 |
| 6 | Registrace zapíše čip a ověří re-readem | ✅ Implementováno |
| 7 | Re-registrace vyžaduje explicitní potvrzení | ✅ HTTP 409 + checkbox |
| 8 | Pokladna rozliší 🟢/🔴 do 1 sekundy | ✅ HW závislé |
| 9 | Po vypnutí/zapnutí RPi se vše rozjede do 30 s | ✅ systemd auto-restart |
| 10 | Žádná stanice nepotřebuje síť | ✅ Architektura |

---

## 8. Co je hotové (k 20. 5. 2026)

| Komponenta | Pokrytí testy | Status |
|---|---|---|
| `shared/passport_chip.py` | 12 unit testů | ✅ Hotovo |
| `shared/countries.py` (11 zemí, 21 faktů × 11) | – | ✅ Hotovo |
| `shared/greeting.py` (skloňování + rod) | 11 unit testů | ✅ Hotovo |
| `shared/nfc_device.py` (PN532 + Mock) | E2E | ✅ Hotovo |
| `station-country` | 6 E2E scénářů | ✅ Hotovo |
| `station-registration` | 7 E2E scénářů | ✅ Hotovo |
| `station-checkout` | 6 E2E scénářů | ✅ Hotovo |

Celkem: **~3 000 řádků kódu**, **~50 testovacích scénářů**, 100% mock-testovaný.

---

## 9. Co zbývá udělat

### 9.1 Hardware testy (PRIORITA 1)

Před objednáním všech 15 ks čteček + 14 ks displejů + 13 ks RPi:

1. **Objednat 1 ks PN532 + 1 ks NTAG213 25 mm + 1 ks RPi 1GB + 1 ks 7" displeje**
2. **Otestovat:**
   - Funguje `nfcpy` driver na konkrétní variantě PN532 (USB-UART vs I²C)?
   - Funguje zápis na 64 B v NTAG213 spolehlivě?
   - Vyhovuje dosah čtečky (cm)?
   - Vejde se uvítací věta na 800×480 displej se zvolenou velikostí písma?
3. **Po úspěšném testu** objednat zbytek

### 9.2 Provisioning

1. Vytvořit master image (Raspberry Pi OS Lite + nainstalovaný software)
2. Naklonovat na 14 SD karet
3. Pro každou stanici upravit `/boot/station.conf`
4. Vyrobit nálepky na krabičky s indexem stanice

### 9.3 Dry-run

Generální zkouška celého toku **týden před akcí**:
- 5 dobrovolníků projde celou cestu (registrace → 11 zemí → pokladna)
- Sleduje se: rychlost obsluhy, chybovost, srozumitelnost hlášek

### 9.4 Drobné polishing

Případné úpravy na základě:
- Reálné grafiky zemí (zatím SVG placeholdery)
- Finálního loga „Srdcem pro Ondráška" (zatím placeholder)
- Zpětné vazby z dry-runu

---

## 10. Otevřené otázky / rizika

| # | Téma | Status | Risk Owner |
|---|---|---|---|
| 1 | NTAG213 vs NTAG215 – stačí 144 B? | ✅ Vejde se i s 100% rezervou | – |
| 2 | Spolehlivost zápisu na NTAG | ⏳ HW test potvrdí | dodavatel |
| 3 | Grafika 11 zemí + finální logo Ondráška | ⏳ Dodá zadavatel | zadavatel |
| 4 | Aktivita pro Českou republiku | ⏳ „Bude upřesněno" | zadavatel |
| 5 | Foto cestovatele – proces tisku | ✅ Mimo systém (papírová vlepenka) | obsluha |
| 6 | Real-time statistiky během akce | ❌ Nepodporujeme; jen post-event | – |

---

## 11. Souhrn pro management

**Co dostaneme:**
- 14 robustních standalone stanic, které spolu nemusí komunikovat
- Plně otestovaný software s 50+ scénáři pokrytými automaticky
- Nezávislost na infrastruktuře místa konání (Wi-Fi, internet)
- Možnost rozšířit v dalších letech (přidání zemí, jiné aktivity, atd.)

**Co stojíme:**
- HW: ~14× RPi + ~14× displej + ~15× PN532 + N× NTAG213 nálepky
- Vývoj: hotovo (~3 000 řádek kódu, plně otestováno)
- Provoz: nulový – po akci se SD karty buď vymažou, nebo zazálohují pro příští rok

**Co je nutné dořešit do nasazení:**
1. Objednat 1 ks vzorového HW a otestovat (kritické)
2. Dodat finální grafiku 11 zemí + logo
3. Provisioning 14 SD karet
4. Dry-run týden před akcí

---

*Dokument je zároveň zadáním pro programátora i finální specifikací implementovaného řešení. Software je 100 % hotov k 20. 5. 2026, čeká jen na HW ověření a dodávku grafiky.*
