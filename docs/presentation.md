# TrayStack — Präsentationsleitfaden (18 Minuten)

Stand: 30.10.2026. Sprechfertiger Ablauf zur beigefügten Riverty Case Study;
als Foliengliederung oder direkt als Gesprächsleitfaden nutzbar.
**Lokal implementiert** sind Upload, Extraktion, Qualität, Suche und Quellenbelege.
**Vorgeschlagen** sind Azure-Betrieb, SharePoint-Anbindung und Pilot. Ein
Handschriftvergleich wurde noch nicht durchgeführt.

## 1. Aufgabe und Erfolgskriterium · 0:00–1:30

**Auf die Folie:** „Verträge schneller finden — mit prüfbarer Quelle und sichtbarer Unsicherheit.“

- Zwei Aufgaben: einen Firmennamen finden und Verträge identifizieren, in deren
  extrahiertem Text eine vorgegebene Passage nicht gefunden wurde.
- Heute: Dokumente einzeln öffnen, suchen, Ergebnisse überprüfen.
- Ziel: Sucharbeit bündeln; juristische Entscheidung bleibt bei Legal.

**Sprechtext:** „Der kritische Fall ist die fehlende Passage. Ein nicht gefundener
Treffer kann auch bedeuten, dass wir den Scan nicht lesen konnten. Deshalb liefert
TrayStack drei Ergebnisse: gefunden, im verarbeiteten Text nicht gefunden und
unverifizierbar.“

## 2. Wortlaut, Qualität und Herkunft · 1:30–3:00

**Auf die Folie:** Drei unabhängige Fragen: Ist der Lauf fertig? Sind alle Seiten
verarbeitet? Gibt es bekannte Qualitätsprobleme?

Exact prüft den Wortlaut. Normalized vereinheitlicht Unicode, Groß-/Kleinschreibung
und Whitespace; Zahlen, Negationen und Satzzeichen bleiben erhalten. Beide Modi
prüfen den gesamten ausgewählten Text der neuesten Revision. Ein positiver
Treffer darf Qualitätswarnungen tragen; ein negatives Ergebnis benötigt vollständige
Abdeckung ohne bekannte Auffälligkeit. Das ist keine Garantie fehlerfreier OCR.

**Beispiel:** Eine Top-k-Liste mit zehn ähnlichen Absätzen sagt nicht, dass die
Passage im übrigen Vertrag fehlt. Semantische Klauselbewertung ist eine spätere,
separat zu evaluierende Aufgabe. Hier ist kein LLM erforderlich.

## 3. Live-Demo · 3:00–9:00

Vorbereitung und Ersatzablauf: [Demo](demo.md). Den Prüf-Stack oder einen mit den
vier synthetischen Dateien vorbereiteten Stack nutzen; OCR nicht erst während
der Präsentation installieren. Keine Echtverträge verwenden.

| Zeit | Aktion | Aussage am Bildschirm |
|---|---|---|
| 3:00–4:00 | A hochladen, Original herunterladen, Verarbeitung starten | Dokument, Revision und Artefakt bleiben verschieden; Originalbytes bleiben erhalten. |
| 4:00–5:00 | Seitentext, JSON/Markdown und Laufhistorie öffnen | Text stammt aus tatsächlicher Verarbeitung; Quelle, Parameter und Versionen sind sichtbar. |
| 5:00–6:15 | Normalisiert nach `The receiving party shall not disclose confidential information` suchen | A und der vorab verarbeitete Druckscan P liefern Treffer. Fundstelle öffnen, zum Original zurückgehen. |
| 6:15–7:30 | Auf „Nicht im extrahierten Text gefunden“ wechseln | D ist negativ; der schwierige, vorgemerkte Scan E bleibt separat unverifizierbar. |
| 7:30–8:15 | Prüfgruppe und Qualität von E öffnen | Vollständige Seitenabdeckung kann mit Prüfbedarf zusammenfallen. E ist degradierter Druck, keine Handschrift-Evaluation. |
| 8:15–9:00 | Erneute Verarbeitung und Herkunft erklären | Neuer Lauf erzeugt neue Artefakte. Fehlgeschlagene Läufe erhalten den bisherigen ausgewählten Text und zeigen den Fehler. |

**Sprechtext:** „Ein Firmenname wird genauso als Literal gesucht. Ich lasse mir
Fundstelle und Original zeigen; eine Vertragsänderung erfolgt anschließend im
freigegebenen juristischen Prozess. Die Anwendung verändert keine Vertragsdateien.“

## 4. Umsetzung und vorgeschlagener Azure-Betrieb · 9:00–11:00

**Auf die Folie:** Diagramm aus [Produktionskonzept](production.md).

Lokal laufen React/TypeScript, FastAPI, ein separater Python-Worker, PostgreSQL und
ein Dateivolume. Jobs werden transaktional beansprucht. Erst die Veröffentlichung
eines Ergebnisses ersetzt den ausgewählten Text. Ein Such-Snapshot hält
Ergebnisliste, Herkunft und Seitenbelege konsistent.

Azure-Vorschlag: Container Apps für Web/API/Worker, Azure Database for PostgreSQL
für Metadaten/Text und Blob Storage für Originale und Ableitungen. Dazu Entra ID,
Managed Identities und Monitoring. Das sind Entwurfsentscheidungen, keine bereits
ausgerollten Ressourcen. Der Blob-Adapter und Berechtigungsprüfung fehlen noch.

SharePoint bleibt Quelle. Quell-ID, Quellversion, Rechte und Löschungen müssen
übernommen werden. Die eingeschränkte Archiv-REST-API erhält ausschließlich eine
zusätzliche Kopie; sie ist weder Such- noch Extraktionsbackend.

## 5. Microsoft-Vergleich und Auswahl · 11:00–13:00

**Auf die Folie:** Vergleichstabelle aus [Produktionskonzept](production.md).

- Lokale Extraktion ist die reproduzierbare Offline-Basis. Gedruckte Scans sind
  geprüft; Tesseract wird hier nicht als zuverlässige Handschrifterkennung verkauft.
- Azure Document Intelligence Read ist ein dokumentierter Kandidat für Druck und
  Handschrift mit Seiten-/Positionsdaten. Wie gut historische Vertragsseiten
  erkannt werden, bleibt eine offene Messfrage.
- SharePoint OCR mit vorhandener Suche ist eine zu prüfende Microsoft-Alternative.
  OCR und Indexierung allein belegen noch nicht den hier benötigten vollständigen
  Negativ-Suchvertrag mit Qualitätsausschluss.

**Entscheidung:** Vor einem Eigenbau-Rollout vorhandene Microsoft-Möglichkeiten
am gleichen freigegebenen Korpus prüfen. Eigene Verarbeitung nur dort behalten,
wo Qualität, Nachvollziehbarkeit oder Arbeitsablauf sie rechtfertigen. Keine
Behauptung über bessere Erkennung, geringere Kosten oder Zeitersparnis ohne Messung.

## 6. Pilot und Adoption · 13:00–16:00

**Auf die Folie:** „Gemeinsam definieren → kontrolliert vergleichen → gezielt erweitern.“

Vorschlag: ein Legal-Verantwortlicher, drei bis fünf Anwender sowie Engineering
und ein Ansprechpartner für Informationssicherheit. Größe und Dauer werden vor
Beginn abgestimmt; das ist keine bereits getroffene Organisationsentscheidung.

1. Zwei echte Arbeitsaufgaben auswählen und Wortlaut versus Bedeutung klären.
2. Freigegebenes, menschlich geprüftes Referenzset nach Digital-PDF, Druckscan und
   schwierigen/handgeschriebenen Seiten schichten. Bekannte Positive, Negative
   und unentscheidbare Fälle getrennt markieren.
3. Kurze Einführung am Original: Fundstelle öffnen, Qualitätswarnungen verstehen,
   „unverifizierbar“ eskalieren. Es gibt im Prototyp keine Freigabe von Prüfbedarf.
4. Manuelle und unterstützte Bearbeitung derselben Aufgaben gegenbalanciert
   vergleichen; Reihenfolge wechseln, damit Erinnerung die Zeitmessung nicht verfälscht.
5. Wöchentlich Fehlertypen und Begriffe mit Legal besprechen. Ein fachlicher Owner
   priorisiert; Engineering verantwortet Laufprobleme und Betrieb.

| Messgröße | Definition und Entscheidung |
|---|---|
| Trefferpräzision/-recall | Korrekte positive Dokument-Passagen-Paare / alle vorgeschlagenen bzw. alle bekannten positiven Paare. Unverifizierbare bekannte Positive zählen beim Recall als nicht gefunden. |
| Falsche Abwesenheit | Negative Vorschläge trotz bekannter Passage / alle negativen Vorschläge; separat absolute Anzahl und nach Dokumenttyp ausweisen. |
| Prüfaufwand | Anteil unverifizierbarer Paare und Minuten für Originalprüfung; nicht aus Erfolgsfällen herausrechnen. |
| Zeit bis Entscheidung | Median und langsame Fälle je Aufgabe einschließlich manueller Nachprüfung, verglichen mit manueller Basis. |
| Nutzbarkeit | Aufgabenabschluss, Fehlinterpretationen der drei Status und konkrete Rückmeldungen. |

Vor Beginn legt Legal mit dem Team tolerierbare Fehler und Mindestnutzen fest.
Ein nachgewiesener falscher Abwesenheitsvorschlag wird untersucht; bis zur Klärung
wird dieser Workflow im Pilot nur mit obligatorischer Originalprüfung verwendet.
Bei unzureichender Handschriftqualität bleiben diese Seiten im manuellen Prozess.
Ausrollen erst nach fachlicher Abnahme und den offenen Betriebsvoraussetzungen.

## 7. Grenzen, nächste Schritte und Gespräch · 16:00–18:00

**Auf die Folie:** „Core demonstriert; Produktionsreife und Handschrift noch offen.“

- Suche ist ein Vollscan des ausgewählten Textes; keine Lastmessung für große Bestände.
- Qualitätsheuristiken erkennen nicht jeden OCR-Fehler. Historische Handschrift
  braucht ein eigenständiges Referenzset und ggf. einen anderen Extraktor.
- Authentifizierung, Rechteübernahme, Retention, Backup/Restore und Audit fehlen
  im lokalen Prototyp. Produktionskonzept und Pilot sind noch nicht umgesetzt.
- Fuzzy-Suche, komfortable Revisionserstellung, zusätzliche Upload-Repräsentationen
  und semantischer Vergleich sind ausdrücklich zurückgestellt.

**Abschlussfrage an das Team:** „Welche Vertragsarten und Fehlertypen verursachen
heute den größten Prüfaufwand? Damit würde ich Korpus und Pilot zuerst ausrichten.“

## Rückfragen vorbereiten

- **Warum kein Agent?** Der klar umrissene Wortlaut-Workflow benötigt keine autonome
  Werkzeugwahl. Ein Agent würde die Vollständigkeit einer Negativsuche nicht garantieren.
- **Warum PostgreSQL?** Ein konsistenter Bestand für Metadaten, Jobs und Volltext
  reicht für den begrenzten Prototyp. Größere Bestände brauchen Messung und Optimierung.
- **Ist ein Hash ein Compliance-Nachweis?** Er prüft Bytegleichheit, ersetzt aber
  weder Aufbewahrungsregeln noch Zugriffskontrolle oder ein rechtssicheres Archiv.
- **Was passiert beim Absturz?** Alte veröffentlichte Ergebnisse bleiben erhalten;
  ein hart abgebrochener laufender Job benötigt dokumentierte Betreiberwiederherstellung.
- **Wie wurde KI genutzt?** Codex unterstützte Implementierung und Dokumentation;
  API-/OCR-/Browserprüfungen und PR-Reviews prüfen konkrete Ergebnisse. Zur Laufzeit
  verwendet der Prototyp keine generative KI und keine Cloudmodelle.
