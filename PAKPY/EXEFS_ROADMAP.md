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
- Version und Flags lesen
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

Dateien:

```text
PAKPY/exefs_nso.py
PAKPY/exefs_gui_patch.py
PAKPY/test_exefs_nso.py
```

## Schritt 2 – ARM64-Disassembler

Geplant:

- AArch64-Disassembly des `text`-Segments
- Adresse, Dateioffset, Bytes, Mnemonic und Operanden
- direkte Branch-/Call-Ziele
- gelesene und geschriebene Register
- Sprung zu Adresse/Offset
- Export eines markierten Bereichs
- optional Capstone; fehlende Abhängigkeit muss sauber gemeldet werden

## Schritt 3 – String- und Xref-Browser

Geplant:

- ASCII-/UTF-8- und relevante UTF-16-Strings katalogisieren
- `ADRP + ADD`, `ADRP + LDR` und Literalreferenzen erkennen
- Pointertabellen in `rodata`/`data` erkennen
- alle Xrefs auf einen String anzeigen
- nahe Strings, Funktionen und Datenobjekte gruppieren
- Suchprofile für `initLevelTransition`, `PrepareForTransition`, `PlayerCount`, `Char_P1`, `Char_P2`, `HARD`

## Schritt 4 – Funktions- und Callgraph-Ansicht

Geplant:

- heuristische Funktionsgrenzen
- `Calls` und `Called by`
- Basic Blocks und Branch-Ziele
- referenzierte Strings und globale Daten
- Rückgabestellen
- lokale Namen, Kommentare und Bookmarks

## Schritt 5 – UI-Callback → ExeFS-Tracer

Geplant:

- vorhandenen Native-Callback-Inspector anbinden
- Aktion `Im ExeFS verfolgen`
- AVM2-Aufrufstelle, Callbackname und Argumentbeispiele übernehmen
- NSO-String und Registrierungs-Xrefs suchen
- mögliche Name/Funktionspointer-Tabellen bewerten
- Callback-Funktionskandidaten mit Konfidenz anzeigen
- konkreter erster Zielpfad: `initLevelTransition("HARD", currentKong)`

---

# Phase B – Datenfluss und Bedingungen

## Schritt 6 – Lokaler Register-/Konstanten-Tracer

Mindestens zu unterstützen:

```text
MOV, MOVZ, MOVK
ADRP, ADR, ADD, SUB
LDR, STR
CMP, TST
CSEL
CBZ, CBNZ
TBZ, TBNZ
B.cond, B, BL, RET
```

Ziele:

- Herkunft einfacher Argumente und Konstanten verfolgen
- Stringpointer bis zum Vergleich verfolgen
- Loads/Stores auf globale Daten verbinden
- Werte wie `PlayerCount == 1` sichtbar machen

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

Nächster technischer Meilenstein nach Schritt 1:

```text
initLevelTransition im ExeFS-main statisch bis zum nativen Callback verfolgen
```

# Formatquellen

- NSO0-Übersicht: https://switchbrew.org/wiki/NSO
- Atmosphère ExeFS-Patches: https://github.com/Atmosphere-NX/Atmosphere
