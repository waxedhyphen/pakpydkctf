# DKCTF – doppelter DK im Normalmodus und Hard Mode

Diese Datei trennt bestätigtes Laufzeitverhalten von rein statisch validierten Änderungen.

## Ziel

Beide Spieler sollen DK unabhängig voneinander im normalen Zwei-Spieler-Modus und im Hard Mode auswählen können:

```text
P1 = DK
P2 = DK
```

Beide Figuren müssen getrennte Spieler mit unabhängiger Steuerung, Tod-, Respawn- und Checkpoint-Logik bleiben.

## Aktuelle UI- und ExeFS-Grundlage

Build ID:

```text
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

UI-Grundlage:

```text
UIPak SHA-256:
58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3
```

Die UI übergibt getrennte P1- und P2-Auswahlen. Die Duplicate-Implementierung erzeugt für P2 logisch einen DK, verwendet intern aber Diddy als physischen P2-Trägerslot.

## Bestätigter Laufzeitstand

### Normaler Zwei-Spieler-Modus

Status: **im Spiel bestätigt**

Der Live-Hook des Normalmodus liegt bei:

```text
0x345898
CProductionFrontEnd::UpdateCharacterTypes-Pfad
```

Er läuft nach dem nativen `Char_P2`-Store und vor dem P2-Character-Change-Event. Wenn beide gespeicherten CharacterTypes DK sind, aktiviert er den Duplicate-Replay-Zustand und ändert nur den internen P2-Träger auf Diddy.

Bestätigtes Ergebnis:

- normales Zwei-Spieler-`DK + DK` funktioniert;
- zwei sichtbare DK-Actors existieren;
- beide Spieler sind unabhängig steuerbar;
- dies ist derzeit die beste bestätigte Duplicate-Character-Grundlage.

### Hard Mode vor dem aktuellen Fix

Status: **Bug im Spiel bestätigt**

Beobachtet:

- `DK + DK` im Hard Mode erzeugte P2 DK nicht zuverlässig;
- P2 DK existierte nur, wenn zuvor im normalen Kong-Select `DK + DK` eingestellt war;
- nach einer normalen Nicht-Duplikat-Auswahl wie `DK + Diddy` fehlte P2 DK beim anschließenden Hard-Mode-Start mit `DK + DK`.

Diese Abhängigkeit zwischen den beiden Modi war unbeabsichtigt.

## Ursache der Hard-Mode-Abhängigkeit

Der Hard-Mode-P2-Parser läuft über:

```text
0x3527EC -> Helper 0xA7A798
```

Der bisherige Helper ersetzte den Hard-Mode-P2-Wert nur dann durch den physischen Diddy-Träger, wenn das globale Duplicate-State-Flag bereits aktiv war.

Dieses Flag wurde vom bestätigten Normalmode-Hook aktiviert. Der Hard-Mode-Argumentparser selbst aktivierte den Duplicate-Zustand nicht anhand seiner eigenen P1- und P2-Auswahl.

Dadurch entstand genau folgende Abhängigkeit:

```text
normaler Selector zuvor DK + DK
    -> Duplicate-Flag bereits aktiv
    -> Hard-Mode-P2-Replay existiert

normaler Selector zuvor nicht DK + DK
    -> Duplicate-Flag inaktiv
    -> Hard-Mode-Parser fordert keinen Replay-Actor an
    -> P2 DK fehlt
```

## Aktueller Fix

Artefakt:

```text
customkong_dkdk_normal_hardmode_fix
```

IPS SHA-256:

```text
bc42c7aa1a2b3575d15c90ae1ead617119c170205f1dd427dca65e1ba3d324d9
```

Der Fix ändert nur den vorhandenen Helper-Record. Die IPS enthält weiterhin 24 Records.

### Änderung am Hard-Mode-Parser

Der Helper bei `0xA7A798`:

1. schreibt die gewählte Hard-Mode-P1-Figur nach `GameState+0x2698`;
2. schreibt die gewählte Hard-Mode-P2-Figur nach `GameState+0x269C`;
3. richtet die gemeinsame Duplicate-Routine auf diesen GameState;
4. springt anschließend in dieselbe `DK + DK`-Aktivierungsroutine wie der funktionierende Normalmode-Pfad.

Für `DK + DK` setzt die gemeinsame Routine:

```text
logischer P1 = DK
logischer P2 = DK
physischer P2-Träger = Diddy
```

Der physische P2-Typ wird in `W22` an den ursprünglichen Hard-Mode-Parser zurückgegeben. Dieser schreibt anschließend wie bisher das Übergabefeld `GameState+0x26C0`.

### Gemeinsame Caller-Behandlung

Der gemeinsame Helper wird von drei Pfaden verwendet:

```text
normaler Live-UpdateCharacterTypes-Pfad
Hard-Mode-Argumentparser
vorhandener Transition-/Initializer-Pfad
```

Die Rückkehr unterscheidet diese Caller, ohne den im funktionierenden Normalmode benötigten ursprünglichen `W22`-Wert zu verändern.

Unverändert bleiben:

- Normalmode-Hook bei `0x345898`;
- Transition-Hook bei `0x35236C`;
- serialisierte Replay-Factory;
- Player-Pointer- und Player-Index-Hooks;
- Tod-, Checkpoint-, Barrel- und Respawn-Hooks;
- modifizierte UIPak-Selectoren.

## Validierungsstatus

Statisch validiert:

- gültige IPS32-Struktur;
- alle 24 Records sind sortiert und überlappen nicht;
- gegenüber der bestätigten Normalmode-Grundlage wurde ausschließlich der Helper-Bereich `0xA7A778..0xA7A7B3` verändert;
- `0x345898` springt weiterhin nach `0xA7A734`;
- `0x35236C` springt weiterhin nach `0xA7A734` und behält den ursprünglichen Tail-Pfad nach `0x1B7EC0`;
- `0x3527EC` ruft weiterhin `0xA7A798` auf;
- der Hard-Mode-Parser springt nun bei `0xA7A7A4` nach `0xA7A734`, ohne seine ursprüngliche Rücksprungadresse zu zerstören;
- der Normalmode-Wert in `W22` wird durch die neue Caller-Behandlung nicht überschrieben.

Die neue unabhängige Hard-Mode-Aktivierung ist **noch nicht im Spiel bestätigt**.

## Erforderlicher nächster Test

1. Spiel vollständig neu starten.
2. Im normalen Kong-Select absichtlich eine Nicht-Duplikat-Kombination wie `DK + Diddy` einstellen.
3. Hard Mode öffnen.
4. Dort `DK + DK` auswählen.
5. Prüfen, ob P2 DK existiert und unabhängig steuerbar ist.
6. P1- und P2-Tod testen.
7. Beide Respawn-Barrel-Richtungen testen.
8. Level verlassen und anschließend erneut normales Zwei-Spieler-`DK + DK` prüfen.

## Aktuelle Statusübersicht

```text
Normaler 2P-Modus DK + DK                 im Spiel bestätigt
Alte Hard-Mode-Abhängigkeit               im Spiel bestätigt
Ursache: Parser aktivierte State nicht    statisch bestätigt
Neue unabhängige Hard-Mode-Aktivierung    statisch validiert, Test offen
Andere doppelte Kong-Kombinationen        nicht implementiert
```