# UI Viewer – MSBT-Lokalisierung und Laufzeittexte

Stand: 2026-07-22

## Zweck

Diese Stufe verbindet die vorhandenen `DefineEditText`-, AVM2-, Data-Value- und Native-Callback-Pfade mit den lokalisierten Nintendo-Message-Studio-Dateien aus `MSBT`-Ressourcen.

Die Implementierung ist ausschließlich lesend und wirkt nur auf die Vorschau. MSBT-, GFX-, GFXL-, TXTR- und PAK-Daten werden nicht verändert.

## Ressourcenpfad

```text
aktuelles PAK + Require-PAKs
  -> Einträge vom Typ MSBT
  -> optionales Sprachbundle
       USEN / USFR / USSP
       EUEN / EUFR / EUSP / EUGE / EUIT
       JPJP
  -> MsgStdBn
  -> LBL1: Text-ID -> Nachrichtenindex
  -> TXT2: lokalisierter Text
  -> ATR1: optionale Rohattribute
```

Der Viewer baut pro geöffnetem Film einen gemeinsamen, schreibgeschützten Katalog aus dem aktuellen PAK und allen im Require-Store geladenen PAKs.

## MSBT-Parser

`PAKPY/msbt_codec.py` unterstützt:

- Little- und Big-Endian-MSBT;
- UTF-8, UTF-16 und UTF-32;
- `LBL1`, `TXT2` und `ATR1`;
- 16-Byte-Sektionsausrichtung;
- validierte Datei-, Sektions-, Tabellen- und Textgrenzen;
- diagnostische Darstellung von Message-Studio-Kontrolltags;
- stabile Nachrichtenobjekte mit Index, Label, Text und Rohattributen.

### Sicherheitsgrenzen

- höchstens 64 Sektionen pro Datei;
- höchstens 1.000.000 Nachrichten oder Label-Buckets;
- höchstens 256 MiB pro Sektion;
- höchstens 16 MiB pro Text;
- höchstens 4.096 Bytes pro Label;
- fehlerhafte Dateien werden einzeln protokolliert und blockieren keine anderen Sprachdateien.

## Sprachcodes

| Code | Anzeige |
|---|---|
| `USEN` | English (US) |
| `USFR` | Français (US) |
| `USSP` | Español (US) |
| `EUEN` | English (EU) |
| `EUFR` | Français (EU) |
| `EUSP` | Español (EU) |
| `EUGE` | Deutsch |
| `EUIT` | Italiano |
| `JPJP` | 日本語 |

Standardmäßig ist `EUEN` aktiv. Der Standard-Fallback ist `USEN`. Fehlt eine dieser Sprachen im geladenen PAK-Satz, wird deterministisch die erste tatsächlich vorhandene Sprache gewählt.

## Exakte Text-ID-Auflösung

Die Laufzeitauflösung ist absichtlich konservativ. Unterstützt werden ausschließlich exakte IDs:

```text
Options_Audio
msbt:Options_Audio
loc:Options_Audio
${Options_Audio}
@Options_Audio@
#Options_Audio#
[Options_Audio]
```

Optional kann ein Bundle explizit angegeben werden:

```text
shell:StartMessage
universe:l01_mangrove_diddy
```

Groß-/Kleinschreibung wird nur dann ignoriert, wenn das Label dadurch weiterhin eindeutig bleibt. Teilstrings, Levenshtein-Abstände und ähnlich klingende Namen werden nicht verwendet.

### Mehrdeutige Labels

Einige IDs existieren absichtlich in mehreren Bundles. Beispiel:

```text
saveslot:l01_mangrove_diddy -> "1-1"
universe:l01_mangrove_diddy -> "MANGROVE COVE"
```

Ohne Bundle-Präfix wird ein solches Label nicht ersetzt. Sind mehrere Datensätze vorhanden, aber ihre Texte identisch, ist die Auflösung weiterhin sicher.

## Vorrangregeln

Für Textfelder gilt:

```text
manueller State-Inspector-Textoverride
-> direkter AVM2-Text-/htmlText-Wert
-> Game-State-Mock
-> exakte MSBT-Auflösung des ursprünglichen Feldwerts oder der Textvariable
-> ursprünglicher DefineEditText-Inhalt
```

Für Native-Callbacks gilt:

```text
manueller Native-Callback-Override
-> bestehende sichere Callback-/Data-Value-Simulation
-> exakte MSBT-Auflösung eines zurückgegebenen Text-IDs
-> bei textbezogenen Callbacks: exakte ID aus den Argumenten
-> unveränderter Rückgabewert
```

Ein manueller Callback-Override wird nicht nachträglich lokalisiert. Dadurch bleibt der explizite Benutzerwert vollständig maßgeblich.

## AVM2- und dynamische TextFields

Wird `text` oder `htmlText` durch AVM2 auf eine exakte MSBT-ID gesetzt, speichert der Viewer zusätzlich die rohe ID. Beim Sprachwechsel wird der Wert aus dieser ID erneut aufgelöst, ohne das Frame Script neu ausführen zu müssen.

Das gilt für vorhandene Timeline-Textfelder, dynamisch erzeugte `TextField`-Instanzen und Runtime-Properties an stabilen DisplayObject-Pfaden. Freier Text, Zahlen, Game-State-Werte und nicht auflösbare Strings bleiben unverändert.

## Data-Value- und Callback-Verbindung

Ein lesender Data-Value- oder Native-Callback darf weiterhin eine rohe Text-ID im filmbezogenen Vorschauzustand speichern. Erst beim Rückgabepfad an ActionScript wird sie lokalisiert. Dadurch bleibt der interne Zustand reproduzierbar und ein späterer Sprachwechsel kann denselben Schlüssel erneut auflösen.

Der Inventar-Scanner erfasst zusätzlich exakte MSBT-IDs in sämtlichen AVM2-Stringpools, statisch erkennbaren Callback-Argumenten sowie `DefineEditText.initial_text` und `variable_name`. Mehrdeutige bundleübergreifende IDs werden im Bericht aufgeführt, aber nicht automatisch als sichere Laufzeitverbindung angewendet.

## Bedienung

Im UI Browser gibt es:

- `MSBT / Texte`: öffnet den Inspector;
- `Lokalisieren`: aktiviert oder deaktiviert die Laufzeitauflösung;
- `Sprache`: wählt einen tatsächlich vorhandenen Sprachcode;
- `Ctrl+L`: öffnet denselben Inspector.

Der Inspector besitzt drei Registerkarten.

### MSBT-Texte

- Filter nach ID, Text oder Bundle;
- Text der aktuell gewählten Sprache;
- Quell-PAK und Bundle;
- Nachrichtenindex;
- Vergleich aller vorhandenen Sprachen;
- vollständiger JSON-Export.

### Laufzeit-Links

- Text-ID;
- Quelle `AVM2`, `EditText` oder `Callback`;
- Vorkommenszahl;
- Modul-, Feld- oder Callback-Fundstellen.

### Diagnose

- Sprachdateien und Nachrichtenzahlen;
- Bundleverteilung;
- Parserfehler;
- aktive Sprache und Fallback;
- statische Laufzeitverbindungen.

Der State Inspector zeigt bei lokalisierten Feldern zusätzlich ID, Sprache, Bundle, Quelle und Fallbackstatus.

## Presetformat

Das bestehende Presetformat Version 1 erhält optional:

```json
{
  "localization": {
    "enabled": true,
    "language": "EUGE",
    "fallback": "USEN"
  }
}
```

Gespeichert werden nur Aktivierung, Sprache und Fallback. Der MSBT-Katalog, Parserdiagnosen und Laufzeit-Linklisten werden beim Öffnen aus den PAKs neu aufgebaut. Ältere Presets ohne `localization` bleiben kompatibel.

## Reproduzierbarer Corpus-Scan

```bash
python PAKPY/scan_ui_localization_links.py UIPak.pak \
  --require MiscData.pak \
  --require PreLoadPak.pak \
  --json ui_localization_links.json
```

Der Scanner liest alle direkten und gebündelten MSBT-Ressourcen, validiert jede `MsgStdBn`-Datei, inventarisiert Sprache, Bundle, Labels und Texte, extrahiert deduplizierte AVM2-Module und vergleicht Stringpools sowie Callback-Argumente ausschließlich exakt mit MSBT-Labels.

### Ergebnis des bereitgestellten Corpus

Gescannt wurden `UIPak.pak`, `MiscData.pak` und `PreLoadPak.pak`.

| Messwert | Ergebnis |
|---|---:|
| MSBT-Sprachdateien | 36 |
| Nachrichtensätze über alle Sprachen | 7.641 |
| Sprachen | 9 |
| Nachrichtensätze pro Sprache | 849 |
| eindeutige Labels pro Sprache | 716 |
| Parserfehler | 0 |
| Labels in mehreren Bundles | 70 |
| eindeutige ABC-Module | 40 |
| exakte AVM2-Labelmatches | 59 Labels / 243 Stringvorkommen |
| davon ohne Bundlehinweis sicher auflösbar | 52 Labels / 131 Stringvorkommen |
| exakte Callback-Argumentmatches | 2 Labels / 11 Call-Sites |
| davon ohne Bundlehinweis sicher auflösbar | 1 Label / 4 Call-Sites |

Die vier Bundles sind:

| Bundle | Nachrichten pro Sprache |
|---|---:|
| `shell` | 502 |
| `saveslot` | 69 |
| `miiverse` | 205 |
| `universe` | 73 |

Jede der neun Sprachen enthält dieselben 716 eindeutigen Labels. Die höhere Nachrichtenzahl von 849 entsteht durch 70 absichtlich bundleübergreifend wiederverwendete IDs.

## Tests und Validierung

Die fokussierte Testsuite prüft Little- und Big-Endian-UTF-16-MSBT, abgeschnittene Sektionen, Sprachwahl und Fallback, präfixierte IDs, mehrdeutige Bundle-Labels, identische Duplikate, deaktivierte Lokalisierung und die Begrenzung einer Preset-Sprache auf tatsächlich vorhandene Sprachen.

Alle 36 realen Sprachdateien wurden gelesen. Es gab keine MSBT- oder ABC-Parserfehler. Das vollständige Tk-Fenster wurde in der Headless-Umgebung nicht visuell end-to-end geprüft.

## Grenzen und nächste Schritte

Noch offen sind:

- semantische Parameterformatierung für spielinterne Message-Studio-Kontrolltags;
- exakte Hostsignaturen für alle textbezogenen Native-Callbacks;
- automatische Bundlewahl aus vollständig rekonstruiertem Spielkontext;
- bidirektional editierbare MSBT-Texte und Repacking;
- pixelgenaue Font-Rasterisierung für alle Sprachzeichensätze;
- klassische `DefineButton`-/`DefineButton2`-Tags und pixelgenaue Shape-HitTests.

Der nächste Viewer-Arbeitsblock ist die **klassische SWF-Button- und HitTest-Stufe**: `DefineButton`, `DefineButton2`, Button-Action-Inventar, masken- und `scrollRect`-bewusste Treffer sowie präzisere Shape-HitTests.
