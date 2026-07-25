# Duplicate primary character – Testlog

Arbeitsstand: 2026-07-25

Ziel: P1 und P2 sollen denselben Kong gleichzeitig als zwei getrennte, steuerbare Spieler verwenden können. Das Problem betrifft normalen 2P und Hard-Mode-2P gleichermaßen.

## Arbeitsgrundlage

```text
ExeFS: exefs(13).zip / main
main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Der bestätigte kombinierte Try-9+10-Patch bleibt unverändert. Für diesen neuen Fehler wurde noch kein ExeFS-Record aktiviert.

## In-Game-Ausgangslage

Bestätigte Beobachtung:

```text
P1 und P2 mit verschiedenen Character-IDs: funktioniert
P1 und P2 mit derselben Character-ID: P2 ist tot / nicht als unabhängiger Spieler vorhanden
```

Das Verhalten tritt unabhängig vom Hard Mode auf und ist daher kein Try-9- oder Try-10-spezifischer Fehler.

## Ursache 1 – PlayerIndex wird aus der Character-ID abgeleitet

`CPlayer::GetPlayerIndex(CGameState const&)` besitzt keinen eigenen P1/P2-Slot im ausgewerteten Pfad. Die Routine liest ausschließlich `CPlayer+0x14`, also den CharacterType, und delegiert an `CGameState::GetPlayerIndexByCharacterType`:

```text
0x1FA6AC  LDR W8,[X0,#0x14]
0x1FA6B0  MOV X0,X1
0x1FA6B4  MOV W1,W8
0x1FA6B8  B   0x3376BC
```

`CGameState::GetPlayerIndexByCharacterType` prüft immer zuerst P1:

```text
0x3376BC  LDR W8,[X0,#0x2698]   ; P1 CharacterType
0x3376C0  CMP W8,W1
0x3376C4  B.NE 0x3376D0
0x3376C8  MOV W0,WZR            ; PlayerIndex 0
0x3376CC  RET

0x3376D0  LDR W8,[X0,#0x269C]   ; P2 CharacterType
0x3376D4  CMP W8,W1
0x3376D8  MOV W8,#1
0x3376DC  CNEG W0,W8,NE         ; PlayerIndex 1 oder -1
```

Folge bei identischen IDs:

```text
P1-Objekt -> CharacterType X -> Treffer bei state+0x2698 -> PlayerIndex 0
P2-Objekt -> CharacterType X -> Treffer bei state+0x2698 -> PlayerIndex 0
```

Damit benutzen beide Objekte P1s slotabhängige Lebens-, Inventar-, Controller- und Respawnzustände. Ein isolierter Patch nur an dieser Routine wäre trotzdem unvollständig, weil zusätzlich die Player-Pointer-Verwaltung kollidiert.

## Ursache 2 – genau ein PrimaryPlayer-Pointer pro CharacterType

`CStateManagerGameData::SetPrimaryPlayer(CPlayer&)` speichert den Player nicht nach P1/P2-Slot, sondern nach einer CharacterType-Mappingtabelle:

```text
CharacterType 1 / DK      -> Pointer-Slot 0
CharacterType 2 / Diddy   -> Pointer-Slot 1
CharacterType 6 / Dixie   -> Pointer-Slot 2
CharacterType 7 / Cranky  -> Pointer-Slot 3
CharacterType 8 / Funky   -> Pointer-Slot 4
```

Relevanter Store:

```text
0x2CE150  CPlayer::GetCharacterType
0x2CE16C  Mappingtabelle laden
0x2CE178  Pointer-Slot berechnen
0x2CE17C  STR X19,[X8,#8]
```

Es existiert in dieser Tabelle somit nur ein aktiver `CPlayer*` je Kong. Ein zweites Objekt mit derselben Character-ID würde denselben Pointer-Slot überschreiben.

Auch die vermeintlich allgemeinere API

```text
CStateManagerGameData::GetPrimaryPlayer(EPrimaryPlayer,...)
CStateManagerGameData::PrimaryPlayer(EPrimaryPlayer,...)
```

indiziert dieselbe fünf Einträge große Character-Pointer-Tabelle. Sie ist keine unabhängige P1/P2-Slot-Tabelle.

## Ursache 3 – Character-Wechsel und Spawn holen das Zielobjekt nach CharacterType

`NPlayerUtils::SpawnOtherPlayer` ruft für den gewünschten Ziel-Kong auf:

```text
0x27C96C  MOV W1,W23
0x27C974  PrimaryPlayerByCharacterType
```

Bei einer Duplikatauswahl liefert dieser Lookup das bereits von P1 verwendete Objekt. P2 erhält daher kein zweites Zielobjekt.

Später schreibt die Routine zwar den gewünschten CharacterType nach `state+0x2698/0x269C`, arbeitet aber weiterhin mit dem einen gefundenen `CPlayer*`.

`NPlayerUtils::CanSpawnPlayer` verwendet denselben CharacterType-Lookup bei `0x27C6D0` und bestimmt anschließend den PlayerIndex des gefundenen Objekts über die oben beschriebene kollidierende Character-ID-Routine.

## Ursache 4 – Checkpoint-Respawn adressiert ebenfalls nur nach CharacterType

`CCheckpointGOC::SpawnPlayer` holt beide Spieler getrennt aus den GameState-Feldern, löst sie aber jeweils über dieselbe CharacterType-Tabelle auf:

```text
P1:
0x3BD0DC  LDR W1,[X22,#0x2698]
0x3BD0E8  PrimaryPlayerByCharacterType

P2:
0x3BD180  LDR W1,[X22,#0x269C]
0x3BD18C  PrimaryPlayerByCharacterType
```

Sind beide IDs gleich, zeigen beide Resultate auf dasselbe `CPlayer`-Objekt. Der Checkpointpfad resetet/spawnt damit denselben Actor zweimal, statt zwei unabhängige Spieler wiederherzustellen.

## Strukturelle Schlussfolgerung

Das Problem ist kein einzelner Duplikat-Guard und kein reines HP-Problem.

Das Stock-System verwendet die Character-ID gleichzeitig als:

- Auswahlwert;
- PlayerIndex-Quelle;
- Schlüssel der aktiven Player-Pointer-Tabelle;
- Schlüssel beim Character-Wechsel;
- Schlüssel beim Checkpoint-/Respawn-Lookup.

Darum reicht keiner der folgenden Blindpatches:

```text
GetPlayerIndexByCharacterType P1-first-Vergleich ändern
CanSpawnPlayer immer true liefern lassen
PrimaryPlayerByCharacterType einfach P2 zurückgeben
P2 erneut HP geben
```

Jeder dieser Einzelpatches ließe mindestens Pointer-, Spawn-, Checkpoint- oder Controller-Kollisionen bestehen.

## Erforderliche Implementierungsrichtung

Für echte Duplikate muss Identität von Darstellung/CharacterType getrennt werden. Zwei grundsätzlich mögliche Wege bleiben:

### Weg A – echter zweiter Player-Actor desselben CharacterType

- zweites `CPlayerGOC`/`CPlayer`-Objekt erzeugen oder klonen;
- unabhängigen P1/P2-Slot am Objekt führen;
- PrimaryPlayer-Registry auf zwei Slot-Pointer erweitern;
- slotabhängige Kern-Lookups in Spawn, Wechsel, Checkpoint, Tod und Controller umstellen;
- CharacterType-Lookups für Systeme erhalten, die bewusst irgendeinen Actor dieses Typs suchen.

### Weg B – vorhandenen anderen Actor als P2-Carrier verwenden

- P2 intern auf einem anderen, eindeutig registrierten Kong-Actor belassen;
- Modell, Animationen, Module und Fähigkeiten auf den ausgewählten Duplikat-Kong aliasen;
- logische P2-Slot-Identität vom dargestellten CharacterType trennen.

Weg B vermeidet einen Runtime-Objektclone, benötigt aber eine vollständige Alias-Schicht für Fähigkeiten und Ressourcen. Ein reiner Modeltausch wäre kein echter gleicher spielbarer Kong.

## Status

### Strukturell bestätigt

- identische Character-IDs liefern für beide Objekte PlayerIndex 0;
- die aktive PrimaryPlayer-Tabelle besitzt nur einen Pointer pro CharacterType;
- `SpawnOtherPlayer` wählt das Zielobjekt nach CharacterType;
- `CCheckpointGOC::SpawnPlayer` löst P1 und P2 nach CharacterType auf;
- P2s Totzustand ist ein Symptom kollidierender Player-Identität und nicht nur fehlender HP;
- Try 9 und Try 10 sind nicht die Ursache und bleiben unverändert.

### Noch nicht gepatcht

Es existiert noch kein sicherer Try-11-IPS-Record. Vor einem Patch muss feststehen, ob ein vorhandenes zweites Actor-Objekt als vollständiger Carrier umgebaut werden kann oder ob ein echter Clone samt slotbasierter Registry erforderlich ist.
