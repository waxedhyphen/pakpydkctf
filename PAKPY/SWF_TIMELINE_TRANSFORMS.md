# PAKPY SWF Timeline – Verschiebung und unbenannte Kopien

Der universelle SWF-Timeline-Editor kann Timeline-Instanzen jetzt zusätzlich relativ verschieben und für reine Sichttests ohne Instanznamen einsetzen.

## Zweck

Bisher konnte eine Instanz nur:

- mit ihrer Quellmatrix oder
- an der exakten Matrix einer vorhandenen Zielinstanz

kopiert werden.

Für neue UI-Anordnungen fehlte eine allgemeine relative X/Y-Verschiebung. Außerdem verlangte das Werkzeug immer einen Instanznamen, obwohl ein neuer Name ohne passenden AVM2-Trait bei versiegelten Timeline-Klassen unsicher sein kann.

## Neue allgemeine Felder

```text
X-Verschiebung in Pixeln
Y-Verschiebung in Pixeln
Ohne Instanznamen einfügen
```

Intern werden Pixel exakt in SWF-Twips umgerechnet:

```text
1 Pixel = 20 Twips
```

Die vorhandenen Scale- und Rotate-Werte der MATRIX bleiben unverändert. Nur die Translation wird addiert.

## Unbenannte Kopie

Eine unbenannte Kopie erzeugt einen `PlaceObject2`-Eintrag ohne `HasName`-Flag.

Sie eignet sich für:

- reine Sichttests,
- Positionsprüfung,
- Prüfung von Tiefe und Überlagerung,
- Fälle, in denen der spätere AVM2-Trait noch nicht existiert.

Eine unbenannte Kopie kann nicht über `replace_existing` ersetzt werden, weil es keinen eindeutigen Namen als Suchanker gibt. Die Zieltiefe muss frei sein.

## Sicherheitsprüfungen

Das Werkzeug prüft weiterhin:

- Quell-Sprite und Quellinstanz existieren eindeutig,
- Character-ID ist vorhanden,
- Ziel-Sprite existiert,
- Zieltiefe ist gültig und frei,
- benannte Zielinstanzen sind eindeutig,
- die neu kodierte MATRIX lässt sich wieder lesen,
- die eingefügte Instanz besitzt nach dem Neuaufbau dieselbe Character-ID und Zieltiefe,
- FWS/CWS-Signatur bleibt erhalten,
- der Ausgangsfilm und die PAK bleiben bis zur ausdrücklichen Speicherung unverändert.

## Implementierung

```text
PAKPY/ui_browser_timeline_transform_patch.py
PAKPY/test_ui_browser_timeline_transform_patch.py
```

Die Erweiterung enthält keine spiel- oder projektspezifischen Sprite-IDs, Tiefen, Matrizen oder Instanznamen.
