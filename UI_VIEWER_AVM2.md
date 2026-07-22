# UI Viewer – AVM2 und Frame Scripts

Stand: 2026-07-22

## Zweck

Diese Stufe liest die ActionScript-3-Struktur aus Scaleform-`DoABC`-Tags, verbindet `addFrameScript`-Methoden mit Root- und MovieClip-Timelines und führt einen begrenzten sicheren Bytecode-Teilumfang aus. Sie ist bewusst keine allgemeine ActionScript-VM.

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

```text
addFrameScript(0, frame1, 9, frame10)
```

wird zu:

```text
Frame 1  → frame1
Frame 10 → frame10
```

## Kontrollierte Runtime

Die neue Runtime führt Frame-Script-Methoden mit einem begrenzten Interpreter aus. Unterstützt sind:

- Operand-Stack und lokale Variablen;
- direkte Konstanten und einfache Konvertierungen;
- arithmetische Operationen und Vergleiche;
- `jump`, bedingte Sprünge und `lookupswitch`;
- direkte Aufrufe von Hilfsmethoden derselben Klasse;
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay`;
- Lesen und Schreiben vorhandener DisplayObject-Properties;
- eine explizite Registry für sichere native Callback-Stubs.

Die Runtime kann im Browser mit `AVM2 Runtime` deaktiviert werden. `Runtime neu ausführen` beziehungsweise `F10` verwirft den erzeugten Runtime-Zustand und führt die aktuellen Frame Scripts erneut aus.

Details: `UI_VIEWER_AVM2_RUNTIME.md`.

## DisplayObject-Properties

Auf bereits vorhandenen Instanzen werden derzeit unterstützt:

- `visible`;
- `alpha`;
- `text`;
- `htmlText`.

Die Objektauflösung verwendet Instanznamen, Textvariablen, Symbolklassen und stabile Inspector-Pfade. Manuelle Inspector-Overrides besitzen weiterhin Vorrang vor Runtime-Werten.

MovieClip- und EditText-Knoten zeigen aktive Werte unter:

```text
AVM2-Runtime:
- visible: false
- alpha: 0.5
- text: 12500
```

## Callback-Stubs und Game-Mocks

`ExternalInterface.call(...)` wird nicht an beliebige Host-Funktionen weitergeleitet. Zulässig sind nur explizit registrierte, nebenwirkungsfreie Callbacks sowie lesende Zugriffe auf aktivierte Game-State-Mocks.

Die Registry kann intern erweitert werden über:

```python
ui_browser.register_avm2_native_callback(
    "GetExampleValue",
    lambda context, arguments: 123,
)
```

Nicht registrierte Namen liefern `undefined` und werden protokolliert.

## Sicherheitsgrenzen

- maximal 8192 Instruktionen pro Ausführung;
- maximale Aufruftiefe 16;
- maximal acht unmittelbar verkettete Frame-Sprünge;
- keine Dateisystem-, Prozess-, Netzwerk- oder beliebigen Python-Aufrufe;
- nicht unterstützte Opcodes brechen nur die betroffene Methode ab.

## Validierung am bereitgestellten UI-Corpus

Ein direkter Scan der eingebetteten SWF/GFX-Filme in `UIPak.pak` ergab:

- 41 Filme mit `DoABC`;
- 43 ABC-Module;
- 0 ABC-Parserfehler;
- 1.460 Klassen;
- 14.642 Methoden;
- 1.342 erkannte Frame-Script-Zuordnungen;
- 1.215 direkt erkennbare Timeline-Aktionen.

| Aktion | Anzahl |
|---|---:|
| `stop` | 908 |
| `gotoAndPlay` | 228 |
| `gotoAndStop` | 70 |
| `play` | 9 |

Fünf Parser-/Inventartests und fünf Runtime-Tests prüfen ABC-Tabellen, Disassembly, Frame-Script-Bindings, Branches, Property-Zuweisungen, Timeline-Sprünge, Callback-Mocks und Override-Vorrang.

## Grenzen

Noch nicht vollständig ausgeführt werden insbesondere:

- allgemeine AVM2-Objekt-, Prototyp- und Klassen-Semantik;
- Konstruktoren und Script-Initializer außerhalb der Frame-Script-Zuordnung;
- Exception-Handling und komplexe Iteration;
- dynamisch erzeugte oder entfernte DisplayObjects;
- Events, Timer und Eingabe;
- beliebige native Scaleform- und Spielcallbacks;
- MSBT- und Sprachlogik.

Unbekannte oder neue AVM2-Opcodes bleiben im Disassembly als `op_XX` sichtbar. Sie werden nicht geraten.

## Nächster Schritt

Die nächste Ausbaustufe erweitert die kontrollierte Runtime um Konstruktor-/Initializer-Zustände, zusätzliche DisplayObject-Properties, Event-Dispatcher-Grundlagen und eine corpus-spezifische Callback-Namenszuordnung.
