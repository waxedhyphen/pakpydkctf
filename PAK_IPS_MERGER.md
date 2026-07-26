# PAKPY PAK-/IPS-Dreiwegemerge

## Zweck

Der Merger kombiniert zwei Mods, die auf derselben unveränderten Original-PAK basieren.
Er arbeitet ressourcentypunabhängig und berücksichtigt deshalb unter anderem `GFX`/SWF,
`TXTR`, Modelle, Materialien, Audio, `MSBT`, `ROOM`, `CHAR` und alle unbekannten
RFRM-Ressourcen.

Eingaben:

1. unveränderte Original-PAK;
2. PAK A;
3. PAK B;
4. optional IPS/IPS32 A;
5. optional IPS/IPS32 B.

Ausgaben:

- eine neu aufgebaute gemeinsame PAK;
- optional eine gemeinsame IPS32-Datei.

## Öffnen

PAKPY starten und unten `PAK-/IPS-Merger` wählen. Tastenkürzel: `Strg+Umschalt+M`.

## PAK-Logik

Jede Ressource wird über ihre UUID mit dem Original verglichen:

- nur A geändert: Ressource aus A;
- nur B geändert: Ressource aus B;
- A und B identisch geändert: Änderung einmal übernehmen;
- beide unterschiedlich geändert: automatischer Dreiwegemerge.

Für gleich große Binärdaten werden getrennte Bytebereiche direkt kombiniert. Bei
Größenänderungen werden getrennte Einfügungen, Löschungen und Ersetzungen über
Originalkoordinaten zusammengeführt.

### GFX/SWF

GFX-Ressourcen werden zunächst pro enthaltenem Film getrennt. Wenn beide Mods denselben
Film ändern, wird der SWF entpackt und rekursiv anhand seiner Tagstruktur kombiniert.
Damit können unter anderem getrennte AVM2-Änderungen, neue Placements, unterschiedliche
DefineSprites und Änderungen in verschiedenen Untertimelines zusammengeführt werden.

Kollisionen werden erkannt, insbesondere:

- unterschiedliche Änderungen am selben Bytebereich;
- zwei verschiedene Placements auf derselben Display-Tiefe;
- zwei verschiedene Definitionen mit derselben Character-ID;
- unterschiedliche DoABC-Einfügungen mit demselben Modulnamen;
- Löschen auf einer Seite und Ändern auf der anderen.

## IPS

Normale IPS- und IPS32-Dateien können eingelesen werden. Die Ausgabe ist immer IPS32.
Nicht überlappende Schreibbereiche werden kombiniert. Identische Überschneidungen werden
nur einmal geschrieben. Unterschiedliche Bytes am selben Offset sind ein Konflikt.

## Konfliktstrategien

- `Bei Konflikt abbrechen`: Standard; es wird nichts mit ungelösten Konflikten gebaut.
- `PAK A bevorzugen`: die vollständige konfliktbehaftete Ressource beziehungsweise das
  IPS-Byte aus A gewinnt.
- `PAK B bevorzugen`: entsprechend B.

Die Bevorzugung greift nur für tatsächlich unauflösbare Konflikte. Alle übrigen
Änderungen werden weiterhin automatisch kombiniert.

## Strukturelle Grenze

Original, A und B müssen dieselbe Top-Level-PAK-Verzeichnisstruktur besitzen: gleiche
UUIDs und Ressourcentypen. PAKPY-Mods ersetzen und verändern vorhandene Ressourcen; das
Hinzufügen oder Entfernen vollständiger Top-Level-Assets wird vom aktuellen PAK-Rebuilder
nicht unterstützt. Neue Inhalte innerhalb einer GFX/SWF-, TXTR-, ROOM- oder anderen
bestehenden Ressource sind davon nicht betroffen.
