# Duplicate primary character – Try 11 Fix 5

Arbeitsstand: 2026-07-26

## Status

```text
FIX 4: TRY-9+10-VERHALTEN WIEDERHERGESTELLT, DUPLIKAT WEITERHIN FEHLGESCHLAGEN
FIX 5: STRUKTURELL BESTÄTIGT
FIX 5: NOCH NICHT IM SPIEL BESTÄTIGT
```

Fix 5 ist ein kombinierter ExeFS-Patch. Alle acht bestätigten Try-9+10-Records bleiben byteidentisch enthalten.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

Try-9+10-Records: 8
Try-11/Fix-5-Records: 90
Gesamt: 98 IPS32-Records
IPS-Größe: 4069 Bytes
IPS SHA-256:
8ad652b071c710b7dccd2a5c047cc01ce018839ca78a3dfea12c23b9c359008c
```

Der IPS32-Export verwendet weiterhin den bestätigten Ryujinx-Bias `Runtime-Offset + 0x100`.

## Warum Fix 4 keinen zweiten sichtbaren Spieler aktivierte

Zwei konkrete Fehler wurden im Binärfluss bestätigt.

### 1. Zu später Hook

Fix 4 hing an:

```text
0x422BC8 CPlayerProxyGOC::ActivatePlayerImpl
```

Die initiale Aktiv-/Inaktiv-Entscheidung wird jedoch bereits früher in

```text
CPlayerGOC::SetInitialState(CStateManager&) @ 0x2A6390
```

getroffen. Diese Routine wertet PlayerIndex und `GameState+0x26A0` aus, sendet `ACTV` beziehungsweise `IACT` und ruft `CPlayer::SetActive(bool)` direkt auf.

Fix 5 entfernt deshalb den Hook bei `0x422BC8` und setzt stattdessen nach dem Stock-Proxy-Durchlauf an:

```text
0x4221E0 CPlayerProxyGOC::AreaLoaded
    -> 0xA7AF44 try11_area_loaded_duplicate
    -> Rückkehr 0x4221E4
```

### 2. Falscher GOC-Pointer

Die bisherigen Carrier-Helper verwendeten:

```text
CPlayer+0x100
```

als angeblichen `CPlayerGOC*`.

Der `CPlayer`-Konstruktor speichert bei `CPlayer+0xF8` jedoch ein Pointerpaar:

```text
CPlayer+0xF8  = CPlayerGOC*
CPlayer+0x100 = CEntityGOC*
```

Damit wurden `ACTV`/`IACT` zuvor an die falsche Komponente geschickt und der Common-CharacterType an der falschen Objektstruktur verändert.

Fix 5 korrigiert alle fünf betroffenen Stellen auf:

```text
CPlayer+0xF8 -> CPlayerGOC*
```

## Fix-5-Levelstartpfad

Nach dem normalen `CPlayerProxyGOC::ForEachProxyPlayer`-Durchlauf:

1. P1- und P2-Auswahl werden aus `GameState+0x2698/+0x269C` gelesen.
2. Der Pfad läuft nur bei identischen IDs und gesetztem P2-Aktivbit.
3. P1 wird aus der bestehenden CharacterType-Registry ermittelt.
4. Die fünf geladenen Primary-Player-Pointer werden nach einem inaktiven, von P1 verschiedenen Actor durchsucht.
5. Dieser Actor wird als logischer P2-Carrier registriert.
6. `CPlayer+0x14` und `CPlayerGOC+0x8C` erhalten den gewünschten Duplikat-CharacterType.
7. `ACTV = 0x41435456` wird an den tatsächlichen `CPlayerGOC*` gesendet.
8. `CPlayer::SetActive(true)` wird direkt aufgerufen.

Der Deaktivierungspfad sendet entsprechend `IACT = 0x49435456` an den tatsächlichen `CPlayerGOC*` und ruft `SetActive(false)`.

## Gegenüber Fix 4

```text
hinzugefügt: 0x4221E0 AreaLoaded-Hook
entfernt:    0x422BC8 ActivatePlayerImpl-Hook
geändert:    Helper und vier Branches auf verschobene Helper-Einstiege
```

Unverändert bleiben:

- Try 9;
- Try 10;
- PlayerSlot-Registry;
- HP-/Inventar-Slotpfade;
- Checkpoint-/Respawn-Slotpfade;
- fehlender-P2-Todesguard;
- Runtime-SpawnOtherPlayer-Carrierpfad für spätere Kongwechsel.

## Strukturelle Validierung

Bestätigt:

- alle Expected-Bytes stimmen gegen die Try-9+10-Baseline;
- alle acht Try-9+10-Records sind byteidentisch;
- keine Record-Überlappung;
- IPS32-Parse-/Write-Roundtrip bestanden;
- Helper passt in `0xA7A708..0xA7B1B8`;
- Hook `0x4221E0` verzweigt nach `0xA7AF44`;
- Helper kehrt nach `0x4221E4` zurück und führt die verdrängte Instruktion aus;
- Deaktivierung kehrt nach `0x422C40` zurück;
- Registrierung kehrt nach `0x1F8404` zurück, ohne den früheren doppelten `SetPrimaryPlayer`-Aufruf;
- alle fünf Carrier-GOC-Zugriffe verwenden `CPlayer+0xF8`;
- im Helper existiert kein als `CPlayerGOC*` behandelter Zugriff auf `CPlayer+0x100`.

## Noch offen

Der Build ist nicht im Spiel bestätigt. Zu testen sind:

```text
1. DK + DK: P2 sichtbar und steuerbar
2. P1 stirbt, P2 lebt weiter
3. P2 stirbt und kann rejoinen
4. Checkpoint
5. Levelwechsel
6. unterschiedliche Kongs als Regression
```

Bis zur Laufzeitbestätigung wird Fix 5 nicht als funktionierender Duplicate-Kong-Fix bezeichnet.