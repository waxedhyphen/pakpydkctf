# Duplicate primary character – Try 11 Fix 7

Arbeitsstand: 2026-07-26

## Status

```text
FIX 5: zweiter DK während Intro-Cutscene bestätigt
FIX 5/6: nach Cutscene Rückfall auf unsteuerbaren Diddy bestätigt
FIX 7: strukturell bestätigt, noch nicht im Spiel getestet
```

## Bestätigte Ursache des Fix-5/6-Verhaltens

Fix 5 und Fix 6 änderten den Carrier erst in `CPlayerProxyGOC::AreaLoaded`, nachdem dessen kompletter `CPlayerGOC::EntityLoaded`-Pfad bereits abgeschlossen war.

Dabei wurden nur folgende Felder nachträglich geändert:

```text
CPlayer+0x14       CharacterType
CPlayerGOC+0x8C    eingebetteter CommonData-CharacterType
```

Der als Carrier verwendete Actor war zu diesem Zeitpunkt jedoch bereits vollständig mit Diddys Loaderdaten gebaut worden. Insbesondere waren bereits ausgeführt:

```text
0x2A5384  NPlayerBuilder::build_player_modules
CPlayer-Konstruktion
Controller-/Modulinitialisierung
Primitive-Set-Aufbau
Respawn-Modul-Aufbau
```

Deshalb konnte der Actor während der Cutscene kurzfristig wie DK erscheinen, fiel danach aber auf seine bereits aufgebauten Diddy-Module zurück und besaß keine funktionierende P2-Controller-/Respawn-Zuordnung.

## Fix 7

Der späte AreaLoaded-Umbau wurde entfernt. Der neue Hook liegt bei:

```text
0x2A5358  CPlayerGOC::EntityLoaded+0x28
```

Das ist vor:

```text
0x2A535C  CGameObjectComponent::EntityLoaded
0x2A5384  NPlayerBuilder::build_player_modules
CPlayer-Konstruktion
Controller-/Respawn-Aufbau
```

Bei einer aktiven Duplikatauswahl führt Fix 7 aus:

1. Den `CPlayerGOC` mit dem bereits gewünschten eingebetteten `SLdrPlayer` als Quelle speichern.
2. Den nächsten anderen primären Player-GOC als Carrier bestimmen.
3. Die eigenen Object-/Link-IDs des Carriers bei `GOC+0x78/+0x80` sichern.
4. Den ursprünglichen eingebetteten Loader des Carriers mit `SLdrPlayer::~SLdrPlayer()` bei `0x2A3D50` zerstören.
5. Den vollständigen Loader der Quelle mit dem refcount-sicheren `SLdrPlayer`-Copy-Konstruktor bei `0x2A49B0` kopieren.
6. Die eigenen Carrier-IDs wiederherstellen.
7. In den unveränderten Stock-EntityLoaded-Pfad zurückkehren.

Damit werden nicht nur CharacterType-Felder, sondern CommonData, Modul-Datenpointer und der vollständige Modulvektor vor ihrer Verwendung übernommen.

## Entfernte Fix-5/6-Hooks

```text
0x4221E0  AreaLoaded late activation
0x422C38  Proxy deactivation helper
```

Diese Records sind in Fix 7 nicht mehr enthalten.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
0ec5155cce5204f3a0dcf8d3b4deb94da1fdd8d18c6959c5fe6bb9ec709b7e7d

Records gesamt: 97
Try-11-Records: 89
Helper: 0xA7A708..0xA7B028
Registry: 0x19E7220..0x19E7270
```

Alle acht bestätigten Try-9+10-Records bleiben byteidentisch enthalten. Der Ryujinx-IPS32-Bias `Runtime-Offset + 0x100` bleibt unverändert.

## Validierte Branchziele

```text
0x2A5358 -> 0xA7AF44  früher Loader-Helper
0xA7AFF4 -> 0x2A3D50 SLdrPlayer-Destruktor
0xA7B000 -> 0x2A49B0 SLdrPlayer-Copy-Konstruktor
0xA7B024 -> 0x2A535C Stock-Rückkehr
```

## Laufzeitgrenze

Noch kein In-Game-Erfolg behauptet. Der unmittelbare Test ist `DK + DK`, da der bisher beobachtete Carrier der ursprüngliche Diddy-GOC ist. Weitere Duplikattypen benötigen eine separate Bestätigung der Loader-Reihenfolge.