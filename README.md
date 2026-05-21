# Srdcem pro Ondráška – Cesta kolem světa

Systém pro charitativní akci – 11 stanovišť zemí + 1 registrační + 2 pokladny.

## Architektura - "Storage on Chip"

- Žádná síť mezi RPi - každá stanice je samostatná
- Veškerý stav cestovatele se ukládá NA ČIP (NTAG213, 64 B)
- Statická DB zemí je součástí každé stanice
- Foto pasu je papírové (řeší se mimo systém)

## Hardware

| Komponenta | Kus | Použití |
|---|---|---|
| RPi 1GB | 13 | 11× země + 2× pokladna |
| RPi 2GB | 1 | Registrační stanice |
| 7" Pi Touch Display 800x480 | 13 | Stanice s displejem (kromě registrace - notebook) |
| PN532 NFC modul | 15 | 14 stanic + 1 rezerva |
| NTAG213 NFC nálepka 25mm | dle počtu dětí | Pasy |
| LED + bzučák (GPIO) | volitelně 2× | Pokladny |
| Notebook | 1 | Pro obsluhu registrace |

## Adresářová struktura

```
passport-system/
├── shared/                    Sdílený kód pro všechny stanice
│   ├── passport_chip.py       Serialize/deserialize čipu (64 B)
│   ├── countries.py           11 zemí + 21 faktů/zemi + lokativy
│   ├── greeting.py            Logika uvítacích vět
│   ├── nfc_device.py          PN532 + Mock abstrakce
│   └── tests/                 Unit testy
│
├── station-country/           Stanice země (×11 RPi)
├── station-registration/      Registrační stanice (RPi 2GB)
├── station-checkout/          Pokladna (×2 RPi)
└── README.md
```

## Quick start (vývoj na PC bez HW)

```bash
# Závislosti
pip3 install --break-system-packages aiohttp

# === Stanice země (Japonsko) ===
cd station-country
PYTHONPATH=.. PASSPORT_COUNTRY_INDEX=2 PASSPORT_NFC_DEVICE=mock PASSPORT_LOG_DIR=/tmp python3 -m app.daemon
# → http://localhost:8090

# === Registrace ===
cd ../station-registration
PYTHONPATH=.. PASSPORT_NFC_DEVICE=mock PASSPORT_LOG_DIR=/tmp python3 -m app.daemon
# → http://localhost:8000

# === Pokladna ===
cd ../station-checkout
PYTHONPATH=.. PASSPORT_NFC_DEVICE=mock PASSPORT_LOG_DIR=/tmp python3 -m app.daemon
# → http://localhost:8090
```

## Mock příkazy

### Stanice země
- `/mock?action=blank` - neregistrovaný
- `/mock?name=Pavel&gender=M&year=2014` - první návštěva
- `/mock?name=X&gender=F&visited=1,5` - už byl jinde
- `/mock?name=X&gender=M&visited=0,1,3,4,5,6,7,8,9,10` - dokončení

### Registrace
- `/mock?action=blank` - prázdný čip
- `/mock?action=registered&name=Pavel` - už registrovaný
- `/mock?action=invalid` - cizí čip
- `/mock?action=remove` - odebrání čipu

### Pokladna
- `/mock?action=registered&name=Pavel&visited=0,1,2` - validní
- `/mock?action=complete&name=Žofie` - dokončený 11/11
- `/mock?action=blank` - neregistrovaný
- `/mock?action=invalid` - cizí čip

## Status komponent

| Komponenta | Status | Pokrytí testy |
|---|---|---|
| shared/passport_chip | ✅ Hotovo | 12 unit testů |
| shared/countries | ✅ Hotovo | - |
| shared/greeting | ✅ Hotovo | 11 testů |
| shared/nfc_device | ✅ Hotovo | - |
| station-country | ✅ Hotovo | 6 E2E scénářů |
| station-registration | ✅ Hotovo | 7 E2E scénářů |
| station-checkout | ✅ Hotovo | 6 E2E scénářů |

## Datový layout čipu NTAG213

```
0x00   magic byte (0x53)
0x01   verze formátu
0x02   pohlaví (M/F)
0x03   CRC8
0x04   rok narození (u16)
0x06   visited bitmask (u16, 11 bitů)
0x08   last visited country idx
0x09   completed flag
0x0A   total scan count (u16)
0x0C   11× per-country counter (uint8)
0x17   first_name (UTF-8, max 15 B)
0x27   rezerva (FF padding)
```
