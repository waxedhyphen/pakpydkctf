# DKCTF Hard Mode – Funky unabhängig vom Funky-Modus auswählbar

Diese Datei dokumentiert den kleinen AVM2-Zwischenschritt während des Umbaus auf zwei unabhängige Hard-Mode-Kong-Selectoren.

## Ziel

Der vorhandene Hard-Mode-Selector soll immer alle fünf Kongs durchlaufen können:

```text
DK -> Funky -> Diddy -> Dixie -> Cranky -> DK
```

Das gilt auch dann, wenn der globale Runtime-Wert `isFunkyMode` false ist.

Die zweite Selector-Zeile und ihre spätere P2-Logik werden durch diesen Patch nicht verändert.

## Binär bestätigte Ursache

Asset:

```text
MasterShell -> MapHUD.swf
```

Klasse:

```text
map.menu_hardmode
Klassenindex: 42
setMenu: Methode 484
```

Relevante Felder:

```text
isFunkyMode       Multiname 448
maxNumberOfKongs  Multiname 449
```

`setMenu` liest zunächst den Runtime-Wert `isFunkyMode`. Danach setzt die Methode die Zykluslänge abhängig davon auf fünf oder vier:

```asm
0x0097  getlocal_0
0x0098  getlocal_0
0x0099  getproperty isFunkyMode
0x009C  iffalse 0x00A6
0x00A0  pushbyte 5
0x00A2  jump 0x00A8
0x00A6  pushbyte 4
0x00A8  initproperty maxNumberOfKongs
```

`toggleLeft` und `toggleRight` verwenden ausschließlich `maxNumberOfKongs` für das Wraparound. Funky ist bereits im vorhandenen `kongMapping` und in `kongMappingTextIDs` enthalten. Es fehlt keine zusätzliche Funky-Funktion.

## Minimaler Patch

Nur der Wert des False-Zweigs wird geändert:

```text
Methode:        484
Code-Offset:    0xA7
Original:       04
Neu:            05
```

Die vollständige betroffene Instruktion lautet:

```text
0x00A6: 24 04  pushbyte 4
        ->
0x00A6: 24 05  pushbyte 5
```

Danach setzen beide Zweige:

```text
maxNumberOfKongs = 5
```

`isFunkyMode` selbst wird nicht verändert. Andere Funky-spezifische Spielsysteme bleiben deshalb unangetastet.

## Externes AVM2-Projekt

Der Patch ist nicht in der Python-Engine hardcodiert. Er liegt als externes Profil vor:

```text
PAKPY/avm2_profiles/dkctf_hardmode_all_kongs.json
```

Profilinhalt:

```json
{
  "schema": 1,
  "patches": [
    {
      "module_name": "<unbenannt>",
      "source": "root",
      "method_index": 484,
      "code_offset": "0xA7",
      "expected": "04",
      "replacement": "05"
    }
  ]
}
```

## Validierungsstatus

Gegen `UIPak(10).pak`, `MasterShell -> MapHUD.swf` lokal bestätigt:

```text
Original bei Methode 484 + 0xA7: 04
Neu:                              05
AVM2-Methoden:                    702 -> 702
AVM2-Methodenbodies:              702 -> 702
SWF/ABC erneut vollständig lesbar
```

Disassemblierter Ergebnisblock:

```asm
0x0099  getproperty isFunkyMode
0x009C  iffalse 0x00A6
0x00A0  pushbyte 5
0x00A2  jump 0x00A8
0x00A6  pushbyte 5
0x00A8  initproperty maxNumberOfKongs
```

Status:

```text
binär bestätigt
in PAKPY noch anzuwenden
im Spiel noch nicht bestätigt
```

## Anwendung in PAKPY

1. `UIPak(10).pak` öffnen.
2. `MasterShell -> MapHUD.swf` auswählen.
3. AVM2-Inventar öffnen.
4. AVM2-Patches öffnen.
5. `Profil laden...` wählen.
6. `PAKPY/avm2_profiles/dkctf_hardmode_all_kongs.json` laden.
7. `Vorschau anwenden` oder direkt `PAK neu bauen...` verwenden.

Beim späteren erneuten Timeline-Bau der zweiten Selector-Zeile berücksichtigt der Timeline-Editor aktive AVM2-Patches automatisch.
