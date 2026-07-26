# Duplicate primary character – Try 11 Fix 3

Arbeitsstand: 2026-07-26

## Status

```text
FIX 2: IM SPIEL FEHLGESCHLAGEN
FIX 3: STRUKTURELL BESTÄTIGT
FIX 3: NOCH NICHT IM SPIEL BESTÄTIGT
```

## Fix-2-Ergebnis

Im Spiel bestätigt:

- Levelstart funktioniert;
- kein zweiter Spieler wird sichtbar;
- beim Tod von P1 bleibt die Kamera stehen;
- kein Rejoin ist möglich;
- das Verhalten ist gegenüber Fix 1 unverändert.

## Warum Fix 2 wirkungslos blieb

Fix 2 patchte `NPlayerUtils::SpawnOtherPlayer` bei `0x27C910`. Dieser Pfad ist nicht der normale Levelstartpfad der Menüauswahl. Der einzige bestätigte direkte Aufrufer gehört zu einem Pre-Death-/Grab-Throw-Pfad.

Der tatsächliche Levelstart läuft über:

```text
CPlayerProxyGOC::AreaLoaded
 -> CPlayerProxyGOC::ForEachProxyPlayer
 -> CPlayerProxyGOC::ActivatePlayerImpl
```

`ForEachProxyPlayer` iteriert die geladenen `CPlayerGOC`s und filtert sie über den CharacterType-Bitfield des Proxys. Bei identischen P1/P2-CharacterTypes trifft dieser Bitfield stock nur den einen Actor dieses Typs. Deshalb wurde der Fix-2-Carrierselector beim Levelstart nie aufgerufen.

## Fix-3-Hooks

```text
0x422BC8  CPlayerProxyGOC::ActivatePlayerImpl
0x422C38  CPlayerProxyGOC::DeactivatePlayerImpl
```

### Aktivierung

Bei aktiver Duplikatauswahl:

1. der regulär gefundene Actor bleibt logischer P1;
2. aus den bereits geladenen Primary-Player-Actors wird ein inaktiver, eigener Actor ausgewählt;
3. dieser Actor wird in `PlayerBySlot[1]` eingetragen;
4. sein `CPlayer`-CharacterType wird auf die gewünschte Duplikat-ID gesetzt;
5. für ihn wird dieselbe Stock-`ACTV`-ScriptMessage erzeugt wie im originalen Proxycode;
6. der Originalpfad aktiviert anschließend P1;
7. weitere Callbacktreffer derselben Proxyaktivierung werden über ein Registry-Gate übersprungen.

### Deaktivierung

Der Deaktivierungshook erzeugt `IACT` für den logischen P2-Actor, lässt den Stockpfad P1 deaktivieren und setzt das Aktivierungsgate für den nächsten Lifecycle zurück.

## Erhaltener Bestand

- alle acht Try-9+10-Records bleiben byteidentisch;
- Fix 1s korrigierter `EntityLoaded`-Rücksprung bleibt enthalten;
- die slotbasierten Index-, HP-, Checkpoint-, Respawn- und Controllerpfade bleiben enthalten;
- der Item-3-Todesguard bleibt enthalten;
- IPS32 verwendet weiterhin `Runtime-Offset + 0x100`.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

Try-9+10-Records: 8
Try-11-Records: 90
Gesamt: 98
Helper: 0xA7A708..0xA7B0F4
Helper-Größe: 2540 Bytes

IPS SHA-256:
87a8daff32b3dd4959fe13e4691b57ddaa2d49895666b37cb36378b77adeb441
```

## Strukturelle Validierung

- Hookbytes stimmen gegen die bestätigte Try-9+10-Baseline;
- Aktivierungshook brancht nach `0xA7AFB8`;
- Deaktivierungshook brancht nach `0xA7B064`;
- der Helper passt in die belegte Helperregion und endet vor `0xA7B1B8`;
- alle Try-9+10-Records bleiben unverändert;
- keine Recordüberlappung;
- IPS32-Roundtrip und simulierte `.text`-/`.data`-Anwendung bestanden;
- callee-saved Register der Stock-Proxyfunktionen werden vor dem Rücksprung wiederhergestellt;
- der originale StateManager-Parameter wird nach internen Helpercalls vor dem Stock-Rücksprung wieder in `X1` gesetzt.

## Laufzeitgrenze

Der zweite Spieler ist ein echter eigener Actor, stammt intern aber zunächst von einem anderen vorhandenen Kong-GOC. Der `CPlayer`-CharacterType wird auf die Duplikat-ID gesetzt. Ob Modell, PrimitiveSets, Module und Fähigkeiten vollständig dieser Änderung folgen, ist statisch nicht beweisbar. Fix 3 darf daher erst nach dem In-Game-Test als Duplicate-Kong-Fix bezeichnet werden.

## Ersttest

```text
1. normaler 2P: DK + DK
2. prüfen, ob P2 sichtbar und steuerbar ist
3. P1-Tod und Rejoin
4. P2-Tod und Rejoin
5. Checkpoint
6. unterschiedliche Kongs als Regression
7. Hard-Mode-2P: DK + DK
```