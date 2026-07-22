# UI Viewer – AVM2-Runtime im gelieferten UI-Corpus

Stand: 2026-07-22

## Zweck

Diese Ergänzung stimmt die kontrollierte AVM2-Runtime auf wiederkehrende Bytecode- und Callback-Muster der gelieferten Scaleform-Filme ab. Die Sicherheitsgrenzen und die Whitelist für native Aufrufe bleiben unverändert.

## Ergänzte Bytecode-Muster

Unterstützt beziehungsweise sicher behandelt werden zusätzlich:

- allgemeine Script-Properties wie `state`, `dialogIsOff`, `allowInput` und Zählerwerte;
- `Controller.GetDataValue(...)` und `Controller.SetDataValue(...)` mit einem isolierten Vorschau-Datenspeicher;
- Zuordnung typischer Datenfelder wie `Count_Balloons`, `Count_Puzzle`, `Max_Puzzle`, `Char_P2` und KONG-Buchstaben zu den vorhandenen Game-State-Mocks;
- Casts auf `MovieClip`, `DisplayObject`, `String`, `Number`, `int`, `uint` und `Boolean`;
- konservative Behandlung von `astypelate`, `constructprop`, `hasnext2` und lokalen Zähler-Opcodes;
- Super-Aufrufe ohne versehentliche Rekursion in die überschreibende Methode;
- Timeline-Aufrufe auf einem Kind-MovieClip, ohne fälschlich die Timeline des aufrufenden Clips zu verändern.

## GetDataValue und SetDataValue

Das im Corpus häufige Muster lautet sinngemäß:

```text
Controller.GetDataValue("Quelle", "mSaveData", "Count_Balloons")
Controller.SetDataValue("Quelle", "mRuntimeData", "allowInput", true)
```

`SetDataValue` schreibt ausschließlich in einen temporären Datenspeicher des aktuellen Vorschaufilms. `GetDataValue` liest zuerst diesen Speicher und verwendet danach gegebenenfalls einen aktiven Game-State-Mock.

Die Aliase `fGetDataValue`, `fSetDataValue`, `InitDataValue` und `fInitDataValue` verwenden denselben isolierten Speicher. `FillDataDictionary`, `GetDictionary` und `ListenForData` besitzen ebenfalls sichere Vorschausemantik.

Es findet keine Kommunikation mit Spielprozess, Dateisystem oder Netzwerk statt.

## Statische AVM2-Auswertung

Die 1.342 erkannten Frame-Script-Zuordnungen verwenden im Wesentlichen den bereits unterstützten Opcode-Bestand. Als zusätzliche Namen traten vor allem `astypelate` und `constructprop` auf; je ein Script verwendete lokale Zähler beziehungsweise `hasnext2`.

Ein kontrollierter Dry-Run aller 1.342 Frame-Script-Methoden mit den realen ABC-Modulen und einem leeren DisplayObject-Sandboxmodell ergab:

- 1.342 ausgeführte Methoden;
- 0 Interpreter-Abbrüche;
- maximal 902 ausgeführte Instruktionen in einer Methode;
- 298 isolierte Script-Property-Schreibvorgänge;
- 484 sichere beziehungsweise protokollierte Callback-Aufrufe.

Dieser Dry-Run prüft Parser, Kontrollfluss und Sicherheitsabbrüche. Er ersetzt keine vollständige visuelle End-to-End-Prüfung jedes Films mit realer Display-List.

## Vollständiges Native-Callback-Inventar

Die anschließende Native-Callback-Stufe untersucht nicht nur Frame Scripts, sondern alle Methodenbodies der deduplizierten ABC-Module.

Reproduzierbarer Aufruf:

```bash
python PAKPY/scan_ui_native_callbacks.py UIPak.pak \
  --json native_callbacks.json
```

Der erweiterte Scan umfasst `FWS`, `CWS` und `GFX` und ergab:

- 47 eingebettete Filmpayloads mit `DoABC`;
- 40 eindeutige ABC-Payloads nach SHA-256-Deduplizierung;
- 0 ABC-Parserfehler;
- 134 native Callback-Namen;
- 6.730 statische Host-Call-Sites;
- 134 klassifizierte Namen;
- 0 unklassifizierte Namen im statischen Corpus.

Häufigste Callbacks:

| Callback | Call-Sites |
|---|---:|
| `SetDataValue` | 2.540 |
| `GetDataValue` | 1.740 |
| `playSound` | 676 |
| `LogEvent` | 565 |
| `ErrorEvent` | 369 |
| `ListenForData` | 106 |
| `InitDataValue` | 97 |
| `GetDictionary` | 90 |
| `Initialize` | 39 |
| `PrepareForTransition` | 35 |

ActionScript-interne Aufrufe auf `Controller.mEventDispatcher` werden dabei nicht als Host-Callbacks gezählt.

## Sichere DKCTF-Vorschauimplementierungen

Klassifiziert und isoliert behandelt werden:

- Data Read, Data Write und Data Listener;
- Navigation und Transitionen;
- Controller- und Moduswerte;
- Save/Profile-Slots;
- Shop und Extras;
- Leaderboard und Replay;
- Lifecycle- und Gameplay-Ereignisse;
- Audio-Requests;
- Telemetrie.

Die Priorität lautet:

```text
manueller Callback-Override
→ sichere Registry / Runtime-Daten / Game-State-Mock
→ DKCTF-Vorschauimplementierung
→ konservativer Default oder undefined
```

Der Inspector über `F11` zeigt alle Call-Sites, Runtime-Aufrufe, Argumentbeispiele, Kategorien und Rückgabe-Overrides. Siehe `UI_VIEWER_NATIVE_CALLBACKS.md`.

## Tests und Validierung

Zusätzlich zu den fünf allgemeinen Runtime-Tests und vier Corpus-Tests prüfen 13 Native-Callback-Tests:

- Klassifikation der kritischen Callback-Gruppen;
- Erkennung von `ExternalInterface.call` und `Controller`-Brücken;
- Ausschluss von `Controller.mEventDispatcher`;
- Registry- und Override-Priorität;
- Data-Value-Aliase, Dictionary und Listener;
- isolierte Audio- und Telemetriepuffer;
- Save-, Controller- und Transition-Zustände;
- Beobachtungsmodus und Unknown-Defaults;
- JSON-sichere Konfiguration und Exporte.

Zusätzlich wurden alle 134 statisch erkannten Namen mit repräsentativen Argumenten einmal durch die sichere Vorschauimplementierung ausgeführt:

- 134 Aufrufe;
- 0 Exceptions;
- vollständiger Runtime-Snapshot erfolgreich als JSON serialisiert.

## Grenzen

Weiterhin offen sind insbesondere:

- exakte hostseitige Signaturen einzelner Callbacks;
- asynchrone Completion-Events für Loading, Save, Leaderboard und Replay;
- reale CAUD-/CSMP-Audioausgabe;
- MSBT-Text-IDs und Sprachauswahl;
- echte Gamepad-Hardware;
- vollständige AVM2-, Event-Capture- und Bubbling-Semantik.
