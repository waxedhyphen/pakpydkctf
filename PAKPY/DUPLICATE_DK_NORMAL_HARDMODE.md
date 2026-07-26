# DKCTF – doppelte Kongs im Normalmodus und Hard Mode

Diese Datei trennt bestätigtes Laufzeitverhalten, bestätigte Fehler und noch unbestätigte Testpatches.

## Gesamtziel

P1 und P2 sollen unabhängig jeden Kong wählen können:

```text
DK, Funky, Diddy, Dixie, Cranky
```

Auch gleiche Kombinationen sollen funktionieren:

```text
DK + DK
Diddy + Diddy
Dixie + Dixie
Cranky + Cranky
Funky + Funky
```

Beide Figuren müssen getrennte Spieler mit unabhängiger Steuerung, Tod-, Respawn- und Checkpoint-Logik bleiben.

## Grundlage

Build ID:

```text
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

UIPak SHA-256:

```text
58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3
```

## Bestätigte funktionierende Basis

Basis-IPS SHA-256:

```text
b5713898d20de69776cbdcbb382c77955d7c47fcdaca815d51184467a4963a83
```

### Normalmodus `DK + DK`

Status: **im Spiel bestätigt**

Der Live-Hook liegt bei:

```text
0x345898
CProductionFrontEnd::UpdateCharacterTypes-Pfad
```

Bestätigt:

- zwei sichtbare DK-Actors;
- beide Spieler unabhängig steuerbar;
- bisher beste bestätigte Duplicate-Grundlage.

### Hard-Mode-Abhängigkeit der Basis

Status: **Bug im Spiel bestätigt**

- Hard-Mode-`DK + DK` erzeugt P2 DK nur, wenn zuvor im normalen Kong-Select `DK + DK` eingestellt war;
- nach einer normalen Nicht-Duplikat-Auswahl fehlt P2 DK im Hard Mode.

### Andere doppelte Kongs in der Basis

Status: **nicht implementiert**

Die Basis-Factory und der Trigger sind auf DK festgelegt.

## Verworfener V2-Patch

Artefakt:

```text
customkong_all_duplicates_v2
```

IPS SHA-256:

```text
63fee0f425b3676d1b895412ffa52b2c7b267881ec88c921d103bebe56b28446
```

Status: **im Spiel fehlgeschlagen und verworfen**

Bestätigte Fehler:

- `Diddy + Diddy` erzeugt zwar zwei Diddys, zusätzlich bleibt jedoch ein sichtbarer DK bestehen;
- beim Verlassen des Levels stürzt das Spiel ab;
- der Patch darf nicht weiter als Arbeitsgrundlage verwendet werden.

Der zusätzliche DK entstand, weil Buddy-Duplikate einen physischen DK-Träger erhielten. Dieser DK wurde als eigener Actor geladen und nicht durch den Replay-Actor ersetzt. Der Exit-Crash trat in genau diesem fehlerhaften Drei-Actor-Zustand auf.

## Neuer Testpatch V3 auf Basis (36)

Artefakt:

```text
customkong_all_duplicates_v3_basis36
```

IPS SHA-256:

```text
ea600fe9fdf30a5b5a91364aa6d27882b106073ff22888d8cfa533ea830b7afa
```

Status: **statisch validiert, In-Game-Test offen**

V3 wurde direkt aus der bestätigten Basis-IPS `b5713898...` erzeugt. V2 wurde nicht als Grundlage verwendet.

### Hard-Mode-Aktivierung

Der Call bei:

```text
0x3527EC
```

springt nun nach:

```text
0xA7A754
```

Dieser Pfad verwendet direkt die bereits geparsten Hard-Mode-Werte:

```text
P1 = W23
P2 = W0
```

Es wird kein geratener GameState-Pointer dereferenziert. Bei einer Nicht-Duplikat-Auswahl wird der Duplicate-State deaktiviert und der ursprüngliche P2-Wert zurückgegeben.

### Physische Trägerzuordnung

```text
DK + DK         -> Diddy
Funky + Funky   -> Diddy
Diddy + Diddy   -> Dixie
Dixie + Dixie   -> Cranky
Cranky + Cranky -> Diddy
```

Buddy-Duplikate verwenden damit keinen DK-Träger mehr. Das soll den in V2 bestätigten zusätzlichen DK vermeiden.

### Dynamische Replay-Factory

Geänderte Bereiche:

```text
0xA7A808..0xA7A81F
0xA7A854..0xA7A857
```

Die Factory liest den ausgewählten logischen CharacterType aus dem Duplicate-State und vergleicht den erzeugten Actor mit diesem Wert. Der feste DK-Vergleich wurde entfernt.

### Absichtlich unverändert gegenüber der funktionierenden Basis

- Normalmode-Hook bei `0x345898`;
- Transition-Hook bei `0x35236C`;
- State-Clear bei `0x352288`;
- Player-Pointer- und Player-Index-Hooks;
- Tod-, Checkpoint-, Barrel- und Respawn-Hooks;
- Level-Unload-Pfad;
- UIPak.

## Statische Validierung von V3

- gültige IPS32-Struktur;
- weiterhin 24 sortierte, nicht überlappende Records;
- nur der vorhandene Helper-Record und der bereits gepatchte Hard-Mode-Parser-Record unterscheiden sich von der Basis;
- Normalmode-Call `0x345898 -> 0xA7A734` bleibt erhalten;
- Transition-Call `0x35236C -> 0xA7A734` bleibt erhalten;
- Hard-Mode-Call `0x3527EC -> 0xA7A754`;
- Original-Tail `0x1B7EC0` bleibt erhalten;
- Level-Unload-Code wurde nicht verändert.

## Erforderlicher Test

1. Spiel vollständig neu starten.
2. Normalmodus `Diddy + Diddy` testen.
3. Prüfen, dass genau zwei Diddys und kein DK existieren.
4. Level normal verlassen und auf Exit-Crash prüfen.
5. Normalmodus `DK + DK` als Regressionstest prüfen.
6. Normalen Selector auf `DK + Diddy` stellen.
7. Hard Mode `DK + DK` testen und prüfen, ob P2 DK unabhängig vom vorherigen Normalmode-State existiert.
8. Danach Dixie, Cranky und Funky doppelt testen.
9. Für funktionierende Kombinationen P1-/P2-Tod und beide Revive-Richtungen prüfen.

## Statusübersicht

```text
Basis: Normalmodus DK + DK                   im Spiel bestätigt
Basis: Hard-Mode-Abhängigkeit                im Spiel bestätigt
Basis: andere doppelte Kongs                 nicht implementiert
V2: Diddy + Diddy plus zusätzlicher DK       im Spiel bestätigt
V2: Crash beim Level-Exit                    im Spiel bestätigt
V2 gesamt                                    verworfen
V3 auf Basis (36)                            statisch validiert, Test offen
```
