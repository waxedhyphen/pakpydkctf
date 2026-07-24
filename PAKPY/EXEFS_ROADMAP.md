# PAKPY ExeFS Lab – Roadmap

Diese Datei ist die feste Roadmap für die universellen ExeFS-/ARM64-Werkzeuge in PAKPY.

## Architekturregel

```text
universelle Analyse-/Patchlogik -> Python-Module
spiel- und buildbezogene Patchdaten -> externe JSON-Projekte
binäre Beweise und Teststatus -> Markdown-Dokumentation
```

Python-Module dürfen keine DKCTF-Adressen, Build IDs oder benannten Gameplay-Patches enthalten. Das aktuelle DKCTF-Hard-Mode-Projekt liegt nur unter:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
```

## Zielkette

```text
SWF-/AVM2-Aufruf
-> nativer Callbackname
-> NSO-String und ARM64-Xrefs
-> Callback-Funktion und Datenfluss
-> frei editierbares Patchprojekt
-> Build-ID-/Originalbyte-Prüfung
-> IPS32-Export
-> Emulator-/Atmosphère-Modstruktur
-> dokumentierter Spieltest
```

Analyse und Schreiben bleiben getrennt. Die geladene `main` wird nie verändert.

---

# Phase A – Fundament

## Schritt 1 – NSO-Loader und Adressübersetzer

Status: **implementiert und am DKCTF-Referenz-Build geprüft**

- NSO0-Header, Version, Flags und vollständige Build ID
- `text`, `rodata`, `data`, `bss`
- korrekte Kompressions-/Hashflags
- rohe LZ4-Dekomprimierung
- Segment-SHA-256-Prüfung
- Dateioffset, NSO-VA und Runtime-Adresse
- keine erfundene 1:1-Dateizuordnung für komprimierte Segmente

## Schritt 2 – ARM64-Disassembler

Status: **Baseline implementiert**

- AArch64-Disassembly des `text`-Segments
- Adresse, Bytes, Mnemonic und Operanden
- direkte Branch-/Call-Ziele
- unbekannte Instruktionen bleiben als `.word` sichtbar
- Capstone optional, eigener Decoder ohne Pflichtabhängigkeit

## Schritt 3 – String- und Xref-Browser

Status: **Baseline implementiert**

- ASCII-/UTF-8-Strings
- Pointerreferenzen in `rodata`/`data`
- ARM64-Adressreferenzen
- Callback-Record-Kandidaten
- `initLevelTransition` am Referenz-Build bis zum Funktionspointer verfolgt

## Schritt 4 – Funktions- und Callgraph-Ansicht

Status: **Baseline implementiert**

- heuristische Funktionsgrenzen
- `Calls` und `Called by`
- Basic Blocks und Branch-Ziele
- Rückgabestellen
- Speicherzugriffssuche nach Feldoffset

## Schritt 5 – UI-Callback -> ExeFS-Tracer

Status: **erster realer Pfad bestätigt**

```text
initLevelTransition
String:          0x1520A98
Callback-Record: 0x193BB40
Native Funktion: 0x35267C
```

Noch offen:

- direkte Aktion aus dem AVM2-Callback-Inspector
- automatische Übergabe von Callbackname und Argumentbeispielen
- allgemeine Bewertung mehrdeutiger Callbacktabellen

---

# Phase B – Datenfluss und Bedingungen

## Schritt 6 – Lokaler Register-/Konstanten-Tracer

Status: **Baseline implementiert**

Unterstützte Kernfälle:

```text
MOV, MOVZ, MOVK
ADRP, ADR, ADD, SUB
LDR, LDRB, STR, STRB
CMP, TST
CBZ, CBNZ
TBZ, TBNZ
B.cond, B, BL, RET
```

Bereits automatisch erkannt:

```text
load32(arg0+0x840) != 2
```

## Schritt 7 – Bedingungsanalyse

Status: **teilweise implementiert**

- Branchbedingungen und Ziele sichtbar
- einfache Registerherkunft sichtbar

Offen:

- generische Vorschläge für immer/nie/invertieren
- Vergleichskonstante gezielt ändern
- Konfidenz und Unsicherheiten ausgeben

## Schritt 8 – Globale Daten- und Schreibzugriffsansicht

Status: **teilweise implementiert**

- Leser/Schreiber nach Feldoffset suchen
- Hard-Mode-Felder `+0x2698`, `+0x269C`, `+0x26A0` verbunden

Offen:

- projektweit benannte globale Daten
- zeitliche Schreibpfade
- systematische Watchpoint-/Hook-Vorschläge

---

# Phase C – Patch-Erzeugung

## Schritt 9 – Universeller ARM64-Patchprojekt-Editor

Status: **implementiert**

GUI:

```text
Werkzeuge -> ExeFS Patchprojekt / IPS32
Ctrl+Shift+P
```

Funktionen:

- beliebige NSO-VA
- beliebige erwartete und neue Bytes
- beliebig viele Einträge
- Hinzufügen, Bearbeiten, Entfernen
- Originalbyte- und Segmentprüfung
- Build-ID-Bindung
- Disassembly vorher/nachher
- Überlappungsprüfung
- JSON laden/speichern

Wichtig: Es gibt keine fest eingebaute Profilregistry und keine DKCTF-Patchfunktion mehr.

## Schritt 10 – ARM64-Hilfsaktionen

Status: **geplant**

```text
NOP
Return false / true / Konstante
Branch immer / nie / invertieren
CBZ <-> CBNZ
B.EQ <-> B.NE
MOV-Konstante ändern
BL-Ziel ersetzen
```

Die Aktionen erzeugen nur editierbare Projektzeilen und müssen Originalbytes anzeigen.

## Schritt 11 – Code-Cave-/Trampolin-Builder

Status: **geplant**

- Paddingbereiche finden
- Branch-Reichweite prüfen
- Originalinstruktionen übernehmen
- Register und 16-Byte-Stackausrichtung sichern
- kontrollierter Rücksprung
- Konflikte mehrerer Trampoline

## Schritt 12 – IPS32-Export

Status: **implementiert**

- Build ID und Originalbytes vor Export zwingend validiert
- Atmosphère-Offsetregel `NSO-VA + 0x100`
- generischer Direkt-Export
- Emulator-Modroot-Export:

```text
<Mod>/exefs/<Build-ID>.ips
```

- Atmosphère-Export:

```text
atmosphere/exefs_patches/<Patchgruppe>/<Build-ID>.ips
```

- `manifest.json` und `README.md`
- geladene `main` bleibt unverändert

---

# Phase D – Versionssicherheit

## Schritt 13 – Build- und Spielversionsprofile

Status: **Projekt-Build-ID vorhanden; vollständige Analyseprofile offen**

## Schritt 14 – Binärvergleich zweier Builds

Status: **geplant**

- verschobene ähnliche Funktionen
- geänderte Konstanten und Branches
- neue/entfernte Strings
- verschobene Callbacktabellen
- bekannte Patchstellen im neuen Build

## Schritt 15 – Pattern-/Signatursystem

Status: **geplant**

- Bytepatterns mit Wildcards
- Segmentbegrenzung
- erwartete Trefferzahl
- Kontextbytes und Instruktionsbedingungen
- keine Anwendung bei Mehrdeutigkeit

## Schritt 16 – Funktions-Fingerprints

Status: **geplant**

- normalisierte Instruktionsfolge
- Basic-Block-Struktur
- Strings und Callziele
- Wiedererkennung über Builds

---

# Phase E – Laufzeitdiagnose

## Schritt 17 – Runtime-Trace-Patch-Generator

Status: **geplant**

- temporäre Hooks
- Callbackargumente und Zustände
- Ringpuffer oder vorhandene Logfunktion
- vollständige Rückbauinformationen

## Schritt 18 – Watchpoint-/Hook-Planer

Status: **geplant**

- alle Schreibzugriffe sammeln
- geeignete Hookpunkte vorschlagen
- Register-/Stackanforderungen

## Schritt 19 – Crash-Report-Mapper

Status: **geplant**

- Atmosphère-Crashreport
- Build ID, PC, LR, Register, Backtrace
- Zuordnung zu Funktion, Offset und Patchprojekt

---

# Phase F – Projektverwaltung

## Schritt 20 – Analyseprojekt pro Build

Status: **geplant**

Die originale `main` wird niemals im Analyseprojekt verändert oder gespeichert.

## Schritt 21 – Patchprojekte und Abhängigkeiten

Status: **JSON-Einzelprojekte implementiert; Abhängigkeiten offen**

Beispiel:

```text
HardModeMultiplayer
├─ UI_EnableButton
├─ UI_EnableNavigation
├─ UI_P2CharacterSelector
├─ ExeFS_PreserveP2Active
└─ ExeFS_PreserveP2Character
```

## Schritt 22 – Automatischer Patchbericht

Status: **Baseline implementiert**

Jeder Export dokumentiert:

- Build ID
- NSO-VA und IPS32-Offset
- erwartete und neue Bytes
- Disassembly vorher/nachher
- Beschreibung
- Quell-SHA-256

Offen:

- Spielteststatus direkt im Projekt
- Abhängigkeiten und Konflikte mehrerer Projekte

---

# Aktuelles Untersuchungsziel

```text
Hard Mode im 2-Spieler-Modus
```

Binär bestätigt:

- Hard Mode setzt nur P1 aktiv.
- Testpatch 1 erhält ein bereits aktives P2-Bit.
- P2-Charakterübernahme ist ein separater späterer Patch.

Konkrete Beweise:

```text
PAKPY/EXEFS_HARDMODE_FINDINGS.md
```

Konkretes Testprojekt, ausschließlich als Daten:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
```

# Arbeitsregeln

1. Analyse und Schreiben bleiben getrennt.
2. Absolute Offsets gelten nur für die dokumentierte Build ID.
3. Originalbytes werden vor jedem Export exakt geprüft.
4. Komprimierte NSO-Segmente besitzen keine direkte Byte-für-Byte-Dateioffset-Zuordnung.
5. Jede Adresse wird als Dateioffset, NSO-VA oder Runtime-Adresse bezeichnet.
6. Binär plausibel ist nicht gleich im Spiel bestätigt.
7. Spielbezogene Patchdaten bleiben außerhalb des Python-Codes.
8. Jede neue Funktion aktualisiert Roadmap und relevante Findings-Dokumentation.
