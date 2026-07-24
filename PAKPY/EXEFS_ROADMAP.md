# PAKPY ExeFS Lab – Roadmap

Diese Datei ist die feste Roadmap für die ExeFS-/ARM64-Werkzeuge in PAKPY. Sie soll verhindern, dass Analyse, Offsets, Build IDs und Patches erneut nur als verstreute Einzelschritte existieren.

## Ziel

PAKPY soll den vollständigen Weg abdecken:

```text
SWF-/AVM2-Aufruf
→ nativer ExternalInterface-/Controller-Callback
→ NSO-String und ARM64-Xrefs
→ Callback-Funktion und Datenfluss
→ geprüfter ARM64-Patch
→ Build-ID-gebundener IPS-/IPS32-Export
→ Test- und Dokumentationsstatus
```

Die Werkzeuge arbeiten standardmäßig nur lesend. Schreibende Patchfunktionen werden getrennt von Analysefunktionen gebaut und müssen immer Originalbytes, Build ID und Segmentgrenzen validieren.

---

# Phase A – Fundament

## Schritt 1 – NSO-Loader und Adressübersetzer

Status: **implementiert**

Umfang:

- `NSO0`-Header validieren
- Version und die NSO-Flags `0..2` (Kompression) sowie `3..5` (Hash) lesen
- Modulname lesen
- vollständige 32-Byte-Build-ID lesen
- `text`, `rodata`, `data` und `bss` erfassen
- komprimierte Segmente erkennen
- rohe LZ4-NSO-Segmente dekomprimieren
- aktivierte Segment-SHA-256-Werte prüfen
- Dateioffset, NSO-VA und Runtime-Adresse übersetzen
- bei komprimierten Segmenten keine falsche 1:1-Dateizuordnung behaupten
- GUI unter `Werkzeuge → ExeFS Lab (NSO)`
- synthetische Tests für normale, komprimierte und BSS-Bereiche
- reale Validierung gegen die angehängte DKCTF-`main` mit `flags = 0x3F`

Dateien:

```text
PAKPY/exefs_nso.py
PAKPY/exefs_gui_patch.py
PAKPY/test_exefs_nso.py
```

## Schritt 2 – ARM64-Disassembler

Status: **implementiert – Baseline vollständig nutzbar**

Umfang:

- AArch64-Disassembly des dekomprimierten `text`-Segments
- NSO-VA oder Runtime-Adresse, Bytes, Mnemonic und Operanden
- direkte Ziele für `B`, `BL`, `B.cond`, `CBZ/CBNZ`, `TBZ/TBNZ`, `ADR/ADRP` und Literal-Loads
- integrierter Decoder für Kontrollfluss, Register-Moves, Immediate-Arithmetik, Move-Wide sowie häufige Load/Store-Formen
- unbekannte Instruktionen bleiben sichtbar als `.word`, statt übersprungen zu werden
- optionales Capstone-Backend für vollständige AArch64-Disassembly
- automatische Erkennung des üblichen ersten Codes hinter dem `MOD0`-Header
- GUI-Ansicht im ExeFS Lab mit Startadresse, Anzahl und Runtime-Adressumschaltung
- Tests mit bekannten Instruktionsbytes und echter DKCTF-`main`

Dateien:

```text
PAKPY/exefs_arm64.py
PAKPY/test_exefs_arm64.py
```

Noch für spätere Datenflussphasen auszubauen:

- vollständige Register-read/write-Metadaten ohne Capstone
- Sprungnavigation und markierter Export

## Schritt 3 – String- und Xref-Browser

Status: **implementiert – erste Analyseebene**

Umfang:

- ASCII-/UTF-8- und relevante UTF-16LE-Strings in `rodata` und `data`
- exakte oder teilweise Suche mit optionaler Groß-/Kleinschreibung
- 64-Bit-Pointerreferenzen in `rodata` und `data`
- direkte `ADR`- sowie `ADRP + ADD`-/`ADRP + LDR`-Referenzen im ARM64-Code
- Erkennung der im DKCTF-Build verwendeten Native-Callback-Records
- Ausgabe von Stringadresse, Pointer-Slots, Callback-Record und nativem Funktionspointer
- GUI-Tab `Strings / Xrefs`
- gecachter Stringkatalog pro geladener NSO-Datei

Dateien:

```text
PAKPY/exefs_strings.py
PAKPY/test_exefs_strings.py
```

Noch auszubauen:

- mehrstufige GOT-/Relocation-Xrefs
- nahe Strings/Funktionen automatisch gruppieren
- vollständige Pointertabellen-Klassifizierung

## Schritt 4 – Funktions- und Callgraph-Ansicht

Status: **implementiert – kontrollflussbasierte Baseline**

Umfang:

- Funktionsanalyse ab einer bekannten Startadresse
- Worklist-basierte Basic-Block-Erkennung
- direkte `B`-/Bedingungsziele
- direkte `BL`-Calls
- globaler Index für `Called by`
- Rückgabestellen und indirekte `BR`-/`BLR`-Grenzen
- maximale Instruktionszahl als Sicherheitsgrenze
- Suche aller unmittelbaren Load-/Store-Zugriffe auf einen Objektfeld-Offset
- eigene GUI unter `Werkzeuge → ExeFS Funktion / Datenfluss`

Dateien:

```text
PAKPY/exefs_functions.py
PAKPY/exefs_function_gui_patch.py
PAKPY/test_exefs_functions.py
```

Noch auszubauen:

- Jump-Table-Ziele automatisch auflösen
- referenzierte Strings und globale Daten direkt in die Funktionsansicht einblenden
- persistente Namen, Kommentare und Bookmarks

## Schritt 5 – UI-Callback → ExeFS-Tracer

Status: **teilweise implementiert; manueller Name-Transfer funktioniert**

Bereits vorhanden:

- Callbackname aus dem UI-Inspector kann im ExeFS-Lab gesucht werden
- String, Pointer-Slots, Callback-Record und native Funktion werden verbunden
- erkannte Callback-Funktion kann mit einem Klick in den ARM64-Tab übernommen werden
- konkreter Zielpfad `initLevelTransition("HARD", currentKong)` wurde im echten Build bis zur nativen Funktion verfolgt

Noch offen:

- direkte Aktion `Im ExeFS verfolgen` im bestehenden Native-Callback-Inspector
- AVM2-Aufrufstelle und Argumentbeispiele automatisch an das ExeFS Lab übergeben
- Konfidenzbewertung mehrerer Kandidaten

---

# Reale DKCTF-Referenz – angehängtes ExeFS

Die Implementierung wurde zusätzlich zu den synthetischen Tests gegen die bereitgestellte echte `main` geprüft.

```text
Dateigröße: 13.616.472 Bytes (0xCFC558)
SHA-256: 018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21
Build ID: F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
NSO-Flags: 0x3F
```

Alle drei gespeicherten Segmente sind in diesem Build komprimiert und gehasht:

| Segment | NSO-VA | Speichergröße | gespeicherte Größe |
|---|---:|---:|---:|
| `text` | `0x0` | `0xB9BC68` | `0x67381F` |
| `rodata` | `0xB9C000` | `0xD7D96B` | `0x644466` |
| `data` | `0x191A000` | `0xE3A68` | `0x447D2` |
| `bss` | `0x19FDE68` | `0x4A6C598` | nur Speicher |

Die drei aktivierten Segment-Hashes werden erfolgreich validiert.

## Bestätigter Callback-Trace

```text
UI: ExternalInterface.call("initLevelTransition", "HARD", currentKong)
String:          0x1520A98
rodata-Pointer:  0xBEFBE0
Callback-Record: 0x193BB40
Native Funktion: 0x35267C
```

Die Funktion bei `0x35267C` übernimmt den Callback-Argumentcontainer aus `x2`, prüft mindestens ein und anschließend mindestens zwei Argumente und ruft nach der Argumentumwandlung den Helfer bei `0x352AA0` auf.

Binär und durch die neue Funktionsanalyse bestätigt:

```text
initLevelTransition: 0x35267C–0x352AA0
  265 erkannte Instruktionen
  78 Basic Blocks
  38 direkte Calls

Helper: 0x352AA0–0x352D28
  154 erkannte Instruktionen
  27 Basic Blocks
  29 direkte Calls
  direkter Aufrufer: 0x352850
```

Der lokale Datenflusstracer beweist für die Prüfung bei `0x352C4C`:

```text
x19 stammt aus arg0
w8 = load32(arg0 + 0x840)
cmp w8, 2
b.ne 0x352CEC
```

Damit ist die Bedingung exakt als `load32(arg0+0x840) != 2` beschrieben. Der Quellname dieses Objektfelds ist weiterhin **nicht** bewiesen und wird deshalb noch nicht als `PlayerCount` bezeichnet.

Weitere Zugriffe derselben Übergangsklasse:

```text
0x351B88: load32(arg0+0x840) == 2
0x3525C4: 32-Bit-Lesezugriff auf arg0+0x840
0x352C4C: load32(arg0+0x840) != 2
```

---

# Phase B – Datenfluss und Bedingungen

## Schritt 6 – Lokaler Register-/Konstanten-Tracer

Status: **implementiert – konservative lokale Baseline**

Unterstützt:

```text
MOV
MOVZ, MOVN, MOVK
ADR, ADRP
ADD, SUB immediate
LDR, STR immediate
CMP immediate/register
B.cond nach einem erkannten Vergleich
BL/BLR mit AAPCS64-Clobbering von x0–x18
```

Der Tracer beginnt mit `arg0` bis `arg7`, bewahrt callee-saved Register und gibt Speicherzugriffe ohne erfundene Symbolnamen aus. Beispiel aus dem realen Build:

```text
0x352C50 / branch 0x352C54:
load32(arg0+0x840) != 2 -> 0x352CEC
```

Datei:

```text
PAKPY/exefs_dataflow.py
```

Noch auszubauen:

- Zustände an CFG-Joins zusammenführen
- `TST`, `CSEL`, bitweise Aliase und weitere Load-/Store-Formen
- Stringpointer bis durch Helferaufrufe verfolgen
- benannte Objektfelder erst nach zusätzlichem Beweis speichern

## Schritt 7 – Bedingungsanalyse

Geplant:

- Branchbedingung lesbar darstellen
- True-/False-Ziel zeigen
- Vergleichskonstante und Registerherkunft zeigen
- Vorschläge: immer nehmen, nie nehmen, invertieren, Konstante ändern
- zunächst ausschließlich Vorschau, keine automatische Änderung

## Schritt 8 – Globale Daten- und Schreibzugriffsansicht

Geplant:

- alle Leser und Schreiber einer globalen Adresse
- mutmaßliche Variablen wie `PlayerCount`, `Char_P1`, `Char_P2`, `GameMode`
- zeitlich relevante Schreibpfade vor Leveltransition/Spawn
- benannte globale Daten in der Projektdatei speichern

---

# Phase C – Patch-Erzeugung

## Schritt 9 – ARM64-Patch-Editor

Geplant:

- erwartete Originalbytes
- neue Bytes
- Disassembly vorher/nachher
- 4-Byte-Ausrichtung
- Segmentgrenzen
- Build-ID-Prüfung
- Patchüberschneidungen
- rein lokale Vorschau vor Export

## Schritt 10 – ARM64-Hilfsaktionen

Geplant:

```text
NOP
Return false / true / Konstante
Branch immer / nie / invertieren
CBZ ↔ CBNZ
B.EQ ↔ B.NE
MOV-Konstante ändern
BL-Ziel ersetzen
```

PAKPY erzeugt die Instruktionsbytes, zeigt sie aber vor der Übernahme vollständig an.

## Schritt 11 – Code-Cave-/Trampolin-Builder

Geplant:

- freie Paddingbereiche finden
- Reichweite von `B`/`BL` prüfen
- überschriebene Originalinstruktionen übernehmen
- Register sichern/wiederherstellen
- 16-Byte-Stackausrichtung prüfen
- kontrollierter Rücksprung
- Konfliktprüfung zwischen mehreren Trampolinen

## Schritt 12 – IPS-/IPS32-Export

Geplant:

- Atmosphère-Struktur erzeugen
- Dateiname aus vollständiger Build ID
- IPS und IPS32
- Titel-ID und Patchgruppe
- Manifest mit Original-SHA-256, Offsets und Disassembly
- nur für exakt passendes Build-Profil exportieren

---

# Phase D – Versionssicherheit

## Schritt 13 – Build- und Spielversionsprofile

Pro `main` speichern:

```text
Build ID
Datei-SHA-256
Segment-SHA-256
Modulname
bekannte Symbole
Kommentare
Bookmarks
Patchstatus
```

## Schritt 14 – Binärvergleich zweier Builds

Geplant:

- verschobene, aber ähnliche Funktionen erkennen
- geänderte Konstanten und Branches
- neue/entfernte Strings
- verschobene Callbacktabellen
- bekannte Patchstelle im neuen Build suchen

## Schritt 15 – Pattern-/Signatursystem

Geplant:

- Bytepatterns mit Wildcards
- Segmentbegrenzung
- erwartete Trefferzahl
- Kontextbytes
- Instruktionsbedingungen
- keine Anwendung bei mehrdeutigen Treffern

## Schritt 16 – Funktions-Fingerprints

Geplant:

- normalisierte Instruktionsfolge
- Basic-Block-Struktur
- Strings und Callziele
- Hash ohne absolute Adressen
- Wiedererkennung über Builds hinweg

---

# Phase E – Laufzeitdiagnose

## Schritt 17 – Runtime-Trace-Patch-Generator

Geplant für Fälle, die statisch nicht eindeutig sind:

- temporären Hook erzeugen
- Callbackargumente und Zustände protokollieren
- Ringpuffer oder vorhandene interne Logfunktion verwenden
- klar als Diagnosepatch markieren
- vollständige Rückbauinformation speichern

Beispielziel:

```text
initLevelTransition aufgerufen
mode = HARD
Char_P1 = DIDDY
PlayerCount vorher = 2
PlayerCount nachher = 1
```

## Schritt 18 – Watchpoint-/Hook-Planer

Geplant:

- alle Schreibzugriffe auf ausgewählte globale Daten sammeln
- geeignete Hookpunkte vorschlagen
- Register-/Stackanforderungen anzeigen
- mehrere mögliche Schreibpfade vergleichbar machen

## Schritt 19 – Crash-Report-Mapper

Geplant:

- Atmosphère-Crashreport einlesen
- Build ID, PC, LR, Register und Backtrace erfassen
- Adressen auf NSO-Funktion und Offset abbilden
- betroffenen PAKPY-Patch benennen

---

# Phase F – Projektverwaltung und Dokumentation

## Schritt 20 – Analyseprojekt pro Build

Geplante Struktur:

```text
analysis/<build-id>/
  profile.json
  symbols.json
  comments.json
  bookmarks.json
  function_signatures.json
  patches.json
```

Die originale `main`-Datei wird nicht verändert.

## Schritt 21 – Patchprojekte und Abhängigkeiten

Beispiel:

```text
HardModeMultiplayer
├─ UI_EnableButton
├─ UI_EnableNavigation
├─ UI_P2CharacterSelector
├─ ExeFS_PreservePlayerCount
└─ ExeFS_EnableP2Spawn
```

Statuswerte:

```text
nicht angewendet
teilweise angewendet
angewendet
Konflikt
falsche Build ID
nicht im Spiel bestätigt
im Spiel bestätigt
```

## Schritt 22 – Automatischer Patchbericht

Jeder Export soll dokumentieren:

- Build ID
- Datei- und virtuelle Adresse
- erwartete und neue Bytes
- Disassembly vorher/nachher
- Funktions-/Symbolname
- Zweck des Patches
- statischer Prüfstatus
- Spielteststatus

---

# Arbeitsregeln

1. Analyse und Schreiben bleiben getrennte Modi.
2. Absolute Offsets gelten nur für die dokumentierte Build ID.
3. Originalbytes werden vor jeder Änderung exakt geprüft.
4. Komprimierte NSO-Segmente besitzen keine direkte Byte-für-Byte-Dateioffset-Zuordnung.
5. Jede Adresse wird ausdrücklich als Dateioffset, NSO-VA oder Runtime-Adresse bezeichnet.
6. Ein statisch plausibler Patch ist nicht automatisch im Spiel bestätigt.
7. Code-Caves und Trampoline werden erst nach einem dokumentierten Kontrollfluss gebaut.
8. PAK-/AVM2- und ExeFS-Änderungen werden in einem gemeinsamen Patchprojekt, aber als getrennte Dateien geführt.

# Aktuelles Untersuchungsziel

Teil 3 des KONG-Select-Projekts:

```text
Hard Mode im 2-Spieler-Modus
```

Bereits UI-seitig bestätigt:

- Hard-Mode-Button im Multiplayer aktiviert
- Hard Mode in die Navigation aufgenommen
- `map.menu_hardmode.inputSelect` ruft `initLevelTransition("HARD", currentKong)` auf
- SWF setzt vor dem Übergang nur `Char_P1`

Aktueller technischer Stand:

```text
initLevelTransition wurde bis 0x35267C und in den Helper 0x352AA0 verfolgt.
Funktions-/Callgraph-Analyse und lokaler Registerdatenfluss sind implementiert.
Das Feld arg0+0x840 wird im Hard-Mode-Übergang gegen 2 geprüft.
```

Nächster Meilenstein:

```text
Die Bedeutung und alle relevanten Schreibstellen von arg0+0x840 nachweisen.
Danach entscheiden, ob die Prüfung bei 0x352C54 der Multiplayer-Block ist oder
nur ein bereits gewünschter Zwei-Spieler-Zweig.
```

# Formatquellen

- NSO0-Übersicht: https://switchbrew.org/wiki/NSO
- Atmosphère ExeFS-Patches: https://github.com/Atmosphere-NX/Atmosphere
