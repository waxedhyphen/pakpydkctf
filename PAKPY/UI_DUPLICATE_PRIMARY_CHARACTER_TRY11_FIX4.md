# Duplicate primary character – Try 11 Fix 4

Arbeitsstand: 2026-07-26

## Status

```text
FIX 3: IM SPIEL FEHLGESCHLAGEN
FIX 4: STRUKTURELL BESTÄTIGT
FIX 4: NOCH NICHT IM SPIEL BESTÄTIGT
```

## Exakte Ursache von Fix 3

Fix 3 wählte einen inaktiven zweiten Player-Actor aus und versuchte, ihm über `CScriptMsg::Create` dieselbe Aktivierungsnachricht zu senden wie die Stock-Funktion `CPlayerProxyGOC::ActivatePlayerImpl`.

Die Script-Aktionswerte waren im Helper jedoch bytevertauscht.

Stock lädt für Aktivierung:

```text
0x422BE8  MOV  W0,#0x41430000
0x422BEC  MOVK W0,#0x5456
Resultat: 0x41435456 = ACTV
```

Stock lädt für Deaktivierung:

```text
0x422C58  MOV  W0,#0x49430000
0x422C5C  MOVK W0,#0x5456
Resultat: 0x49435456 = IACT
```

Fix 3 erzeugte dagegen:

```text
0x54564143
0x54564943
```

Diese Werte sind nicht `ACTV` und `IACT`. Deshalb konnte der zweite Actor ausgewählt und als P2 registriert werden, erhielt aber keine gültige Aktivierungsnachricht und blieb unsichtbar/inaktiv. Das erklärt gleichzeitig, warum P1s Tod weiterhin in einem Zustand ohne real aktiven P2 endete.

## Fix 4

Drei Konstanten im Helper wurden korrigiert:

```text
ACTV compare: 0x41435456
ACTV send:    0x41435456
IACT send:    0x49435456
```

Die Hookadressen, Slotregistry, Try-9+10-Records und alle übrigen Try-11-Records bleiben unverändert.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
1c8caa947f724165c26060cf34b84f53726f43e355d8927a8b3b0fdaaf13195e

Records insgesamt: 98
Try-9+10-Records: 8
Try-11-Records: 90
Helper: 0xA7A708..0xA7B0F4
Registry: 0x19E7220..0x19E7250
```

## Strukturelle Prüfung

- alle Expected-Bytes stimmen gegen die bestätigte Try-9+10-Baseline;
- keine Überlappung mit Try 9 oder Try 10;
- IPS32-Roundtrip mit `Runtime-Offset + 0x100` bestanden;
- Helpergröße und Registrybereich unverändert gültig;
- Fix 4 unterscheidet sich von Fix 3 nur im Helper-Record bei den drei Aktionskonstanten.

## Noch offen

Fix 4 muss im Spiel bestätigen:

```text
1. zweiter Actor wird sichtbar/aktiv;
2. P1 und P2 bleiben getrennt steuerbar;
3. P1-Tod verfolgt bzw. übernimmt P2 statt Kamera-Freeze;
4. P2-Tod/Rejoin funktionieren;
5. welcher visuelle/module-seitige Kong der Carrier nach dem Alias tatsächlich verwendet.
```
