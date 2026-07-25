# Hard Mode P2 selector – Try 7 result

Arbeitsstand: 2026-07-25

## Ausgangslage

Try 6 ist im Spiel bestätigt:

- der zweite Hard-Mode-Slider bestimmt den tatsächlich gespawnten P2-Kong;
- der Levelübergang crasht nicht;
- die automatische DK/Default-Paarung überschreibt die Auswahl nicht mehr.

Bestätigter Nebeneffekt von Try 6:

```text
Nach der Rückkehr bleibt der im Hard Mode gewählte P2-Kong als aktueller P2 gesetzt.
```

## Idee von Try 7

`UpdateCharacterTypes()` besitzt bereits einen Reload für den normalen P2-Wert aus `Char_P2`. Try 7 änderte nur das Gate vor diesem vorhandenen Reload:

```text
0x345848
4D BF FF 97 40 05 00 36
->
00 3F 40 39 40 05 00 34
```

Der P2-Reload sollte damit über den persistenten Zwei-Spieler-Zustand bei `state+0x26AF` freigegeben werden.

## In-Game-Ergebnis: manueller Quit

```text
FEHLGESCHLAGEN
```

Getestet wurde:

1. normalen P2-Kong wählen;
2. im Hard Mode einen anderen P2-Kong wählen;
3. das Level über die manuelle Quit-/Level-verlassen-Funktion verlassen;
4. nach der Rückkehr blieb weiterhin der Hard-Mode-P2-Kong aktiv.

Nicht getestet:

```text
Rückkehr nach regulärem Abschluss des Levels.
```

## Schlussfolgerung

Der manuelle Quit-Pfad ruft den veränderten allgemeinen `UpdateCharacterTypes()`-Refresh nicht an der erforderlichen Stelle auf. Das P2-Gate bei `0x345848` repariert den manuellen Quit daher nicht.

Try 7 ist aus dem aktiven ExeFS-Profil entfernt. Das aktive Profil entspricht wieder dem im Spiel bestätigten Try-6-Selector.

## Nächster überprüfbarer Schritt

Der konkrete manuelle Quit-/Rückkehr-Callback muss bytegenau identifiziert werden. Erst dort wird der normale P2-Wert wiederhergestellt – entweder durch den originalen `UpdateCharacterTypes()`-Aufruf unmittelbar vor dem Quit-Übergang oder durch den vorhandenen `Char_P2`-Reload im tatsächlich ausgeführten Rückkehrpfad.

Bis dieser Pfad identifiziert ist, wird kein weiterer allgemeiner Refresh-Patch als Fix ausgegeben.
