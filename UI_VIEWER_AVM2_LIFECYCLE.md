# UI Viewer – AVM2-Lifecycle, Events und Timer

Stand: 2026-07-22

## Zweck

Diese Stufe erweitert die kontrollierte AVM2-Runtime um den Lebenszyklus vorhandener Scaleform-Klassen. Script-, Klassen- und Instanz-Initializer können ausgeführt werden; außerdem stehen eine isolierte EventDispatcher-Grundlage und deterministische Timer zur Verfügung.

Alle Zustände bleiben reine Vorschauzustände. Es werden keine SWF/GFX-, GFXL-, TXTR-, MSBT-, PAK- oder Repacking-Daten verändert. Native Aufrufe erhalten weiterhin keinen direkten Zugriff auf Betriebssystem, Dateisystem, Prozesse oder Netzwerk.

## Initializer und Konstruktoren

Für einen geladenen Film werden kontrolliert ausgeführt:

1. der Script-Initializer eines ABC-Scripts einmal pro Runtime-Generation;
2. der Klassen-Initializer einer Klasse einmal pro Runtime-Generation;
3. der Instanz-Initializer einmal pro stabilem Root- oder MovieClip-Pfad.

Bei Klassen, deren Basisklasse im selben ABC-Modul enthalten ist, werden die Basisklassen-Initializer vor dem abgeleiteten Instanz-Initializer ausgeführt. Die Vererbungskette ist auf 32 Klassen begrenzt.

Root-Initialisierung erfolgt vor dem Root-Frame-Script. Verschachtelte MovieClips werden beim ersten Erreichen ihres stabilen Timeline-Pfads initialisiert. `Runtime neu ausführen` beziehungsweise `F10` verwirft den Lifecycle-Zustand und startet die Initialisierung für den aktuellen Film erneut.

## EventDispatcher-Grundlage

Unterstützt werden:

- `addEventListener`;
- `removeEventListener`;
- `hasEventListener`;
- `willTrigger`;
- `dispatchEvent`;
- `preventDefault`;
- `stopPropagation` und `stopImmediatePropagation`;
- Listener-Priorität.

Bekannte Event-Konstanten werden auf Scaleform-/Flash-Namen abgebildet, darunter:

- `ENTER_FRAME` und `EXIT_FRAME`;
- `ADDED`, `ADDED_TO_STAGE`, `REMOVED`, `REMOVED_FROM_STAGE`;
- `CHANGE`, `COMPLETE`, `SELECT`;
- `TIMER` und `TIMER_COMPLETE`;
- `CLICK`, `MOUSE_DOWN`, `MOUSE_UP`;
- `KEY_DOWN`, `KEY_UP`;
- `FOCUS_IN`, `FOCUS_OUT`.

Custom-Event-Konstruktoren erzeugen sichere Runtime-Eventobjekte. Nicht bekannte zusätzliche Argumente bleiben als isolierte Eventdaten verfügbar.

Die aktuelle Umsetzung dispatcht direkt an die Listener des Zielobjekts. Capture-Phase, vollständiges Bubbling, Weak References und die komplette Flash-EventDispatcher-Vererbung sind noch nicht modelliert.

## Timer und Runtime-Uhr

Unterstützt werden:

- `new Timer(delay, repeatCount)`;
- `start`, `stop` und `reset`;
- `TimerEvent.TIMER` und `TimerEvent.TIMER_COMPLETE`;
- `getTimer`;
- `setTimeout` und `setInterval`;
- `clearTimeout` und `clearInterval`.

Die Runtime-Uhr folgt absichtlich der UI-Timeline. Pro abgespieltem SWF-Frame wird sie anhand der Film-Framerate fortgeschrieben. Dadurch sind Presets und Tests reproduzierbar; beim Pausieren der UI-Timeline pausieren auch Timer. Es wird keine separate Echtzeit-Thread- oder OS-Timerquelle verwendet.

Zum Schutz vor großen Zeitsprüngen werden höchstens 32 Timer-Auslösungen pro Runtime-Tick verarbeitet.

`ENTER_FRAME` wird ebenfalls über diese Timeline-Uhr ausgelöst. Änderungen eines Event-Handlers an Root- oder verschachtelten MovieClip-Timelines werden in den jeweiligen Timeline-State zurückgeschrieben.

## Analyseanzeige

Das normale Analysefeld zeigt zusätzlich:

- initialisierte ABC-Scriptmodule;
- initialisierte Klassen;
- ausgeführte Instanz-Konstruktoren;
- registrierte Event-Listener;
- vorhandene und laufende Timer;
- Stand der Runtime-Uhr;
- ausgeführte Listener-Aufrufe.

Die bestehenden AVM2-Sicherheitsgrenzen bleiben aktiv:

- höchstens 8192 Instruktionen pro Ausführung;
- maximale Methodenaufruftiefe 16;
- höchstens acht direkt verkettete Frame-Sprünge;
- keine beliebigen Host- oder nativen Aufrufe.

## Relevanz im gelieferten UI-Corpus

Ein statischer Scan der eingebetteten ABC-Module in `UIPak.pak` ergab folgende häufige Lifecycle-Muster:

| Muster | Vorkommen |
|---|---:|
| `addEventListener` | 824 |
| `dispatchEvent` | 739 |
| `removeEventListener` | 300 |
| `EventDispatcher`-Konstruktor | 99 |
| `Timer`-Konstruktor | 81 |
| `Event`-Konstruktor | 80 |
| `ENTER_FRAME` | 181 |
| `TIMER_COMPLETE` | 100 |
| `setTimeout` | 5 |

Die Zählung zeigt Bytecode-Verwendungen und ist kein Beleg dafür, dass jede vollständige Spiellogik bereits emuliert wird.

## Tests

Acht fokussierte Tests prüfen:

- einmalige Script-, Klassen- und Instanz-Initialisierung;
- Reihenfolge von Basis- und abgeleitetem Konstruktor;
- Listener hinzufügen, dispatchen und entfernen;
- Event-Konstanten und Lifecycle-Property-Speicherung;
- deterministische Timer- und `timerComplete`-Ereignisse;
- `ENTER_FRAME` über die Runtime-Uhr;
- einmalige `setTimeout`-Ausführung mit Argumenten;
- Rückschreiben von Timeline-Änderungen aus verschachtelten Event-Handlern.

## Grenzen

Noch nicht enthalten sind:

- vollständige AVM2-Prototyp-, Klassen- und Namespace-Semantik;
- Basisklassen-Initialisierung über ABC-Modulgrenzen hinweg;
- vollständiges Event-Bubbling und Capture;
- dynamisches Erzeugen oder Entfernen von DisplayObjects;
- reale Maus-, Tastatur- und Controller-Ereignisse;
- Echtzeit-Timer unabhängig von der Timeline;
- vollständige native DKCTF-Callback-Implementierungen;
- Audioausgabe sowie MSBT- und Sprachlogik.
