# Duplicate Kong V4 – Basis 36

Diese Datei trennt bestätigte Laufzeitergebnisse von der neuen, nur statisch geprüften Testfassung.

## Verwendete Grundlage

Die neue Fassung wurde direkt aus der vom Nutzer erneut bereitgestellten funktionierenden Basis aufgebaut:

```text
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000(36).ips
SHA-256: b5713898d20de69776cbdcbb382c77955d7c47fcdaca815d51184467a4963a83
Records: 24
```

Bestätigt an dieser Grundlage:

- normales Zwei-Spieler-`DK + DK` funktioniert;
- der Live-Hook liegt bei `0x345898` im `UpdateCharacterTypes`-Pfad;
- der bestehende Hard-Mode-`DK + DK`-Pfad bleibt Bestandteil der Basis.

## Verworfene V2/V3-Fassungen

Die allgemeinen V2- und V3-Patches sind fehlgeschlagen und dürfen nicht weiterverwendet werden.

Im Spiel beobachtet:

- `Diddy + Diddy` erzeugte zusätzlich einen DK;
- das Spiel konnte beim Verlassen des Levels abstürzen;
- ein 1P-Level konnte mit zwei DKs starten;
- eine normale Kombination aus Diddy und DK konnte fälschlich zwei DKs erzeugen.

## Konkrete Ursache des falschen Hard-Mode-Triggers

Im Hard-Mode-Parser liegen die beiden Auswahlen nicht im selben Zahlenraum vor:

```text
P1-Selectorindex: 0, 1, 2, 3, 4
P2-Runtimewert:   1, 2, 6, 7, 8
```

V3 verglich beide Werte direkt. Dadurch galt beispielsweise:

```text
P1 Diddy -> Index 1
P2 DK    -> Runtimewert 1
```

als Gleichheit, obwohl zwei verschiedene Kongs gewählt waren. Der Duplicate-DK-Pfad wurde deshalb bei `Diddy + DK` fälschlich aktiviert.

Die korrekte Normalisierung ist:

```text
P1 intern = P1-Index + 1
P2 intern = P2-Wert, wenn P2-Wert < 6
P2 intern = P2-Wert - 3, wenn P2-Wert >= 6
```

Damit liegen beide Seiten anschließend im internen Bereich `1..5`.

## V4-Testfassung

Artefakt:

```text
customkong_all_duplicates_v4_basis36
IPS SHA-256: b56fea4d42317a5c10a78c34920b8d566561da9cf85a524694db1c10abb0b428
Records: 24
```

Status: **statisch geprüft, nicht im Spiel bestätigt**.

### Änderungen gegenüber Basis 36

Nur zwei bestehende IPS-Records unterscheiden sich:

```text
0x3528A0 – Hard-Mode-Argumentparser
0xA7A808 – vorhandener Helper-/Replay-Bereich
```

Alle anderen Basis-Records bleiben bytegleich, insbesondere:

- Normalmode-Hook `0x345898`;
- Level-Unload-Hook;
- Player-Pointer- und Player-Index-Hooks;
- Tod-, Checkpoint-, Barrel- und Respawn-Hooks.

### Hard-Mode-Gate

Vor der Duplicate-Aktivierung wird der vorhandene P2-Aktivstatus geprüft. Ohne aktiven P2 wird kein Duplicate-State gesetzt.

Danach werden P1 und P2 in denselben internen CharacterType-Bereich normalisiert und erst anschließend verglichen.

### Technische Trägerslots

```text
DK + DK         -> Diddy-Träger
Funky + Funky   -> Diddy-Träger
Diddy + Diddy   -> Funky-Träger
Dixie + Dixie   -> Funky-Träger
Cranky + Cranky -> Funky-Träger
```

Der frühere DK-Träger für Buddy-Duplikate wurde entfernt, weil er im Spiel als zusätzlicher sichtbarer DK bestehen blieb.

### Replay-Factory

Die Actor-Typprüfung verwendet den gespeicherten logischen Duplicate-Typ statt eines festen DK-Vergleichs.

## Erforderliche Testreihenfolge

1. Spiel vollständig neu starten.
2. 1P-Level starten: Es darf nur ein Spieler existieren.
3. Normalen 2P-Level mit `Diddy + DK` starten: Es dürfen keine zwei DKs entstehen.
4. Normalmode `DK + DK` erneut prüfen.
5. `Diddy + Diddy` prüfen: kein zusätzlicher DK.
6. Level unmittelbar verlassen: kein Exit-Crash.
7. Erst danach Dixie, Cranky, Funky und Hard Mode testen.
