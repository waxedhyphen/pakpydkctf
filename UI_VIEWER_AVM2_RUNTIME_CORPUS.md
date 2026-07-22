# UI Viewer – AVM2-Runtime im gelieferten UI-Corpus

Stand: 2026-07-22

## Zweck

Diese Ergänzung stimmt die kontrollierte AVM2-Runtime auf wiederkehrende Bytecode- und Callback-Muster der gelieferten Scaleform-Filme ab. Die Sicherheitsgrenzen und die Whitelist für native Aufrufe bleiben unverändert.

## Ergänzte Muster

Unterstützt beziehungsweise sicher behandelt werden zusätzlich:

- allgemeine Script-Properties wie `state`, `dialogIsOff`, `allowInput` und Zählerwerte;
- `Controller.GetDataValue(...)` und `Controller.SetDataValue(...)` mit einem isolierten Vorschau-Datenspeicher;
- Zuordnung typischer Datenfelder wie `Count_Balloons`, `Count_Puzzle`, `Max_Puzzle`, `Char_P2` und KONG-Buchstaben zu den vorhandenen Game-State-Mocks;
- Casts auf `MovieClip`, `DisplayObject`, `String`, `Number`, `int`, `uint` und `Boolean`;
- konservative Behandlung von `astypelate`, `constructprop`, `hasnext2` und lokalen Zähler-Opcodes;
- Super-Aufrufe ohne versehentliche Rekursion in die überschreibende Methode;
- Timeline-Aufrufe auf einem Kind-MovieClip, ohne fälschlich die Timeline des aufrufenden Clips zu verändern.

Nicht registrierte Sound-, Telemetrie- und Spielcallbacks wie `playSound` oder `LogEvent` bleiben nebenwirkungsfreie protokollierte Aufrufe.

## GetDataValue und SetDataValue

Das im Corpus häufige Muster lautet sinngemäß:

```text
Controller.GetDataValue("Quelle", "mSaveData", "Count_Balloons")
Controller.SetDataValue("Quelle", "mRuntimeData", "allowInput", true)
```

`SetDataValue` schreibt ausschließlich in einen temporären Datenspeicher des aktuellen Vorschaufilms. `GetDataValue` liest zuerst diesen Speicher und verwendet danach gegebenenfalls einen aktiven Game-State-Mock.

Es findet keine Kommunikation mit Spielprozess, Dateisystem oder Netzwerk statt.

## Statische Corpus-Auswertung

Die 1.342 erkannten Frame-Script-Zuordnungen verwenden im Wesentlichen den bereits unterstützten Opcode-Bestand. Als zusätzliche Namen traten vor allem `astypelate` und `constructprop` auf; je ein Script verwendete lokale Zähler beziehungsweise `hasnext2`.

Ein kontrollierter Dry-Run aller 1.342 Frame-Script-Methoden mit den realen ABC-Modulen und einem leeren DisplayObject-Sandboxmodell ergab:

- 1.342 ausgeführte Methoden;
- 0 Interpreter-Abbrüche;
- maximal 902 ausgeführte Instruktionen in einer Methode;
- 298 isolierte Script-Property-Schreibvorgänge;
- 484 sichere beziehungsweise protokollierte Callback-Aufrufe.

Dieser Dry-Run prüft Parser, Kontrollfluss und Sicherheitsabbrüche. Er ersetzt keine vollständige visuelle End-to-End-Prüfung jedes Films mit realer Display-List.

## Tests

Zusätzlich zu den fünf allgemeinen Runtime-Tests prüfen vier Corpus-Tests:

- Übersetzung eingefrorener AVM2-Instruktionsdatensätze;
- Game-Mock- und Runtime-Datenzugriff über `GetDataValue`/`SetDataValue`;
- getrennte Timeline-Steuerung eines Kind-MovieClips;
- Speicherung nicht-visueller Script-Properties für spätere Bedingungen.

## Grenzen

Weiterhin offen sind insbesondere echte EventDispatcher-Semantik, Timer, vollständige Konstruktoren, dynamisch erzeugte DisplayObjects, Audioausgabe und die konkrete Implementierung aller nativen Spielcallbacks.
