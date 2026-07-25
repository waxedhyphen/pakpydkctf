# Hard Mode P2 – Try 9

Arbeitsstand: 2026-07-25

## Ergebnis von Try 8

```text
FEHLGESCHLAGEN FÜR MANUELLEN LEVEL-QUIT
```

Auch der ungefilterte `Char_P2`-Reload in `UpdateCharacterTypes()` stellte nach einem manuellen Level-Quit den normalen P2-Kong nicht wieder her. Damit sind sowohl Try 7 als auch Try 8 als Rückkehr-Fix ausgeschlossen. Der manuelle Quit führt den dafür gepatchten Refresh-Pfad nicht so aus, dass `state+0x269C` wiederhergestellt wird.

## Try 9 – P2 innerhalb der Hard-Mode-Initialisierung setzen

Try 9 versucht keinen nachträglichen Quit- oder Refresh-Fix mehr.

Der bestätigte Parser liest weiterhin den dritten `initLevelTransition`-Parameter und mappt den Slider:

```text
0 -> DK     -> interne ID 1
1 -> Diddy  -> interne ID 2
2 -> Dixie  -> interne ID 6
3 -> Cranky -> interne ID 7
4 -> Funky  -> interne ID 8
```

Der Unterschied zu Try 6 bis Try 8:

```text
bisher:
Callback -> ausgewählte ID direkt nach state+0x269C
0x1E700C -> NOP

Try 9:
Callback -> ausgewählte ID temporär nach state+0x26C0
Hard-Mode-Initialisierung -> ID aus state+0x26C0 laden
0x1E700C -> originaler STR W8,[X19,#0x269C]
```

Dadurch wird P2 an derselben Stelle und im selben Initialisierungsablauf geschrieben, in dem unmittelbar davor P1 nach `state+0x2698` geschrieben wird. Der UI-Callback verändert den aktuellen persistenten P2-Zustand nicht mehr vorzeitig.

## ExeFS-Records

```text
0x1E6FEC   P2-Hard-Mode-Zustand erhalten
0x1E7000   P2-ID aus state+0x26C0 laden
0x1E7004   automatische DK-Erhöhung entfernen
0x1E7018   P2-Slot-Bit erhalten
0x3526EC   Parser-Branch
0x3527A0   164-Byte-Parser; Store nach +0x26C0
0x352B18   temporären Wert vor Initialisierung nicht löschen
```

Wichtig:

```text
0x1E700C bleibt vollständig stock.
```

## Status

```text
Strukturell validiert.
Noch nicht im Spiel bestätigt.
```

Zu prüfen:

1. ausgewählter Hard-Mode-P2 wird weiterhin korrekt gespawnt;
2. kein Crash und keine Regression der Join-Animation;
3. nach manuellem Level-Quit ist wieder der normale P2-Kong aktiv;
4. regulären Levelabschluss getrennt prüfen.
