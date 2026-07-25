# Duplicate primary character – Try 11 Fix 1

Arbeitsstand: 2026-07-26

## Status

```text
TRY 11 ORIGINAL: IM SPIEL FEHLGESCHLAGEN
FIX 1: STRUKTURELL BESTÄTIGT
FIX 1: LEVEL-EINSTIEG NOCH NICHT IM SPIEL BESTÄTIGT
```

Der ursprüngliche kombinierte Try-9+10+11-IPS startet bis ins Menü, crasht aber beim Betreten eines Levels während `CPlayer`-/PrimaryPlayer-Initialisierung.

## Crashlog

```text
PC 0x1FA354  CPlayer::GetCharacterType()
LR 0x2CE158  CStateManagerGameData::SetPrimaryPlayer(CPlayer&)+0x1C
Invalid memory access at 0x0
```

Der Stack führt über:

```text
CPlayerModuleManager::PreOwnerEntityLoaded
CPlayerGOC::EntityLoaded
CEntityGOC::EntityLoaded
CGameAreaObject::AddObjectsOverTime_Process
CGameAreaLoader::ContinueLoad
```

Damit ist der Fehler dem Try-11-Actor-Registrierungspfad beim Level-Laden zugeordnet. Try 9 und Try 10 sind nicht betroffen.

## Exakte Ursache

Der Try-11-Helper bei `0xA7A708` ruft bereits einmal korrekt auf:

```text
CStateManagerGameData::SetPrimaryPlayer(GameData, Player)
```

Danach endete der Helper ursprünglich mit:

```text
0xA7A7B0  B 0x1F8424
```

`0x1F8424` liegt im originalen Abschluss von `CPlayer::EntityLoaded`. Dieser stellt die Register wieder her und erreicht anschließend bei `0x1F8430` erneut den Stock-Tailcall auf `SetPrimaryPlayer`.

Folge:

```text
1. Helper ruft SetPrimaryPlayer korrekt auf.
2. Rücksprung nach 0x1F8424.
3. Stock-Tailcall ruft SetPrimaryPlayer ein zweites Mal auf.
4. X0 enthält jetzt nur noch den vorherigen Rückgabewert 1 statt GameData*.
5. SetPrimaryPlayer ruft GetCharacterType in ungültigem Kontext auf.
6. Invalid memory access / Level-Load-Crash.
```

Die Register im Crashlog bestätigen genau diesen Zustand:

```text
X19 = gültiger CPlayer*
X20 = 1  (von SetPrimaryPlayer aus X0 übernommen)
PC  = CPlayer::GetCharacterType
```

## Fix 1

Nur der letzte Branch des Registrierunghelpers wird geändert:

```text
0xA7A7B0
alt: B 0x1F8424
neu: B 0x1F8404
```

`0x1F8404` führt denselben Register-/Stack-Epilog aus, endet aber direkt mit `RET` bei `0x1F8410`. Dadurch bleibt der bereits ausgeführte Helper-Aufruf der einzige `SetPrimaryPlayer`-Aufruf.

## Binäre Änderung

Der korrigierte IPS besitzt weiterhin:

```text
8  Try-9+10-Records
85 Try-11-Records
93 Records insgesamt
Helper-Größe: 1316 Bytes
```

Der neue Build unterscheidet sich vom ursprünglichen Try 11 ausschließlich hier:

```text
Helper Record 0xA7A708
Payload-Offset 168
alt: 0x1D
neu: 0x15
```

Alle späteren Helper-Einstiege bleiben an denselben Adressen. Try 9 und Try 10 bleiben byteidentisch. Der Ryujinx-IPS32-Bias `Runtime-Offset + 0x100` bleibt korrekt.

## Fix-1-Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
b3f221171e511aed368986361bee9c7aa358dfec6010bb836c0e16d5d183041a
```

## Nächster Test

```text
1. Spiel starten.
2. Level betreten.
3. Unterschiedliche Kongs als Regression.
4. DK + DK normaler 2P.
5. DK + DK Hard-Mode-2P.
```

Bis der Level-Einstieg mit Fix 1 bestätigt ist, bleibt der Duplicate-Kong-Patch experimentell.