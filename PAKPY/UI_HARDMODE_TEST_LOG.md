# DKCTF Hard Mode UI – Testprotokoll

Diese Datei trennt reine Viewer-/Strukturtests von späteren In-Game-Bestätigungen.

## UI-Test 1 – zweite Selector-Grafik

Referenz:

```text
UIPak(10).pak
MasterShell -> MapHUD.swf
Sprite 80 = map.menu_hardmode
Character 72 = vorhandener Kong-Selector
```

Eingefügte Timeline-Instanz:

```text
Quelle:       Sprite 80 / chooseKong / Character 72
Ziel:         Sprite 80
Tiefe:        22
Instanzname:  keiner
Verschiebung: X 0 px / Y +66 px
```

## Ergebnis

Status: **in der PAKPY-Vorschau sichtbar bestätigt**

Beobachtet:

- Die zweite vollständige Selector-Zeile wird unterhalb der vorhandenen Zeile gerendert.
- Die Kopie zeigt `P1` und `Two Lines!`.
- Diese Texte sind keine funktionierende P2-Beschriftung, sondern unveränderte Designer-/Standardtexte der noch uninitialisierten Kopie.
- Die Kopie besitzt absichtlich noch keinen Instanznamen und wird deshalb von `map.menu_hardmode` nicht als eigenes Feld initialisiert.

Damit ist ausschließlich bestätigt:

```text
Character 72 kann ein zweites Mal in Sprite 80 dargestellt werden.
```

Noch nicht bestätigt:

- eigener AVM2-Trait `chooseKongP2`;
- richtige P2-Beschriftung;
- eigener Auswahlzustand;
- getrennte Controller-Eingabe;
- Übernahme der beiden gewählten Figuren beim Levelstart;
- Darstellung im Spiel.

## Nächster isolierter Schritt

1. universell einen vorhandenen AVM2-Slot-Trait klonen;
2. in `map.menu_hardmode` den Slot `chooseKong : utilities.BaseToggle` als `chooseKongP2 : utilities.BaseToggle` ergänzen;
3. erst danach die zweite Timeline-Instanz kontrolliert `chooseKongP2` nennen;
4. zunächst nur prüfen, ob der Film mit beiden benannten Instanzen fehlerfrei lädt.
