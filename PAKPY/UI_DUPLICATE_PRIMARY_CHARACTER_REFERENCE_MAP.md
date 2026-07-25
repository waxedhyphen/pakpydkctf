# Duplicate primary character – vollständiger Kong-ID-Referenzkatalog

Arbeitsstand: 2026-07-25

## Zweck und Patch-Vertrag

Dieser Katalog ist die statische Grundlage für einen späteren ExeFS-only Slotmechanismus. Er aktiviert **keinen** neuen Patch. Der bestätigte Try-9+10-Stand bleibt unverändert.

```text
Build-ID: F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
main SHA-256: 018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21
aktiver korrigierter Try-9+10-IPS SHA-256: b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f
UI/UIPak.pak SHA-256: 58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3
```

Unverhandelbare Belegung:

| Offset | Besitzer |
|---:|---|
| `0x1E6FEC` | Try 9 |
| `0x1E7000` | Try 9 |
| `0x1E7004` | Try 9 |
| `0x1E7018` | Try 9 |
| `0x1E7520` | Try 10 |
| `0x3526EC` | Try 9 |
| `0x3527A0` | Try 9 parser + Try 10 helper tail |
| `0x352B18` | Try 9 |

- Try 7 und Try 8 bleiben ausgeschlossen.
- `0x1E700C` bleibt der originale P2-Store.
- `0x3527A0..0x352840` darf nicht als freie Code-Cave behandelt werden.
- Ein späterer IPS32-Export muss den von Ryujinx erwarteten `+0x100`-Record-Bias verwenden.

## Erfassungsmethode und Grenzen

- vollständig erfasst: direkte AArch64-`BL`-Calls und direkte `B`-Tailcalls auf die unten aufgeführten Kernfunktionen;
- vollständig erfasst: direkte unsigned-immediate Zugriffe auf `CGameState+0x2698` und `CGameState+0x269C`;
- vollständig erfasst: exportierte Textsymbole, deren Signatur `CharacterType`, `charType`, `character_type` oder `PrimaryPlayer` enthält;
- nicht automatisch einem Ziel zuordenbar: indirekte `BLR`-Calls über vtables/Funktionspointer;
- `CPlayer+0x14` wird nicht blind global katalogisiert, weil derselbe Feldoffset in tausenden anderen Klassen vorkommt. Exakte CharacterType-Leser werden über `CPlayer::GetCharacterType()` und bestätigte CPlayer-Funktionen erfasst.

## Kernbefund

Das Kong-ID-System besteht nicht aus einem einzelnen Guard. Vier Identitätsräume sind gekoppelt:

1. `CGameState+0x2698/+0x269C` speichern die gewählten P1/P2-CharacterTypes;
2. `CPlayer+0x14` speichert den CharacterType des Actors;
3. `GetPlayerIndexByCharacterType()` leitet P1/P2 aus dem CharacterType ab;
4. `CStateManagerGameData` registriert nur einen Playerpointer je CharacterType.

Ein ExeFS-only Slotmechanismus muss deshalb Player-Slot und CharacterType trennen, ohne den CharacterType für Modell, Animationen und Fähigkeiten zu verändern.

## Exakte Kernimplementierungen

### `CPlayer::GetPlayerIndex`

```asm
0x1FA6AC  LDR W8,[X0,#0x14]
0x1FA6B0  MOV X0,X1
0x1FA6B4  MOV W1,W8
0x1FA6B8  B   0x3376BC
```

Das Objekt besitzt in diesem Pfad keinen unabhängigen Slotwert. `CPlayer+0x14` ist der einzige Identitätseingang.

### `CGameState::GetPlayerIndexByCharacterType`

```asm
0x3376BC  LDR W8,[X0,#0x2698]
0x3376C0  CMP W8,W1
0x3376C4  B.NE 0x3376D0
0x3376C8  MOV W0,WZR
0x3376CC  RET
0x3376D0  LDR W8,[X0,#0x269C]
0x3376D4  CMP W8,W1
0x3376D8  MOV W8,#1
0x3376DC  CNEG W0,W8,NE
0x3376E0  RET
```

Bei gleicher P1/P2-ID ist der erste Vergleich immer erfolgreich. Ein P2-Actor desselben Typs kann über diese API niemals Index 1 erhalten.

### CharacterType-zu-Pointer-Slot-Tabelle

Die Registry-Funktionen verwenden bei `0x151E340` folgende `int32`-Tabelle:

| CharacterType | Kong | Pointerindex |
|---:|---|---:|
| `1` | DK | `0` |
| `2` | Diddy | `1` |
| `3` | nicht primär | `-1` |
| `4` | nicht primär | `-1` |
| `5` | nicht primär | `-1` |
| `6` | Dixie | `2` |
| `7` | Cranky | `3` |
| `8` | Funky | `4` |

`SetPrimaryPlayer`, `ClearPrimaryPlayer`, `GetPrimaryPlayerByCharacterType` und `PrimaryPlayerByCharacterType` benutzen dieselbe Tabelle. Daher existiert stock exakt ein Registry-Pointer pro primärem Kongtyp.

### Slot-API ist derzeit ebenfalls Character-Pointer-Tabelle

`GetPrimaryPlayer(EPrimaryPlayer,flags)` und `PrimaryPlayer(EPrimaryPlayer,flags)` berechnen direkt `base + EPrimaryPlayer*8 + 8`. Die gültigen Werte sind `0..4`, also die fünf Primary-Kong-Slots, nicht ausschließlich P1/P2. Der Typname `EPrimaryPlayer` ist hier eine Kongklassifikation und kein unabhängiger lokaler Multiplayer-Slot.

## Referenzsummen

| Kernfunktion/Feld | direkte Referenzen |
|---|---:|
| `CPlayer.GetCharacterType` | 282 |
| `CPlayer.GetPlayerIndex` | 17 |
| `CGameState.GetPlayerIndexByCharacterType` | 19 |
| `GameData.GetPrimaryPlayer` | 16 |
| `GameData.PrimaryPlayer` | 19 |
| `GameData.GetPrimaryPlayerByCharacterType` | 138 |
| `GameData.PrimaryPlayerByCharacterType` | 44 |
| `GameData.SetPrimaryPlayer` | 1 |
| `GameData.ClearPrimaryPlayer` | 1 |
| `NPlayerState.character_type_in_bit_field` | 17 |
| `NPlayerState.is_a_primary_kong` | 1 |
| `NPlayerState.charType_for_primary_player` | 3 |
| `NPlayerState.primary_player_for_charType` | 1 |
| `NPlayerUtils.CanSpawnPlayer` | 5 |
| `NPlayerUtils.SpawnOtherPlayer` | 1 |
| `CCheckpointGOC.SpawnPlayer` | 1 |
| `CCheckpointGOC.FinishRespawn` | 0 |
| `CPlayer.EntityLoaded` | 0 |
| `CPlayer.AcceptScriptMsg` | 0 |
| `CGameState+0x2698` | 145 |
| `CGameState+0x269C` | 106 |
| Character/PrimaryPlayer-Symbole | 82 |

## Kritische Umbaugruppen

### A. Actor-Registrierung

- `CPlayer::EntityLoaded` tailcallt `SetPrimaryPlayer`;
- `CPlayer::AcceptScriptMsg` ruft beim Entfernen `ClearPrimaryPlayer(CharacterType)` auf;
- `SetPrimaryPlayer` und `ClearPrimaryPlayer` indizieren dieselbe CharacterType-Mappingtabelle.

Diese Gruppe muss eine zusätzliche P1/P2-Slotregistry erhalten. Die bestehende CharacterType-Registry sollte für bewusst typbasierte Systeme erhalten bleiben.

### B. PlayerIndex

- `CPlayer::GetPlayerIndex` liest `CPlayer+0x14` und tailcallt `GetPlayerIndexByCharacterType`;
- `GetPlayerIndexByCharacterType` prüft `state+0x2698` vor `state+0x269C`;
- zusätzlich existieren direkte Calls auf `GetPlayerIndexByCharacterType`, die einen bloßen Patch von `CPlayer::GetPlayerIndex` umgehen würden.

Ein sicherer Slotmechanismus muss beide Einstiegspunkte und deren direkte Verbraucher klassifizieren.

### C. CharacterType-Player-Lookups

Die const- und mutable-Varianten von `PrimaryPlayerByCharacterType` besitzen zusammen 182 direkte Call-/Tailcall-Stellen. Ein globales Umschreiben dieser APIs auf P1/P2 wäre falsch, weil zahlreiche Gameplaysysteme bewusst einen Actor eines bestimmten Kongtyps suchen.

Benötigt wird stattdessen eine neue slotbasierte API/Helper-Cave und eine selektive Umstellung nur der Stellen, die logisch P1 oder P2 meinen.

### D. Direkte GameState-Feldzugriffe

`state+0x2698` besitzt 145 direkte Zugriffe; `state+0x269C` besitzt 106. Diese Zugriffe dürfen nicht pauschal ersetzt werden: viele brauchen weiterhin die echte Kong-ID, während Spawn-/Registry-/Checkpoint-Pfade den Slot benötigen.

## Vollständige Referenzanhänge

Alle Listen liegen einzeln unter `PAKPY/reference_maps/`, damit sie durchsucht, verglichen und später pro Aufrufer klassifiziert werden können:

- `duplicate_kong_get_character_type_xrefs_01.md`
- `duplicate_kong_get_character_type_xrefs_02.md`
- `duplicate_kong_get_character_type_xrefs_03.md`
- `duplicate_kong_identity_xrefs.md`
- `duplicate_kong_character_lookup_xrefs_const.md`
- `duplicate_kong_character_lookup_xrefs_mutable_and_lifecycle.md`
- `duplicate_kong_state_2698_refs.md`
- `duplicate_kong_state_269c_refs.md`
- `duplicate_kong_character_symbols.md`

Die Anhänge enthalten die vollständigen direkten Referenzen. Indirekte `BLR`-/Vtable-Aufrufe sind methodisch getrennt und werden erst nach Auflösung der jeweiligen Tabelle ergänzt; sie werden nicht als direkte Xrefs ausgegeben.

## Patchentscheidung

Noch kein Try-11-Record. Vor einem Patch werden die 182 CharacterType-Lookups in zwei Klassen aufgeteilt:

- **typbasiert behalten:** Gameplay, Fähigkeiten, Animationen, Rider-/Mount-Logik, Effekte;
- **slotbasiert umstellen:** Actor-Registry, PlayerIndex, Spawnziel, Checkpoint/Respawn, Controller-/HP-Zuordnung und andere eindeutig P1/P2-semantische Pfade.

Erst danach kann ein neuer Helper-/Registry-Entwurf gegen alle Referenzgruppen geprüft werden, ohne Try 9, Try 10 oder die bestehende UI-Auswahl zu überschreiben.
