# DKCTF – doppelte Kongs im Normalmodus und Hard Mode

Diese Datei trennt bestätigtes Laufzeitverhalten von statisch validierten Änderungen.

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

## Bestätigter Stand

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

### Hard-Mode-Abhängigkeit

Status: **Bug im Spiel bestätigt**

Beobachtet:

- Hard-Mode-`DK + DK` erzeugte P2 DK nur, wenn zuvor im normalen Kong-Select `DK + DK` eingestellt war;
- nach einer normalen Nicht-Duplikat-Auswahl fehlte P2 DK im Hard Mode.

### Andere doppelte Kongs

Status: **nicht implementiert im bestätigten Stand**

Der bisher bestätigte Helper war auf CharacterType `1` (`DK`) festgelegt. Daher funktionierten `Diddy + Diddy`, `Dixie + Dixie`, `Cranky + Cranky` und `Funky + Funky` nicht.

## Verworfener Hard-Mode-Fix

Artefakt:

```text
customkong_dkdk_normal_hardmode_fix
```

Status: **im Spiel fehlgeschlagen und verworfen**

Der Fehler war konkret:

- der Helper behandelte `x20` direkt als `GameState`;
- am Hard-Mode-Parser ist `x20` jedoch das Frontend-Objekt;
- der echte GameState liegt bei:

```text
GameState = [[x20 + 0x20] + 0x8]
```

Dadurch schrieb der Fix P1/P2 an die falsche Struktur.

## Neuer allgemeiner V2-Patch

Artefakt:

```text
customkong_all_duplicates_v2
```

IPS SHA-256:

```text
63fee0f425b3676d1b895412ffa52b2c7b267881ec88c921d103bebe56b28446
```

Status: **statisch validiert, In-Game-Test offen**

### 1. Gemeinsamer Duplicate-Trigger

Bereich:

```text
0xA7A734..0xA7A797
```

Der Trigger aktiviert den Duplicate-State nun bei jedem gleichen P1/P2-CharacterType.

Physische Trägerzuordnung:

```text
DK + DK         -> P2-Träger Diddy
Funky + Funky   -> P2-Träger Diddy
Diddy + Diddy   -> P2-Träger DK
Dixie + Dixie   -> P2-Träger DK
Cranky + Cranky -> P2-Träger DK
```

Damit bleibt die interne Paarung jeweils Primär-Kong + Buddy-Kong. Der sichtbare und logische P2 bleibt der ausgewählte Kong.

### 2. Korrigierter Hard-Mode-Parser

Bereich:

```text
0xA7A798..0xA7A7AF
```

Der Parser:

1. übernimmt den geparsten P2-Typ;
2. löst den echten GameState über `[[x20+0x20]+0x8]` auf;
3. schreibt die eigenen Hard-Mode-P1/P2-Werte nach `+0x2698/+0x269C`;
4. springt in den gemeinsamen Duplicate-Trigger;
5. gibt den physischen P2-Träger in `W22` zurück.

Damit hängt Hard Mode nicht mehr vom vorherigen normalen Kong-Select-State ab.

### 3. Allgemeine Replay-Factory

Bereiche:

```text
0xA7A808..0xA7A81F
0xA7A854
```

Die Factory lädt den ausgewählten logischen CharacterType aus dem Duplicate-State und vergleicht den erzeugten Actor dynamisch damit. Der frühere feste Vergleich gegen DK wurde entfernt.

## Unverändert

- bestätigter Normalmode-Hook bei `0x345898`;
- Transition-Hook bei `0x35236C`;
- Replay-Konstruktionsstufen;
- Player-Pointer- und Player-Index-Hooks;
- Tod-, Checkpoint-, Barrel- und Respawn-Hooks;
- modifizierte UIPak-Selectoren.

## Statische Validierung

Bestätigt:

- gültige IPS32-Struktur;
- weiterhin 24 sortierte, nicht überlappende Records;
- Helper-Größe unverändert: 968 Bytes;
- Hard-Mode-Call bei `0x3527EC` erreicht weiterhin `0xA7A798`;
- Normalmode-Call bei `0x345898` erreicht weiterhin `0xA7A734`;
- Transition-Call bei `0x35236C` erreicht weiterhin `0xA7A734`;
- alle fünf Duplicate-/Carrier-Zuordnungen statisch geprüft.

## Erforderlicher Test

1. Spiel vollständig neu starten.
2. Normalmodus `DK + DK` erneut prüfen.
3. Normalmodus mit `Diddy + Diddy`, `Dixie + Dixie`, `Cranky + Cranky` und `Funky + Funky` prüfen.
4. Normalen Selector auf eine Nicht-Duplikat-Auswahl stellen.
5. Hard Mode öffnen und alle fünf doppelten Kombinationen prüfen.
6. Für jede Kombination P1- und P2-Tod sowie beide Respawn-Barrel-Richtungen testen.
7. Level verlassen und anschließend 1P sowie eine normale Nicht-Duplikat-2P-Kombination prüfen.

## Statusübersicht

```text
Normalmodus DK + DK                         im Spiel bestätigt
Alter Hard-Mode-Abhängigkeitsbug            im Spiel bestätigt
Vorheriger Hard-Mode-Fix                    fehlgeschlagen, verworfen
Andere Duplicate-Kongs im alten Stand       nicht implementiert
V2: allgemeiner Duplicate-Trigger           statisch validiert
V2: korrekte Hard-Mode-GameState-Auflösung  statisch validiert
V2: dynamische Replay-Factory               statisch validiert
V2 gesamt                                    In-Game-Test offen
```
