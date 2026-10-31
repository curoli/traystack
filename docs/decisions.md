# Entscheidungen

- **Abgeschlossener lokaler Core:** Meilenstein 4 ergänzt eine ausführbare
  Demo-Prüfung und einen Präsentations-/Einführungsplan. Azure, SharePoint,
  Handschriftevaluation und Nutzerpilot bleiben ausgewiesene Vorschläge.
  Der [Produktionsentwurf](production.md) vergleicht Microsoft-Alternativen;
  weder ein Suchcluster noch ein Cloud-/LLM-Dienst wird dafür zur Laufzeit eingeführt.
- **Schmaler erster Durchstich:** Ein kombinierter Upload legt Dokument, Revision 1
  und Original an. Weitere Revisionen und Repräsentationen bleiben im Datenmodell
  möglich; ihre Schreib-APIs und komfortable Verwaltung folgen später.
- **PostgreSQL von Anfang an:** JSONB, Fremdschlüssel und echte Migrationen werden
  gegen PostgreSQL geprüft. Die erste textuelle Ähnlichkeitssuche scannt begrenzte
  vollständige Textbestände mit RapidFuzz. Ein `pg_trgm`-Kandidatenindex und
  persistierte Suchsegmente bleiben einer gemessenen Optimierung vorbehalten.
- **Originalbytes und Herkunft:** Dateiname ist ein bereinigtes Anzeigefeld,
  niemals ein Dateipfad. SHA-256 adressiert Inhalt, die Artefakt-ID dessen konkrete
  Herkunft. Inhaltsgleiche Uploads werden nicht als dasselbe Dokument behandelt.
- **Lokale Ablage:** Der API-Container läuft ohne root-Rechte. Ein benanntes Volume
  hält Originalbytes; ein späterer Blob-Storage-Adapter kann die Ablage ersetzen.
  Die tatsächliche Storage-Schnittstelle bietet Stream-/Byte-Ablage und Abruf.
- **Ehrlicher Status:** Ein erfolgreicher Upload ist keine erfolgreiche Extraktion.
  Jobstatus, Seitenabdeckung und Qualität sind getrennt. Eine Prüfvormerkung bleibt
  auch bei vollständig verarbeitetem Text sichtbar und wird für dieselbe Quelle
  nicht automatisch zurückgenommen; daraus wird kein Qualitätssiegel abgeleitet.
- **Lokale API-Dokumentation:** Swagger-JavaScript und CSS kommen aus einer
  installierten Abhängigkeit statt aus einem CDN. Der Core braucht nach dem Build
  keine externen Dienste.
- **Suchprinzip:** Exact/normalized prüfen den ganzen
  ausgewählten Text. Fehlende oder fragwürdige Extraktion wird unverifizierbar;
  ein Treffer wird mit Quelle belegt. Textuelle Ähnlichkeit hat einen separaten
  positiven Kandidatenablauf; sie und eine spätere semantische Ähnlichkeit sind
  keine Beweise für Abwesenheit.

- **Ein Job ist ein Lauf:** Pro Revision genau ein aktiver Lauf, transaktional
  beansprucht. Wiederholung erstellt einen neuen Datensatz. Alte Artefakte bleiben
  erhalten; erst die abgeschlossene Veröffentlichung wechselt den ausgewählten Text.
- **Einfache Warteschlange:** PostgreSQL reicht für diesen lokalen Prototyp.
  Ein eigener Worker hält OCR außerhalb von HTTP-Anfragen. Ein hart abgebrochener
  Lauf erfordert explizite Wiederherstellung statt einer riskanten automatischen
  Zeitüberschreitung mit eventuell noch arbeitendem Vorgänger.
- **Konservative Extraktion:** Jede PDF-Seite mit Rasterbildern wird als Ganzes
  OCRt, auch wenn eine Textschicht vorhanden ist. Das verhindert, dass ein Header
  den unlesenen Scaninhalt verdeckt. Hochwertige Mischlayouts könnten später gezielt
  kombiniert werden. Leere Seiten werden vorerst zur Prüfung markiert.
- **Qualitätsheuristik v1:** Weniger als zehn alphanumerische Zeichen,
  Unicode-Ersatzzeichen oder mehr als max(5, 8 Prozent der Zeichen) ungewöhnliche
  Zeichen erzeugen Prüfbedarf. Bei OCR gelten ein mittlerer Wortscore unter 80/100
  oder mehr als 20 Prozent Wörter unter 50/100 als Auffälligkeit. Fehlende
  Konfidenzwerte erzeugen ebenfalls Prüfbedarf. Die Werte sind keine kalibrierten
  Wahrscheinlichkeiten und keine Garantie für Handschrift oder korrektes Wording.
- **Stabile Normalisierung:** NFC und Whitespace-/Casefold-Regeln behalten rechtlich
  bedeutsame Zeichen bei. Mehrdeutige Silbentrennungen werden nicht repariert.
  Unicode-Casefold kann Zeichen erweitern; deshalb referenzieren Seitenoffsets
  ausdrücklich den normalisierten Text und keine geratenen Rohtextpositionen.

- **Ein gemeinsamer Such-Snapshot:** Die neueste Revision wird unabhängig vom
  Verarbeitungszustand gewählt. PostgreSQL prüft den gesamten ausgewählten Text
  per `strpos`; eine Read-only-Transaktion mit `REPEATABLE READ` hält Zählungen,
  Herkunft, Ausschnitte und Seitenpositionen konsistent. Unverifizierbare Dokumente
  haben eigene Pagination und werden nie in negativen Treffern versteckt.
- **Erste Fundstelle pro Dokument:** Dokumente sind die Einheit der Ergebnisliste,
  kein Ranking über Textsegmente. Alle Offsets nennen ihren Roh-/Normaltextbezug
  und sind Unicode-Codepoints. Seiten und Originale sind aufrufbar; geänderte
  ausgewählte Läufe lösen einen Hinweis zur erneuten Suche aus.

- **Suchsteuerung vor Semantik:** Textuelle Schwelle 0 wird abgelehnt. Ein gemeinsam
  verwendetes Query-Assessment erklärt längenabhängige Edit-Budgets und einfache
  Risikohinweise, ohne einen statistisch sicheren Mindestwert zu behaupten.
  Fundstellenanzahl/-dichte und Ressourcenbudgets können einen Lauf abbrechen;
  dann wird keine Teilmenge als fertiges Suchergebnis ausgegeben. Die Oberfläche
  verändert keine Schwelle automatisch und kann auf das offene Dokument eingrenzen.

- **Semantik nach konkreten Fundstellen:** Ein lokales, fest versioniertes
  MiniLM-ONNX-Modell bewertet erst textuell gefundene Passagen. Embeddings entstehen
  bei Bedarf und werden nach Textinhalt und Pipeline-Version wiederverwendet.
  Kontext wird angezeigt, aber nicht in den Passagenscore eingemischt. Semantische
  Filterung erfolgt vor Pagination und Zählung; textuelle Rangfolge bleibt erhalten.
  100 bedeutet ausdrücklich identischen Vergleichstext, niedrigere Scores sind
  keine Wahrscheinlichkeiten oder juristische Äquivalenz. Überlange Modelleingaben
  werden abgelehnt statt abgeschnitten. Feste Singleton-Eingaben verhindern, dass
  dynamische INT8-Quantisierung vom übrigen Batch oder Cache-Zustand abhängt.
  Grenzen und Messbeispiele stehen in [semantic-search.md](semantic-search.md).

- **Prüfentscheidungen pro Fundstelle und Ausdruck:** Keep, Dismiss und Decide
  later werden getrennt von Not reviewed gespeichert. Identität folgt dem
  Verarbeitungslauf, Modus, effektiven Suchausdruck und den vorhandenen
  Fundstellenregeln; Schwellen und semantisches Modell sind keine menschliche
  Entscheidungsidentität. Explizite Resets behalten eine Versionsnummer gegen
  veraltete Schreibversuche. Statusfilter wirken nach beiden Ähnlichkeitsfiltern
  und vor Pagination; Zähler zeigen den Bestand vor dem Statusfilter. Ein neuer
  Lauf erhält neue Fundstellenidentitäten. Die lokale Anwendung teilt aktuelle
  Entscheidungen ohne Reviewer-Konten oder vollständiges Ereignis-Audit.
