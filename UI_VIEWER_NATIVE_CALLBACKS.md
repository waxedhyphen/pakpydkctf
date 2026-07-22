# UI Viewer – DKCTF Native Callbacks

Stand: 2026-07-22

## Zweck

Diese Stufe bildet die Grenze zwischen ActionScript 3 und den nativen Spielsystemen nachvollziehbar ab. Der Viewer inventarisiert alle erkennbaren Aufrufe über `ExternalInterface`, `Controller`, `Model` und die Data-Value-Brücken und bietet dafür kontrollierte Vorschauimplementierungen.

Das Ziel ist nicht, beliebigen nativen Spielcode nachzubilden. Das Ziel ist ein deterministischer, untersuchbarer und sicherer Host-Ersatz für UI-Zustände.

Alle Zustände bleiben am aktuell geöffneten `SwfMovie`-Objekt. Es gibt keine Verbindung zu:

- einem laufenden Spielprozess;
- Spielständen oder anderen Dateien;
- Netzwerkdiensten oder Leaderboards;
- Telemetrie-Endpunkten;
- Audio- oder Gamepad-Geräten;
- Betriebssystem- oder Prozess-APIs.

## Erkennung der Call-Sites

Die Erkennung arbeitet auf den bereits geparsten ABC-Methodenbodies. Pro Methode wird ein begrenztes abstraktes Stackmodell verwendet. Es verfolgt:

- lexikalische Empfänger wie `ExternalInterface` und `Controller`;
- Property-Ketten wie `Controller.mEventDispatcher`;
- direkte und statische Methodenaufrufe;
- konstante String-, Zahlen-, Boolean- und Nullargumente;
- dynamische Argumentpositionen als explizites `<dynamic>`.

Ein Aufruf wird als Host-Callback erfasst, wenn eines der folgenden Muster vorliegt:

```text
ExternalInterface.call("CallbackName", ...)
Controller.GetDataValue(...)
Controller.SetDataValue(...)
GetDataValue(...)
SetDataValue(...)
InitDataValue(...)
ListenForData(...)
```

ActionScript-interne Aufrufe auf `Controller.mEventDispatcher`, etwa `addEventListener` und `removeEventListener`, werden ausdrücklich nicht als native Callbacks gewertet. Dasselbe gilt für lokale Cast-Helfer wie `Controller.int(...)`.

Jede Call-Site enthält:

- Callback-Name;
- Brückentyp beziehungsweise Empfänger;
- Kategorie und Vorschauverhalten;
- DoABC-Modul und Quelle;
- Klasse und Methode;
- Methodenindex und Bytecode-Offset;
- statisch erkennbare Argumente.

## Reproduzierbarer Corpus-Scan

Der vollständige Scan kann ohne AVM2-Ausführung wiederholt werden:

```bash
python PAKPY/scan_ui_native_callbacks.py UIPak.pak \
  --json native_callbacks.json
```

Der Scanner:

1. sucht eingebettete `FWS`-, `CWS`- und `GFX`-Filmblöcke;
2. validiert Header und Tagstruktur;
3. liest nur `DoABC`-Tags;
4. dedupliziert ABC-Payloads per SHA-256;
5. wendet denselben Call-Site-Extractor wie der UI Browser an;
6. schreibt optional alle Call-Sites und Argumentbeispiele als JSON.

Ergebnis für den bereitgestellten `UIPak.pak`:

| Messwert | Ergebnis |
|---|---:|
| Eingebettete Filmblöcke mit DoABC | 47 |
| Eindeutige ABC-Payloads | 40 |
| ABC-Parserfehler | 0 |
| Erkannte Callback-Namen | 134 |
| Statische Host-Call-Sites | 6.730 |
| Klassifizierte Callback-Namen | 134 |
| Unklassifizierte Namen im statischen Corpus | 0 |

Die Zahlen beziehen sich auf erkannte eingebettete Filmpayloads. Mehrere PAK-Einträge können identische ABC-Payloads enthalten; deshalb werden die Module für die Auswertung dedupliziert.

### Verteilung

| Kategorie | Namen | Call-Sites |
|---|---:|---:|
| Data Write | 5 | 2.690 |
| Data Read | 4 | 1.832 |
| Telemetrie | 8 | 940 |
| Audio | 4 | 684 |
| Controller | 10 | 178 |
| Navigation/Transition | 29 | 112 |
| Data Listener | 1 | 106 |
| Lifecycle | 8 | 63 |
| Extras | 19 | 39 |
| Save/Profile | 17 | 29 |
| Leaderboard/Replay | 13 | 26 |
| Gameplay Events | 8 | 16 |
| Shop | 8 | 15 |
| **Gesamt** | **134** | **6.730** |

Die häufigsten Aufrufe sind:

| Callback | Call-Sites | Kategorie |
|---|---:|---|
| `SetDataValue` | 2.540 | Data Write |
| `GetDataValue` | 1.740 | Data Read |
| `playSound` | 676 | Audio |
| `LogEvent` | 565 | Telemetrie |
| `ErrorEvent` | 369 | Telemetrie |
| `ListenForData` | 106 | Data Listener |
| `InitDataValue` | 97 | Data Write |
| `GetDictionary` | 90 | Data Read |
| `Initialize` | 39 | Lifecycle |
| `PrepareForTransition` | 35 | Navigation |
| `setModeAndControllers` | 32 | Controller |
| `FillDataDictionary` | 30 | Data Write |

## Laufzeit-Priorität

Für jeden Aufruf gilt folgende Reihenfolge:

1. **manueller Rückgabe-Override** aus dem Native-Callback-Inspector;
2. **bestehende sichere Registry, Runtime-Daten oder Game-State-Mocks**;
3. **DKCTF-spezifische Vorschauimplementierung**;
4. **deterministischer sicherer Default** oder `undefined`.

Damit bleiben bereits registrierte Testschnittstellen und Game-State-Mocks maßgeblich. Ein manueller Callback-Override ist die einzige Ebene darüber.

## Betriebsmodi

### Sicher simulieren

Dies ist der Standard. Klassifizierte Callbacks aktualisieren ausschließlich den isolierten Vorschauzustand und liefern deterministische Rückgabewerte.

### Nur beobachten

In diesem Modus werden keine zusätzlichen DKCTF-spezifischen Simulationen ausgeführt. Die bereits vorhandene sichere Runtime-Registry und die Data-Value-/Mock-Grundlage bleiben aktiv. Nicht dort behandelte Aufrufe werden nur protokolliert.

Der Modus kann im UI Browser oder im Fenster `Native Callbacks` geändert werden.

## Implementierte Kategorien

### Data Read / Data Write / Data Listener

Unterstützt werden:

```text
GetDataValue
fGetDataValue
SetDataValue
fSetDataValue
InitDataValue
fInitDataValue
GetDictionary
FillDataDictionary
ListenForData
NotifyDataValue
```

Der Datenspeicher ist nach Dictionary und Feld getrennt:

```text
("mRuntimeData", "allowInput") -> true
("mSaveData", "Count_Coins") -> 99
```

Lesereihenfolge:

1. temporärer Runtime-Datenspeicher;
2. aktiver Game-State-Mock, wenn das Feld einer bekannten Rolle entspricht;
3. nicht definiert.

`ListenForData` speichert lediglich einen begrenzten Subscription-Deskriptor. Es wird kein nativer Listener registriert.

### Navigation und Transitionen

Unter anderem werden erfasst:

```text
PrepareForTransition
TransitionState
ActivateLevelLoad
ActivateHUD
ActivateShell
ActivateMasterShell
ActivateMap
ActivateInventorySelect
ActivateDeathScreen
initGameTransition
initWorldTransition
initAreaTransition
enterPause
exitPause
retryLevel
continueLevel
quitToFrontEnd
```

Die Vorschau speichert eine geordnete Navigationshistorie sowie den aktuellen Transition-Namen und dessen Status. Es wird kein Level geladen und kein anderer SWF-Host aktiviert.

### Controller

Unterstützte Vorschauwerte umfassen:

- dynamischen Controller-Modus;
- Controller-Modus für Spieler 1 und 2;
- Motion-Status für beide Spieler;
- Reassigning-Status;
- simulierten Controller-Swap.

Typische Callbacks:

```text
IsDynamicControllerModeActive
setModeAndControllers
setPlayer1ControllerMode
setPlayer2ControllerMode
setPlayer1ControllerMotionEnabled
setPlayer2ControllerMotionEnabled
setReassigningControllerIndices
StartControllerSwap
StopControllerSwap
```

Es wird kein Hardwaregerät geöffnet. Controllerartige UI-Ereignisse stammen weiterhin ausschließlich aus der Tastaturabbildung des Viewers.

### Save/Profile

`newSaveGame`, `selectSaveGame`, `copySaveGame`, `deleteSaveGame`, `PopulateSaveData` und `initSlotData` arbeiten ausschließlich auf drei temporären Vorschau-Slots.

Ein Vorschau-Slot kann enthalten:

```json
{
  "slot": 1,
  "funky_mode": true,
  "mock_values": {
    "lives": 5,
    "banana_coins": 23
  },
  "created_in_preview": true
}
```

Es werden keine Dateien gelesen, geschrieben oder gelöscht.

### Shop

Implementiert sind sichere Zustände für:

- ausgewähltes Shop-Item;
- Vorschau-Käufe;
- Figurinenstatus;
- Health-Boost-Abfrage;
- `GetShopText` und `GetUIText` über eine lokale Texttabelle.

Ein Vorschau-Kauf verändert weder Save-Daten noch Inventar außerhalb des geöffneten Films.

### Extras

Erfasst werden Unlock- und New-Flags sowie Start-/Stop-Zustände für Kategorien und Items. Standardmäßig sind Extras in der Vorschau freigeschaltet, damit die zugehörigen UI-Zustände untersuchbar bleiben. Dieser Wert kann per Rückgabe-Override geändert werden.

### Leaderboard und Replay

Die Vorschau erzeugt bei Bedarf eine deterministische lokale CPU-Liste. Query-, Post- und Replay-Aufrufe werden lokal protokolliert. Es gibt keine Netzwerkverbindung und keinen Upload.

### Audio

`playSound`, `debugSoundPlay`, `EffectsSetting` und `MusicSetting` erzeugen nur einen Audio-Request-Datensatz:

```json
{
  "callback": "playSound",
  "sound": "UI_Menu_Button_Enter",
  "arguments": [null, "UI_Menu_Button_Enter", false],
  "path": "root/5:menu",
  "time_ms": 133.33
}
```

Die tatsächliche CAUD-/CSMP-Ausgabe folgt in einer späteren Stufe.

### Telemetrie

`LogEvent`, `ErrorEvent` und Miiverse-bezogene Aufrufe werden in einem begrenzten lokalen Ringpuffer gespeichert. Es findet kein Versand statt.

## Native-Callback-Inspector

`F11` oder die Schaltfläche `Native Callbacks` öffnet das Inventar.

Die Baumansicht ist gegliedert nach:

```text
Kategorie
  -> Callback
      -> Klasse.Methode @ Bytecode-Offset
```

Für einen Callback werden angezeigt:

- Kategorie und implementiertes Verhalten;
- Standard-Rückgabepolitik;
- Brücken und statische Call-Sites;
- Runtime-Aufrufzahl;
- Argumentbeispiele;
- vorhandener Rückgabe-Override.

### Rückgabe-Overrides

Das Feld `Rückgabe-Override (JSON)` akzeptiert jeden JSON-Wert:

```json
true
```

```json
42
```

```json
{
  "unlocked": true,
  "count": 8
}
```

Der Override wird nach Callback-Namen ohne Beachtung von Groß-/Kleinschreibung aufgelöst. Maximal 256 Overrides werden aus einem Preset übernommen.

Beispiele:

```text
GetExtrasUnlockState -> true
IsDynamicControllerModeActive -> false
GetShopText -> "Nicht genug Banana Coins"
```

## JSON-Export

Der Inspector exportiert:

- Callback-Zusammenfassungen;
- sämtliche statischen Call-Sites;
- Kategorien und Argumentbeispiele;
- Modus und Overrides;
- Runtime-Call-Log;
- Data-Value-Speicher;
- Navigation, Controller, Save, Shop, Extras und Leaderboard;
- Audio- und Telemetrie-Requests.

Das Exportformat beginnt mit:

```json
{
  "schema": 1,
  "mode": "simulate",
  "overrides": {},
  "summary": {
    "callbacks": 134,
    "call_sites": 6730
  }
}
```

Die Werte im Film-spezifischen Inspector hängen vom jeweils geöffneten Film ab. Die genannten 134 und 6.730 sind die deduplizierte Gesamtauswertung von `UIPak.pak`.

## State-Presets

Das bestehende Presetformat bleibt Version 1 und erhält optional:

```json
{
  "native_callbacks": {
    "mode": "simulate",
    "overrides": {
      "GetExtrasUnlockState": true,
      "IsDynamicControllerModeActive": false
    }
  }
}
```

Ältere Presets ohne `native_callbacks` bleiben kompatibel. Transiente Call-Logs, Vorschau-Save-Slots, Audio-Requests und Telemetriedaten werden bewusst nicht im Preset gespeichert.

## Sicherheitsgrenzen

- Keine dynamische Python-Auswertung von Callback-Namen oder Argumenten.
- Keine beliebigen Imports oder Host-Funktionsaufrufe.
- JSON-Werte werden rekursiv begrenzt und bereinigt.
- Maximal 2.000 Runtime-Call-Records.
- Maximal 500 Einträge pro Audio-, Telemetrie-, Navigation- oder Unknown-Puffer.
- Maximal 256 Callback-Overrides pro Preset.
- Bestehende AVM2-Schritt-, Tiefen-, Timer- und DisplayObject-Limits bleiben aktiv.
- Unbekannte Query-Namen erhalten nur einen konservativen Boolean-Default; andere unbekannte Aufrufe bleiben `undefined`.

## Validierung

Durchgeführt wurden:

- 13 fokussierte Unit-Tests für Klassifikation, Call-Site-Erkennung, Registry- und Override-Priorität, Data-Value-Aliase, Dictionary/Listener, Audio, Telemetrie, Save, Controller, Transition, Beobachtungsmodus, Unknown-Defaults und JSON-Sicherheit;
- Installations-Smoke-Test gegen die gepatchten Modul-Schnittstellen;
- vollständiger statischer Scan von `UIPak.pak` mit 47 Filmpayloads, 40 eindeutigen ABC-Modulen und 0 Parserfehlern;
- sicherer Dry-Run aller 134 erkannten Callback-Namen mit repräsentativen Argumenten;
- 134 von 134 Aufrufen ohne Exception;
- JSON-Serialisierung des vollständigen Runtime-Snapshots.

Die Tk-Oberfläche konnte in der headless Entwicklungsumgebung nicht visuell vollständig geprüft werden.

## Grenzen und nächster Schritt

Die native ABI wird aus ActionScript-Call-Sites abgeleitet. Ohne Ausführung des ursprünglichen Spielhosts sind Argumentbedeutung und asynchrone Completion-Events bei einigen Callbacks nur konservativ modelliert.

Noch offen sind:

- hostseitige Rückrufereignisse nach asynchronen Operationen;
- konkrete Completion-Events für Save, Loading, Leaderboard und Replay;
- exakte Text-IDs und MSBT-Sprachauswahl;
- reale CAUD-/CSMP-Audioauflösung und Wiedergabe;
- echte Gamepad-Hardware;
- Abgleich einzelner Callback-Signaturen mit dem Spielcode, sofern entsprechende Symbole oder Disassembly verfügbar werden.

Der nächste Arbeitsblock ist die **asynchrone Callback-/Audio-Stufe**: sichere Completion-Event-Queues, Zuordnung der 676 `playSound`-Call-Sites zu CAUD/CSMP-Ressourcen und anschließend MSBT-basierte Laufzeittexte.
