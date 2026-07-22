# UI Viewer – AVM2 und Frame Scripts

Stand: 2026-07-22

## Zweck

Diese Stufe liest die ActionScript-3-Struktur aus Scaleform-`DoABC`-Tags und verbindet direkt erkennbare Frame Scripts mit den Root- und MovieClip-Timelines. Sie ist bewusst keine allgemeine ActionScript-VM.

Alle ausgeführten Aktionen wirken ausschließlich auf die Vorschau. SWF/GFX-, PAK- und Repacking-Daten werden nicht verändert.

## AVM2-Inspector

Im UI Browser öffnet `AVM2 / Frame Scripts` oder `F9` ein eigenes Fenster. Angezeigt werden:

- DoABC-Modulname, Quelle, Flags, Größe und ABC-Version;
- Constant-Pool-Größen;
- Namespaces und Multinames;
- Klassen und Basisklassen;
- Methoden und Methodenbodies;
- Traits, Scripts und Initializer;
- erkannte `addFrameScript`-Zuordnungen;
- disassemblierter AVM2-Bytecode mit aufgelösten String-, Multiname-, Methoden- und Klassenreferenzen;
- direkt erkannte Timeline-Aktionen.

Das Inventar kann als JSON gespeichert werden.

## Strukturparser

Der Parser unterstützt die strukturellen ABC-Tabellen:

- Integer-, UInt-, Double- und String-Pools;
- Namespaces, Namespace-Sets und Multinames einschließlich `TypeName`;
- Methodeninformationen und optionale Parameter;
- Metadaten;
- Instance-, Class- und Script-Informationen;
- Slot-, Const-, Method-, Getter-, Setter-, Class- und Function-Traits;
- Methodenbodies, Exception-Tabellen und Body-Traits.

Fehler in einem DoABC-Modul verhindern nicht das Laden des restlichen UI-Films. Das fehlerhafte Modul wird im Inspector mit seiner Diagnose angezeigt.

## Frame-Script-Erkennung

ActionScript-Compiler registrieren Timeline-Skripte üblicherweise über `addFrameScript`. Der Viewer analysiert den Instance-Initializer einer Klasse und ordnet dabei direkt erkennbare Paare aus Frameindex und Methodenreferenz zu.

Der ActionScript-Frameindex ist nullbasiert; im Viewer wird er als normaler SWF-Frame ab 1 dargestellt.

Beispiel:

```text
addFrameScript(0, frame1, 9, frame10)
```

wird zu:

```text
Frame 1  → frame1
Frame 10 → frame10
```

## Sicher ausgeführter Teilumfang

Nur folgende direkte Timeline-Aufrufe werden ausgeführt:

- `stop()`;
- `play()`;
- `gotoAndStop(frameOderLabel)`;
- `gotoAndPlay(frameOderLabel)`.

Die Argumente von `gotoAndStop` und `gotoAndPlay` müssen im Bytecode als direkte Zahl oder direkter String erkennbar sein. Berechnete Werte, Variablen, Bedingungen und Rückgabewerte nativer Funktionen werden nicht geraten.

Die Aktionen gelten für:

- die Dokumentklasse über `SymbolClass` mit Character-ID 0;
- exportierte MovieClip-Klassen über ihre jeweilige Character-ID;
- Root- und verschachtelte Timeline-Zustände;
- numerische Frames und vorhandene Frame-Labels.

Ein Skript wird beim Eintritt in seinen Frame einmal angewendet. Beim späteren erneuten Eintritt in denselben Frame wird es erneut ausgeführt. Manuelle `sprite_frame`-Overrides bleiben fixiert und führen für diesen Pfad keine automatische Frame-Script-Steuerung aus.

## State Inspector

MovieClip-Knoten zeigen zusätzlich:

```text
AVM2-Frame-Scripts:
- Klasse: ui.controls.MenuButton
- Frames: 1, 10, 18
- Aktionen im aktuellen Frame:
  - stop (frame1)
```

Im normalen Analysefeld stehen Anzahl der DoABC-Module, Klassen, Methoden, Frame Scripts, sicher erkannten Timeline-Aktionen und Parserfehler.

## Validierung am bereitgestellten UI-Corpus

Ein direkter Scan der eingebetteten SWF/GFX-Filme in `UIPak.pak` ergab:

- 41 Filme mit `DoABC`;
- 43 ABC-Module;
- 0 ABC-Parserfehler;
- 1.460 Klassen;
- 14.642 Methoden;
- 1.342 erkannte Frame-Script-Zuordnungen;
- 1.215 direkt ausführbare Timeline-Aktionen.

Verteilung der sicheren Timeline-Aktionen:

| Aktion | Anzahl |
|---|---:|
| `stop` | 908 |
| `gotoAndPlay` | 228 |
| `gotoAndStop` | 70 |
| `play` | 9 |

Die übrigen erkannten Frame Scripts bleiben im Inspector und Disassembly sichtbar, werden aber nur ausgeführt, wenn ihre Operationen in den sicheren Teilumfang fallen.

Zusätzlich prüfen fünf synthetische Tests ABC-Tabellen, DoABC, Disassembly, `addFrameScript`, direkte Timeline-Aktionen und JSON-Inventar.

## Grenzen

Noch nicht ausgeführt werden insbesondere:

- allgemeine AVM2-Stack- und Objektsemantik;
- Konstruktorlogik außerhalb der statischen `addFrameScript`-Erkennung;
- Bedingungen, Schleifen und Exceptions;
- Property-Zuweisungen wie `visible`, `alpha`, `text` oder `htmlText`;
- dynamische DisplayObjects;
- Events, Timer und Eingabe;
- native Scaleform- und Spielcallbacks;
- MSBT- und Sprachlogik.

Unbekannte oder neue AVM2-Opcodes bleiben im Disassembly als `op_XX` sichtbar. Sie werden nicht ausgeführt.

## Nächster Schritt

Die nächste AVM2-Ausbaustufe ergänzt eine kleine kontrollierte Interpreter-Laufzeit mit:

1. lokalen Variablen und Operand-Stack;
2. einfachen Verzweigungen;
3. Property-Lesen und -Schreiben auf vorhandenen DisplayObjects;
4. Text-, Sichtbarkeits- und Alpha-Änderungen;
5. einer Registry für sichere native Callback-Stubs, die mit den vorhandenen Game-State-Mocks verbunden wird.
