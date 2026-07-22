# UI Viewer – Asynchrone Native-Events und CAUD/CSMP-Audio

Stand: 2026-07-22

## Zweck

Diese Stufe ergänzt die sichere Native-Callback-Schicht um zwei für reale UI-Abläufe wesentliche Host-Funktionen:

1. native Operationen können auf der deterministischen SWF-Uhr verzögert abgeschlossen werden und anschließend ActionScript-Events beziehungsweise Data-Value-Änderungen auslösen;
2. `playSound`-Aufrufe werden über echte `CAUD`-Definitionen auf `CSMP`-Samples aufgelöst, aus Nintendo-DSP-ADPCM in PCM/WAV dekodiert und optional lokal abgespielt.

Die Implementierung bleibt vollständig auf den Vorschaufilm begrenzt. Es gibt weiterhin keinen Zugriff auf Spielprozess, Netzwerk, Spielstände, Telemetrie-Endpunkte oder beliebige Host-Funktionen.

## Architektur

```text
ActionScript / ExternalInterface
  -> sichere Native-Callback-Schicht
  -> unmittelbarer deterministischer Rückgabewert
  -> optionaler Async-Request auf der SWF-Uhr
       -> Data-Value-Updates
       -> Controller.mEventDispatcher
       -> Controller
       -> stabiler DisplayObject-Pfad

playSound(name)
  -> normalisierter Soundname
  -> CAUD im aktuellen oder requireten PAK
  -> CAUD.csmp_refs
  -> CSMP-Ressource
  -> DSP-ADPCM-Decoder
  -> PCM/WAV
  -> optionaler fester Viewer-Backend
```

Die Rückgabe eines nativen Aufrufs bleibt sofort verfügbar. Die Completion-Queue bildet ausschließlich die später eintreffenden Host-Ereignisse nach.

## Deterministische Completion-Queue

Die Queue verwendet dieselbe Laufzeituhr wie AVM2-Timer und `ENTER_FRAME`. Sie läuft nur weiter, wenn die UI-Timeline weitergeschaltet wird. Dadurch sind Screenshots, Presets und Debug-Abläufe reproduzierbar.

Jeder Queue-Eintrag enthält:

```json
{
  "id": 12,
  "kind": "completion",
  "callback": "newSaveGame",
  "arguments": [1, false],
  "result": true,
  "path": "root/5:saveMenu",
  "queued_ms": 1000.0,
  "due_ms": 1120.0,
  "events": [
    "newSaveGameComplete",
    "SaveBusy",
    "isSaveDataPopulated",
    "nativeComplete"
  ],
  "data_updates": [
    {
      "dictionary": "mRuntimeData",
      "field": "SaveBusy",
      "value": false
    }
  ]
}
```

### Ereignisziele

Bei Fälligkeit wird jedes Event an die vorhandene isolierte AVM2-Ereignisschicht gesendet:

1. `Controller.mEventDispatcher`;
2. `Controller`;
3. den stabilen DisplayObject-Pfad des ursprünglichen Aufrufs mit normalem Pfad-Bubbling.

Eventdaten enthalten mindestens Request-ID, Callback-Name, Argumente, Rückgabewert, Erfolgsstatus und Quelle `native-preview`.

### Data-Value-Benachrichtigungen

Schreibende Data-Value-Aufrufe erzeugen zusätzlich feldbezogene Events. Beispiel:

```text
SetDataValue(..., "Count_Balloons", 7)
  -> Count_Balloons
  -> dataValueChanged
```

Die Werte werden vor dem Event in den vorhandenen filmbezogenen Preview-Datenspeicher geschrieben. Dadurch liest ein nachfolgender Event-Handler bereits den neuen Wert.

### Simulierte Abschlusszeiten

Die Zeiten sind absichtlich kurz, fest und nicht als Original-Spielzeiten zu verstehen:

| Bereich | Vorschauverzögerung | Typische Events |
|---|---:|---|
| Navigation / Transition | 80 ms | `TransitionComplete`, `isLoadingIn`, `nativeComplete` |
| Save / Profile | 120 ms | `<Callback>Complete`, `SaveBusy`, `isSaveDataPopulated` |
| Extras Load / Unload | 120 ms | `UnitLoadComplete`, `nativeComplete` |
| Leaderboard / Replay | 180 ms | `LeaderboardComplete`, `nativeComplete` |
| Audio | echte dekodierte Dauer | `soundComplete`, `<Soundname>Complete` |

`SaveBusy` und `isLoadingIn` werden als echte Preview-Data-Values gesetzt und beim Abschluss wieder zurückgenommen.

### Priorität und Nebenwirkungen

Die bestehende Callback-Priorität bleibt unverändert:

```text
manueller Native-Callback-Override
-> sichere Registry / Runtime-Daten / Game-State-Mock
-> DKCTF-Vorschauimplementierung
-> sicherer Default oder undefined
```

Ein manueller Callback-Override unterdrückt auch die neue Completion- und Audio-Nachbearbeitung. Im Modus `Nur beobachten` werden ebenfalls keine neuen Completion-Ereignisse erzeugt.

## CAUD-Katalog

Beim Öffnen eines Films baut der Viewer einen gemeinsamen, schreibgeschützten Audiokatalog aus:

- dem aktuell geöffneten PAK;
- allen im Require-Store geladenen PAKs.

Pro `CAUD` werden gespeichert:

- Soundname;
- Quell-PAK;
- CAUD-UUID;
- referenzierte CSMP-UUIDs;
- Lautstärke und Gain;
- Loop-Flag;
- Parserdiagnose.

Die Namensauflösung ignoriert Groß-/Kleinschreibung sowie Trennzeichen. Dadurch werden beispielsweise `UI_Razz_Polite`, `ui-razz polite` und `ui_razz_polite` identisch behandelt. Mehrdeutige Namen bleiben in stabiler PAK-/UUID-Reihenfolge; der Inspector zeigt sämtliche Datensätze.

### Robuster CAUD-Fallback

Ein kleiner Teil der bereitgestellten CAUD-Varianten weicht von der derzeit vollständig beschriebenen Struktur ab. In diesem Fall bricht der Katalogaufbau nicht ab. Der Viewer liest konservativ den Namen und sucht ausschließlich tatsächlich im Asset vorhandene CSMP-UUIDs. Es werden keine ähnlich klingenden Soundnamen geraten.

## CSMP-Decoder

`ui_audio_codec.py` implementiert einen read-only Decoder für:

- interne `RFRM/CSMP`-Assets aus PAK-Dateien;
- das bereits unterstützte rohe `CSMP`-Austauschformat;
- ein bis vier DSP-ADPCM-Kanäle;
- Mono- und Stereoausgabe;
- deterministisches Downmixing von vier Kanälen auf Stereo;
- 16-Bit-PCM-WAV-Export.

### Dekodierpfad

```text
CSMP
  -> FMTA: Kanalzahl und Format
  -> DATA: gleich große Kanalblöcke
  -> 0x60-Byte Nintendo-DSP-Header pro Kanal
  -> 8-Byte-ADPCM-Frames mit je 14 Samples
  -> Prädiktor/Koeffizienten/History
  -> begrenztes signed 16-Bit PCM
  -> WAV
```

Kanalzahl, Sampleanzahl, Sample-Rate, Blockgrenzen und Koeffizientenzugriffe werden vor beziehungsweise während der Dekodierung validiert.

### Sicherheitsgrenzen

- höchstens 4 Eingangskanäle;
- höchstens 20.000.000 Samples pro Kanal;
- höchstens 256 MiB dekodiertes PCM pro Sound;
- 64-MiB-LRU-Cache für fertige WAV-Vorschauen;
- ungültige oder abgeschnittene Kanäle betreffen nur den jeweiligen Sound;
- keine externe Codec-Bibliothek und kein Shell-/Prozessaufruf.

## Wiedergabe

Audio ist standardmäßig deaktiviert. Die Optionen im UI Browser sind:

- `UI-Sounds`: automatische Wiedergabe von aufgelösten `playSound`-Requests;
- `Stumm`: unterdrückt lokale Ausgabe;
- `Lautstärke`: 0 bis 100 Prozent;
- `Audio / Async` oder `F12`: Katalog- und Queue-Inspector.

Die effektive Preview-Lautstärke kombiniert Viewer-Wert, CAUD-Volume und CAUD-Gain und wird begrenzt.

### Backend

Unter Windows verwendet der Viewer ausschließlich das Python-Standardmodul `winsound` mit WAV-Daten aus dem Speicher. Die Wiedergabe läuft in einem Daemon-Thread, damit der UI-Renderpfad nicht blockiert.

Auf Plattformen ohne `winsound` bleiben Katalog, Auflösung, Dekodierung, Dauerberechnung und WAV-Export vollständig verfügbar; nur die direkte lokale Ausgabe fehlt. Ein Fehler des Audio-Backends stoppt weder AVM2 noch Rendering.

Das CAUD-Loop-Flag wird inventarisiert. Die aktuelle einfache WAV-Vorschau spielt einen Datensatz einmal ab; eine dauerhafte Loop-Stimme wird noch nicht verwaltet.

## Audio-/Async-Inspector

`F12` öffnet zwei Registerkarten.

### CAUD / CSMP Audio

- Filter nach Soundname;
- Quell-PAK und Anzahl der CSMP-Varianten;
- CAUD-UUID und alle CSMP-UUIDs;
- Loop, Volume, Gain und Parserdiagnose;
- manuelles Abspielen;
- Stop;
- WAV-Export.

### Async Queue

- ausstehende Requests mit Fälligkeitszeit und Events;
- zuletzt abgeschlossene Requests;
- fällige Requests sofort verarbeiten;
- alle Requests kontrolliert abschließen;
- Queue leeren.

Das manuelle Abschließen ist ein Debug-Werkzeug. Es verändert weiterhin nur den Zustand des geöffneten Vorschaufilms.

## Presetformat

Das bestehende State-Presetformat Version 1 erhält optional:

```json
{
  "audio_preview": {
    "enabled": false,
    "muted": false,
    "volume": 0.65
  }
}
```

Gespeichert werden nur die Benutzereinstellungen. Ausstehende Completion-Requests, dekodierte WAV-Daten, Audio-Requests und abgespielte Stimmen sind transient und werden nicht in Presets geschrieben. Ältere Presets bleiben kompatibel.

## Reproduzierbarer Corpus-Scan

```bash
python PAKPY/scan_ui_audio_links.py UIPak.pak \
  --require PreLoadPak.pak \
  --require MiscData.pak \
  --decode \
  --json ui_audio_links.json
```

Der Scanner:

1. liest die PAK-Verzeichnisse mit dem vorhandenen `pak_core`;
2. baut denselben CAUD-Katalog wie der UI Browser;
3. verwendet das vorhandene statische Native-Callback-Inventar;
4. extrahiert konstante Soundargumente aus `playSound` und `debugSoundPlay`;
5. ordnet sie ohne Fuzzy-Guessing CAUD-Namen zu;
6. dekodiert optional die erste CSMP-Variante jedes aufgelösten Namens;
7. schreibt alle Links und Diagnosen als JSON.

### Ergebnis des bereitgestellten Corpus

PAK-Inventar:

| PAK | CAUD | CSMP |
|---|---:|---:|
| `UIPak.pak` | 133 | 151 |
| `PreLoadPak.pak` | 876 | 1.096 |
| `MiscData.pak` | 1 | 1 |
| **Gesamt** | **1.010** | **1.248** |

Der gemeinsame Katalog enthält 1.010 CAUD-Datensätze und 999 normalisierte Namen.

Das statische AVM2-Inventar enthält 680 Audio-Bridge-Call-Sites: 676 `playSound`- und 4 `debugSoundPlay`-Aufrufe. Daraus entstehen 69 konstante Strings beziehungsweise 68 normalisierte Namen.

- 67 Namen werden eindeutig auf CAUD aufgelöst;
- ein Eintrag ist ein alter ActionScript-Librarypfad, `../libs/music/FrontEnd_ButtonPress_In.mp3`, für den im bereitgestellten PAK-Satz kein gleichnamiges CAUD existiert;
- alle 67 aufgelösten ersten CSMP-Varianten wurden ohne Decoderfehler verarbeitet.

Dekodierte Verteilung:

| Eigenschaft | Ergebnis |
|---|---:|
| 22.050 Hz | 3 Sounds |
| 24.000 Hz | 6 Sounds |
| 32.000 Hz | 58 Sounds |
| Mono | 26 Sounds |
| Stereo | 41 Sounds |
| kürzeste Dauer | 0,0295625 s |
| längste Dauer | 7,9951875 s |
| Gesamtdauer der 67 Prüfvarianten | 101,4475 s |

Als konkrete End-to-End-Prüfung wurde `UI_Menu_Button_Enter` über CAUD und CSMP dekodiert: Stereo, 32.000 Hz, 25.601 Samples und rund 0,80003 Sekunden.

## Tests und Validierung

Die fokussierte Testsuite umfasst 13 Tests:

- Mono-DSP-Frame;
- Stereo-Interleaving und WAV-Header;
- Lautstärkebegrenzung;
- abgeschnittene Kanalblöcke;
- Audio-Preset-Kompatibilität;
- normalisierte Soundnamen;
- zeitgesteuerte Completion- und Data-Value-Updates;
- Eventdispatch an die Controller-Brücke;
- Listenerzählung pro Completion;
- Data-Value-Feldbenachrichtigungen;
- Unterdrückung aller Nachwirkungen bei manuellem Callback-Override;
- deterministischer Save-Abschluss;
- Audioauflösung und `soundComplete` anhand der echten dekodierten Dauer.

Zusätzlich wurden Syntax- und Installations-Smoke-Tests sowie der vollständige Corpus-Scan durchgeführt. Die direkte `winsound`-Ausgabe konnte in der Linux-Headless-Umgebung nicht akustisch geprüft werden; der erzeugte reale WAV-Datenstrom wurde strukturell validiert.

## Grenzen und nächster Schritt

Noch offen sind:

- exakte hostseitige Eventnamen und Payloads für einzelne Callbacks, sofern sie nicht aus dem ActionScript ableitbar sind;
- dauerhafte Loop-Stimmen, Mixing mehrerer Stimmen und Voice-Prioritäten;
- echte Plattform-Gamepads;
- MSBT-Text-ID-Auflösung und Sprachauswahl;
- pixelgenaue Shape-/Masken-HitTests und klassische `DefineButton`-/`DefineButton2`-Tags.

Der nächste Arbeitsblock ist die **MSBT- und Laufzeittext-Stufe**: Sprachbundles inventarisieren, Text-IDs aus Data-Value-/Callback-Argumenten zuordnen, sichere Sprachumschaltung ergänzen und dynamische TextFields mit den lokalisierten Laufzeittexten verbinden.
