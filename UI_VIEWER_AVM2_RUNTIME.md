# UI Viewer – Kontrollierte AVM2-Runtime

Stand: 2026-07-22

## Zweck

Diese Stufe führt einen begrenzten, explizit sicheren Teil von ActionScript-3-Frame-Scripts aus. Grundlage sind die bereits geparsten `DoABC`-Module und `addFrameScript`-Zuordnungen.

Die Runtime verändert ausschließlich den Vorschauzustand. SWF/GFX-, GFXL-, TXTR-, MSBT-, PAK- und Repacking-Daten bleiben unverändert.

## Bedienung

Unterhalb der AVM2-Leiste befinden sich:

- `AVM2 Runtime`: schaltet die kontrollierte Ausführung für den aktuellen Film ein oder aus;
- `Runtime neu ausführen`: verwirft die bisher erzeugten Runtime-Properties und führt die aktuellen Frame-Scripts erneut aus;
- `F10`: entspricht `Runtime neu ausführen`.

Im Analysefeld erscheinen Aktivstatus, Anzahl geänderter Pfade und Properties, Callback-Aufrufe sowie abgebrochene Methoden.

## Ausgeführter Bytecode-Teilumfang

Unterstützt werden derzeit:

- Operand-Stack und lokale Variablen;
- direkte Konstanten, Strings, Zahlen, Booleans, `null` und `undefined`;
- `getlocal`/`setlocal`, Scope-Grundoperationen und direkte Property-Auflösung;
- einfache arithmetische Operationen und Vergleiche;
- `jump`, bedingte Sprünge und `lookupswitch`;
- direkte Aufrufe von Methoden derselben Klasse;
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay`;
- Lesen und Schreiben vorhandener DisplayObject-Properties;
- begrenzte, registrierte native Callback-Stubs.

Zur Sicherheit gelten ein Schrittlimit von 8192 Instruktionen und eine maximale Aufruftiefe von 16 Methoden. Eine nicht unterstützte Instruktion beendet nur die betroffene Methode und wird im Analysefeld gezählt.

## DisplayObject-Properties

Frame Scripts können auf bereits vorhandenen Instanzen folgende Properties setzen:

- `visible`;
- `alpha`;
- `text`;
- `htmlText`.

Objekte werden über Instanznamen, Textvariablen, Symbolklassen und die stabilen Inspector-Pfade aufgelöst. Die erzeugten Werte werden getrennt vom SWF und getrennt von den manuellen Preset-Overrides gespeichert.

Vorrang:

1. manueller State-Inspector-Override;
2. AVM2-Runtime-Property;
3. Game-State-Mock;
4. ursprünglicher Timeline-/DefineEditText-Wert.

Der State Inspector zeigt aktive Werte zusätzlich unter `AVM2-Runtime`.

## Native Callback-Registry

Externe Aufrufe werden nicht an Betriebssystem-, Netzwerk- oder Python-Funktionen weitergeleitet. Erlaubt sind ausschließlich Einträge der Registry:

```python
ui_browser.register_avm2_native_callback(
    "GetExampleValue",
    lambda context, arguments: 123,
)
```

`ExternalInterface.call(...)` kann außerdem lesend auf aktive Game-State-Mocks zugreifen, wenn der Callback-Name semantisch einer bekannten Rolle entspricht. Beispiele sind Leben, Spielerzahl, Banana Coins, Puzzle Pieces, Timer und Punkte.

Nicht registrierte Callback-Namen liefern `undefined` und werden protokolliert.

## Frame-Script-Verhalten

Ein Frame Script wird beim Eintritt in seinen Root- oder MovieClip-Frame einmal ausgeführt. Bei einem späteren erneuten Eintritt wird es erneut ausgeführt. Direkte Sprünge können weitere Frame Scripts auslösen; zum Schutz werden höchstens acht unmittelbar verkettete Framewechsel verarbeitet.

Manuelle `sprite_frame`-Overrides bleiben fixiert und umgehen die automatische Runtime-Steuerung für den jeweiligen Pfad.

## Performance

Runtime-Properties besitzen eine eigene Revisionsnummer und sind Bestandteil des Stage-Frame-Cache-Schlüssels. Ein bereits gecachter Frame wird deshalb nicht wiederverwendet, wenn ein Frame Script Sichtbarkeit, Alpha oder Text geändert hat.

## Tests

Fünf fokussierte Tests prüfen:

- Sichtbarkeits- und Alpha-Zuweisungen an vorhandene Kinder;
- bedingte Sprünge;
- `ExternalInterface.call` mit Game-State-Mock;
- Timeline-Sprünge aus dem Interpreter;
- Vorrang manueller Overrides.

## Grenzen

Noch nicht enthalten sind:

- vollständige AVM2-Objekt- und Prototypsemantik;
- allgemeine Konstruktor- und Script-Initializer-Ausführung;
- Exception-Handling und komplexe Iteration;
- dynamisches Erzeugen oder Entfernen von DisplayObjects;
- Events, Timer und Eingabe;
- beliebige native Spielcallbacks;
- MSBT- und Sprachlogik.

Nicht unterstützte Methoden bleiben im AVM2-Inspector vollständig disassemblierbar.
