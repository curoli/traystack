# Demo und Prüfstand — Meilenstein 2

## Reproduzierbarer Ablauf

1. `docker compose up --build` starten. Migration `0002` muss erfolgreich enden;
   API, PostgreSQL, Webserver und separater Worker laufen. <http://localhost:8080> öffnen.
   Bereits hochgeladene Dokumente aus Meilenstein 1 bleiben erhalten.
2. `examples/synthetic-contracts/A-confidentiality.pdf` mit einem Titel hochladen.
   Die Details zeigen Dokument, Revision 1 und das unveränderte Original.
3. Quelle in den Details prüfen und **Verarbeitung starten** wählen. Der Status
   wechselt von wartend/laufend auf verarbeitet. Seitenabdeckung und Qualität
   erscheinen getrennt: eine verarbeitete Seite, keine bekannte Auffälligkeit.
4. **Seitentext ansehen** öffnen. Die Vertraulichkeitspassage stammt aus der realen
   PDF-Textschicht. JSON und Markdown stehen als neue Artefakte mit Quelle, Lauf-ID,
   Verfahren und Hash bereit; ihre Vorschau zeigt tatsächlichen Dateiinhalt.
5. **Original herunterladen** wählen und Bytes/Hash mit der Eingabedatei vergleichen.
6. `P-printed-scan.jpg` hochladen und verarbeiten. Hier arbeitet tatsächlich
   Tesseract. Die Seitenansicht nennt OCR und den mittleren Wortscore; der Score
   ist keine Wahrscheinlichkeit für einen korrekten Vertragstext.
7. `E-difficult-scan.jpg` mit **Manuelle Prüfung erforderlich** hochladen und
   verarbeiten. Der Eintrag bleibt in der gesonderten Prüfgruppe. Auch vollständig
   verarbeitete Seiten können weiterhin prüfbedürftig sein. Original herunterladen
   und manuell prüfen; es gibt keinen Knopf, der OCR als rechtlich korrekt bestätigt.
8. Beim digitalen PDF **Erneut verarbeiten** wählen. Es entstehen ein neuer Lauf
   und zwei neue Artefakte; alte Artefakte bleiben zugänglich. Die Textansicht
   nennt den neu ausgewählten Lauf.
9. **Verarbeitungsläufe** aufklappen: Eingabeparameter, Engine-Versionen und
   Normalisierungsversion sind pro Lauf nachvollziehbar. Bei Fehlern wird ein
   fester Fehlercode gezeigt; vorhandener ausgewählter Text bleibt erhalten.
10. Seite neu laden. Dokumente, Artefakte, Status und ausgewählter Text bleiben
    bestehen. Die Suche ist in diesem Meilenstein noch nicht implementiert.

Die schwierige Datei ist ein degradierter Druckscan und ersetzt keine Evaluation
historischer Handschrift. Die Sucherwartungen im Fixture-Manifest sind Akzeptanzziele
für Meilenstein 3, keine vorberechneten Ergebnisse der Anwendung.

## API-Demo

Upload vom Repository-Stammverzeichnis:

```sh
curl --fail http://localhost:8000/api/health
curl --fail -X POST http://localhost:8000/api/documents/upload \
  -F 'title=Vertraulichkeitsvereinbarung' \
  -F 'metadata={"company":"Example Company"}' \
  -F 'file=@examples/synthetic-contracts/A-confidentiality.pdf'
```

Revisions- und Artefakt-ID aus der Antwort übernehmen:

```sh
curl --fail -X POST http://localhost:8000/api/revisions/REVISIONS-ID/process \
  -H 'Content-Type: application/json' -d '{"source_artifact_id":"ARTEFAKT-ID"}'
curl --fail http://localhost:8000/api/jobs/JOB-ID
curl --fail http://localhost:8000/api/revisions/REVISIONS-ID/text
curl --fail http://localhost:8000/api/artifacts/ARTEFAKT-ID/content -o /tmp/traystack-original.pdf
sha256sum examples/synthetic-contracts/A-confidentiality.pdf /tmp/traystack-original.pdf
```

Ein weiterer Start während eines aktiven Laufs liefert 409. Ein fehlgeschlagener
Job lässt sich über `POST /api/jobs/JOB-ID/retry` als neuer Lauf wiederholen.
Seine Parameter werden übernommen; ein inzwischen gesetzter manueller Prüfbedarf
wird zusätzlich beibehalten. Bei geänderten OCR-Sprachen oder Grenzen einen neuen
Verarbeitungslauf starten statt die alten Parameter unverändert zu wiederholen.

## Prüfungen

Die exakten Testkommandos stehen in der README. Backendtests verwenden eine
eigene PostgreSQL-Datenbank, angewendete Migrationen und echte OCR für gedruckte
Scans. Sie prüfen auch gemischte PDFs, Text-/Seitenoffsets, Fremdquellen, parallele
Worker-Claims, Timeout/Enginefehler, fehlerhafte Veröffentlichung, Auswahl alter
Ergebnisse nach Fehlschlag und neue Wiederholungsläufe. Kontrolliert simulierte
Fehler ergänzen die Tests; erfolgreiche Demo-Ergebnisse werden nie simuliert.

Worker-Abbruch und Wiederherstellung sind in der README beschrieben. Für diesen
Prototyp sind weder automatische Wiederholungen noch sichere zeitbasierte
Lease-Übernahmen implementiert. Mehrbild-/animierte Bilddateien werden bei der
Verarbeitung explizit abgelehnt, statt nur das erste Bild als vollständigen Inhalt
zu behandeln. Leere Seiten werden vorsichtshalber zur Prüfung markiert.

## Tatsächlich geprüft am 29.10.2026

- Beide Migrationen auf einer frischen PostgreSQL-17-Testdatenbank sowie Upgrade
  des laufenden Meilenstein-1-Stacks mit erhaltenen Originalen: erfolgreich.
- 60 Backendtests: bestanden, keine übersprungenen Tests. Darunter echte Tesseract-
  OCR, gemischte PDFs, zeitgleiche Worker-Claims und atomare Rücknahme bei einem
  absichtlich ausgelösten Datenbankfehler während der Veröffentlichung.
- Fünf Chrome-/Playwright-Szenarien gegen den Compose-Stack: Upload/bytegleicher
  Download, PDF-Verarbeitung/Neuverarbeitung, echte JPEG-OCR, schwieriger Scan mit
  Prüfbedarf und API-Explorer ohne externe CDN-Aufrufe.
- TypeScript-Prüfung, Vite-Produktionsbuild, Ruff, Prettier und `git diff --check`:
  bestanden. Der ORM-/Migrationsabgleich meldet keine Schemaabweichung.

Die installierte Starlette-Version meldet weiterhin eine Deprecation-Warnung für
HTTPX im Testclient. Die Tests laufen erfolgreich; diese Warnung betrifft nicht
die HTTP-Verarbeitung der laufenden Anwendung.
