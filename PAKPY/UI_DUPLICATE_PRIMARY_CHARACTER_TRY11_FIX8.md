# Duplicate primary character – Try 11 Fix 8

Arbeitsstand: 2026-07-26

## Status

```text
FIX 7: LEVEL-LOAD-CRASH BESTÄTIGT
FIX 8: STRUKTURELL BESTÄTIGT
FIX 8: NOCH NICHT IM SPIEL BESTÄTIGT
```

## Fix-7-Crash

Der Fix-7-Hook bei `0x2A5358` sprang nach dem frühen `SLdrPlayer`-Clone zurück auf den verdrängten Stock-Call bei `0x2A535C`:

```text
CPlayerGOC::EntityLoaded
  -> CGameObjectComponent::EntityLoaded
  -> CGameObjectComponent::FindLinkedObjects
```

Der Crashlog zeigte:

```text
PC: CGameObjectComponent::FindLinkedObjects
LR: CGameObjectComponent::EntityLoaded + 0x38
Stack: CPlayerGOC::EntityLoaded + 0x30
Invalid memory access at 0x0
```

Der Loader-Helper hatte vor der Rückkehr Destruktor- und Copy-Konstruktor-Aufrufe ausgeführt. Dabei wurden die volatilen Argumentregister des verdrängten Stock-Aufrufs nicht erhalten.

Der Stock-Call bei `0x2A535C` benötigt:

```text
x0 = CPlayerGOC*
x1 = CStateManager*
x2 = CGameObjectComponent::SEntityLoadedInfo const*
```

Im Crashdump stand dagegen:

```text
x1 = 0x2B8
```

Das ist ein vom Loader-Copy-Pfad hinterlassener Wert und kein gültiger `CStateManager*`.

## Fix 8

Der ursprüngliche `x2`-Wert wird am Helper-Einstieg in einem callee-saved Register gesichert:

```asm
mov x28, x2
```

Direkt vor dem Rücksprung nach `0x2A535C` werden alle drei Argumente explizit rekonstruiert:

```asm
mov x0, x20
mov x1, x19
mov x2, x28
```

Dabei sind `x20` und `x19` bereits die vom Stock-Prolog gesetzten und über Funktionsaufrufe erhaltenen Werte für `CPlayerGOC*` und `CStateManager*`.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
256aff11e8687af442c63ea0b02ea86540390836244510c5870c7ef3aca5252b

Records insgesamt: 97
Try-11-Records: 89
Helper: 0xA7A708..0xA7B038
Helper-Größe: 2352 Bytes
Registry: 0x19E7220..0x19E7270
```

Alle acht bestätigten Try-9+10-Records sind byteidentisch enthalten. Der IPS32-Bias bleibt `Runtime-Offset + 0x100`.

## Validierung

Bestätigt:

- erwartete Bytes stimmen gegen die Try-9+10-Baseline;
- keine Überlappung mit Try 9 oder Try 10;
- alle acht Try-9+10-Records byteidentisch;
- Helper bleibt innerhalb der bestätigten Cave-Grenze;
- IPS32-Parse-/Write-Roundtrip bestanden;
- simulierte Anwendung auf `.text` und `.data` bestanden;
- `x0`, `x1` und `x2` werden vor dem verdrängten `EntityLoaded`-Call explizit wiederhergestellt.

## Laufzeitgrenze

Fix 8 behebt ausschließlich die aus dem Log nachgewiesene Fix-7-Crashursache. Ob der frühe Loader-Clone danach den zweiten identischen Kong vollständig spielbar und respawnfähig macht, ist noch nicht im Spiel bestätigt.