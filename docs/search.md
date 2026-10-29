# Volltextsuche — Meilenstein 3

`POST /api/search` prüft den gesamten ausgewählten Text der **neuesten Revision
jedes Dokuments**. Eine neuere unverarbeitete Revision fällt nicht auf einen
älteren Suchindex zurück. Dokumente ohne Revision sind ebenfalls unverifizierbar.

```json
{
  "query": "The receiving party shall not disclose confidential information",
  "mode": "normalized",
  "relation": "lacks",
  "scope": "latest",
  "limit": 25,
  "offset": 0,
  "unverifiable_limit": 25,
  "unverifiable_offset": 0
}
```

## Bedeutung der Ergebnisse

| Status | Aussage |
|---|---|
| `found` | Die Passage kommt im ausgewählten Text vor. Qualitätswarnungen bleiben erhalten, auch bei einem positiven Treffer. |
| `not_found_in_processed_text` | Die Passage wurde im ganzen ausgewählten Text nicht gefunden; Abdeckung ist vollständig und Qualität hat keine bekannte Auffälligkeit. |
| `unverifiable` | Es fehlt ein ausgewählter Text, die Abdeckung/Qualität genügt nicht oder die gespeicherten Normalisierungsregeln werden nicht unterstützt. |

`contains` liefert positive Ergebnisse in `results`, `lacks` negative Ergebnisse.
`unverifiable` wird bei beiden Relationen separat zurückgegeben. Die unabhängigen
Offsets/Limits beider Gruppen beeinflussen nie die Klassifikation oder die globalen
Zählungen in `summary`. Ein leerer erster Ergebnisbereich beweist daher nicht,
dass alle Dokumente zuverlässig geprüft wurden.

Eine explizite manuelle Prüfvormerkung des Quellartefakts oder eines späteren Laufs
mit derselben Quelle verhindert negative Ergebnisse auch dann, wenn noch ein
älterer, unauffälliger Text ausgewählt ist. Fehlschläge und laufende Neuverarbeitung
werden neben dem tatsächlich ausgewählten Lauf angezeigt. Ein weiterhin gültiger
alter Index darf verwendet werden, seine Herkunft bleibt sichtbar.

## Literalität und Normalisierung

- `exact`: unveränderte Zeichenfolge in `revision_texts.plain_text`, inklusive
  Groß-/Kleinschreibung und Zeilenumbrüchen. Zwischen Seiten steht `\n\f\n`.
- `normalized`: dieselbe versionierte NFC-/Whitespace-/Casefold-Funktion wie bei
  der Verarbeitung. Zahlen, Negationen, Satzzeichen und Bindestriche bleiben
  erhalten. Leerraum zwischen nichtleeren Seiten wird zu einem Leerzeichen.
- PostgreSQL `strpos` prüft den vollständigen Text mit gebundenen Parametern.
  Prozentzeichen, Unterstriche, Backslashes und SQL-artige Zeichenfolgen sind
  gewöhnlicher Suchtext. Keine Top-k- oder Segmentbegrenzung entscheidet Abwesenheit.
- Eine nicht unterstützte Normalisierungsversion liefert im normalisierten Modus
  `unverifiable`; rohe exakte Suche bleibt unabhängig davon möglich.

Der Eingabetext darf 1–2000 Zeichen enthalten und muss mindestens ein Nicht-
Leerraumzeichen besitzen. Nullzeichen, ungültiges Unicode, unbekannte Felder,
Fuzzy-Modus, `scope: all` und ungültige Pagination werden mit 422 abgelehnt.
Validierungsantworten nennen Feld und Grund, ohne Eingabetext zurückzuspiegeln.

## Fundstellen und Herkunft

Pro Dokument wird die erste Fundstelle der neuesten Revision zurückgegeben
(`match_policy: first_occurrence_per_revision`). `total` zählt Dokumente, keine
Vorkommen. Positive Ergebnisse enthalten passenden Text, Ausschnitt, Original-
Artefakt-ID, ausgewählten Lauf, Engine-Versionen, Qualität und verfügbare Seiten.
Negative/unverifizierbare Ergebnisse erfinden keine Fundstelle oder Offsets.

Alle Offsets sind nullbasiert, das Ende exklusiv, gezählt in Unicode-Codepoints.
`offset_basis` nennt `plain_text` oder `normalized_text`; `snippet_start_offset`
bezieht sich auf denselben String. JavaScript-Hervorhebung berücksichtigt dabei
Codepoints statt UTF-16-Codeeinheiten. `page_numbers` und Anfangs-/Endseite können
mehrere Seiten umfassen. Rohtextseiten werden aus Seitenlängen und den exakt
verwendeten Trennern zugeordnet; normalisierte Seiten nutzen gespeicherte Offsets.
Fehlt eine zuverlässige Zuordnung, wird keine Seitennummer geraten. `score` ist null.

Die Oberfläche öffnet auf Wunsch den Seitentext des ausgewählten Laufs. Wurde der
Text inzwischen neu verarbeitet, wird eine erneute Suche angefordert, statt die
Fundstelle dem neuen Textbestand zuzuordnen. Ergebnisse bleiben bis zur nächsten
Suche eine ausdrücklich beschriftete Momentaufnahme.

## Konsistenz und Grenzen

Zählungen, Ausschnitte, Herkunft und Seitenpositionen kommen aus einer gemeinsamen
Read-only-Transaktion mit `REPEATABLE READ`. Ein Integrationstest veröffentlicht
einen neuen Textbestand zwischen den Suchabfragen und prüft die alte, konsistente
Antwort. Gleichzeitige Worker-Verarbeitung kann deshalb keine Seiten eines anderen
Laufs in die Antwort mischen.

Der Prototyp scannt den ausgewählten Volltext in PostgreSQL und lädt Metadaten für
den gesamten Suchumfang, Ausschnitte und Seitenmetadaten nur für die ausgegebenen
positiven Treffer. Für große Bestände wären Abfragepläne und serverseitige
Aggregation/Pagination zu optimieren. Dieser Meilenstein benötigt keine neue
Tabelle oder Migration. Fuzzy- und semantische Suche sind nicht implementiert.

Die Aussage bleibt auf den extrahierten Text beschränkt, nicht auf juristische
Vollständigkeit oder fehlerfreie OCR. Bereits mit einer fehlerhaften älteren
Extraktion verarbeitete Quellen müssen neu verarbeitet werden; eine Suche startet
keine neue Extraktion und ersetzt keinen manuell zu prüfenden Vertrag.
