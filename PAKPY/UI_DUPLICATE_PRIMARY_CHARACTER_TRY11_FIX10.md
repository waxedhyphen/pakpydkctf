# Try 11 Fix 10 – multiplayer guard and Fix 9 rollback

Arbeitsstand: 2026-07-26

## Bestätigte Regressionen aus Fix 9

- Im 1P-Start wurde ein zweiter Player-Actor aktiviert.
- Im 2P-Start trat weiterhin ein Crash auf.

Damit ist `state+0x26A0 bit 1` allein kein ausreichender Laufzeitnachweis für einen echten Multiplayer-Start. Außerdem wird der persistente Alias aus Fix 9 verworfen.

## Basis

Fix 10 basiert vollständig auf dem letzten nicht-crashenden Fix-6-Helperblock. Die Fix-9-Änderungen an `try11_clear_entity_fix2` sind nicht enthalten.

## Neuer Multiplayer-Guard

Für die beiden Proxy-Hooks werden Wrapper im bisher freien Bereich hinter dem Fix-6-Helper eingefügt:

```text
AreaLoaded guard:   0xA7B120
Deactivate guard:   0xA7B150
Guard region end:   0xA7B194
Code-region bound:  0xA7B1B8
```

Beide Wrapper verwenden die vorhandene Stock-Funktion:

```text
CGameState::IsMultiplayerActive() = 0x33557C
```

### `0x4221E0` – AreaLoaded

- Multiplayer `false`: displaced `LDR X8,[X19]` ausführen und direkt bei `0x4221E4` in Stock fortsetzen.
- Multiplayer `true`: unveränderten Fix-6-AreaLoaded-Helper bei `0xA7AF44` aufrufen.

### `0x422C38` – DeactivatePlayerImpl

- Multiplayer `false`: ursprüngliche Argumente restaurieren, displaced `MOV X19,X2` ausführen und Stock bei `0x422C3C` fortsetzen.
- Multiplayer `true`: unveränderten Fix-6-Deaktivierungshelper bei `0xA7B088` aufrufen.

## Binärer Stand

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
816e34cd3416f63a3686feb4c8cc06f8b47ea17a1a398b10a7b7482a581461b2
```

Fix-6-zu-Fix-10-Diff:

- Hook `0x4221E0` auf den neuen AreaLoaded-Guard umgebogen;
- Hook `0x422C38` auf den neuen Deactivate-Guard umgebogen;
- neuer Wrapperblock bei `0xA7B120`;
- übriger Fix-6-Helperblock byteidentisch;
- alle bestätigten Try-9+10-Records byteidentisch.

## Status

Fix 10 ist eine Regression-Baseline, keine fertige dauerhafte Duplicate-Kong-Lösung.

Erwartete Laufzeittests:

1. 1P startet mit genau einem Spieler;
2. 2P crasht nicht mehr durch Fix 9;
3. Try-9+10-Verhalten bleibt erhalten;
4. das bekannte Fix-6-Verhalten nach der Cutscene darf noch bestehen: Carrier kann wieder zum Original-Kong zurückkehren.
