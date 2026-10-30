# Demo und Prüfstand — Meilenstein 4

## Frischer Prüf-Stack

Vom Repository-Stamm aus; Docker/Compose v2 und Python 3.12+ vorausgesetzt.
Ein eigener Compose-Projektname und eigene Ports trennen die Demo vom normalen
Stack. Beim ersten Aufruf entstehen neue Datenvolumes. Der Build braucht Zugriff
auf Image-/Paketregistries, die laufende Anwendung keine externen Dienste.

```sh
WEB_PORT=18080 API_PORT=18000 docker compose -p traystack-m4-review up -d --build --wait
python3 scripts/demo_smoke.py --base-url http://localhost:18080
```

<http://localhost:18080> öffnen. Das Skript zeigt einen Laufbezeichner wie
`Demo 02aa7981`; die vier Dokumenttitel beginnen damit. Es prüft tatsächliche
Uploads, bytegleiche Originaldownloads, Worker/OCR, JSON-/Markdown-Abruf sowie
A/P als Treffer, D als negativ und E als unverifizierbar. Vorhandene Trefferlisten
werden vollständig paginiert. Pro Aufruf entstehen vier weitere Dokumente.
Die Skriptprüfung ersetzt nicht die Browserprüfungen für Fokus und Bedienung.

Browserprüfungen gegen genau diesen Stack:

```sh
TRAYSTACK_BASE_URL=http://localhost:18080 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm run test:e2e --prefix frontend
```

Alternativ Playwright-Chromium wie in der README installieren und
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` weglassen. Die Browserprüfungen legen weitere
synthetische Dokumente an. Für eine kurze Präsentation die Demo vor diesen Tests
vorbereiten oder einen weiteren eigenen Compose-Projektnamen mit freien Ports
verwenden. Den Prüf-Stack anschließend stoppen, Daten bleiben erhalten:

```sh
docker compose -p traystack-m4-review down
```

Kein `down -v` auf dem regulären Stack verwenden, um eine Demo aufzuräumen.
Für einen weiteren Start aus leerem Zustand einen bisher unbenutzten Projektnamen
wählen. Wiederverwendung desselben Projektnamens verwendet vorhandene Volumes.

## Vorführung und Ersatzablauf

Den [18-Minuten-Leitfaden](presentation.md) mit einer sechsminütigen Live-Demo
verwenden. Die vier Beispiele vorher verarbeiten, eine Neuverarbeitung von A
kann live gezeigt werden. Die Zielpassage steht unten und im Fixture-Manifest.
Ist der Stack nicht verfügbar, anhand der Architektur und des dokumentierten
Prüfstands erklären, was geprüft wurde; keine Screenshots als laufende Verarbeitung
ausgeben. Bei Workerproblemen Jobstatus/Fehler und den Wiederherstellungsablauf
der README zeigen. Fehlgeschlagene oder unsichere Dokumente bleiben prüfbedürftig.

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
6. `D-delivery.pdf` ebenfalls hochladen und verarbeiten; es enthält die Zielpassage
   nicht. Danach `P-printed-scan.jpg` hochladen und verarbeiten. Hier arbeitet tatsächlich
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
    bestehen. Nun oben die Passage `The receiving party shall not disclose confidential information`
    im normalisierten Modus suchen. A und P liefern positive Treffer; D erscheint
    bei „Nicht im extrahierten Text gefunden“. E bleibt unverifizierbar.
11. Einen weiteren Vertrag hochladen und noch nicht verarbeiten: Auch er bleibt
    unverifizierbar und wird nicht als negativer Treffer ausgegeben.
12. Bei einem Treffer **Seite 1 ansehen** wählen. Der Seitentext wird geöffnet;
    Qualitätsinformationen und Originaldownload bleiben verfügbar. Nach erneuter
    Verarbeitung eines Treffers weist ein Klick auf die alte Suchfundstelle auf
    die veraltete Momentaufnahme hin.

Die schwierige Datei ist ein degradierter Druckscan und ersetzt keine Evaluation
historischer Handschrift. Die Sucherwartungen im Fixture-Manifest dienen der Prüfung tatsächlicher Ergebnisse;
die Anwendung berechnet ihre Treffer ausschließlich aus dem gewählten Textbestand.

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

Suchanfrage:

```sh
curl --fail -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"The receiving party shall not disclose confidential information","mode":"normalized","relation":"lacks","scope":"latest","limit":25}'
```

Den [Suchvertrag](search.md) für Status, separate Pagination und Offsetregeln beachten.

## Prüfungen

Die exakten Testkommandos stehen in der README. Backendtests verwenden eine
eigene PostgreSQL-Datenbank, angewendete Migrationen und echte OCR für gedruckte
Scans. Sie prüfen auch gemischte PDFs, Text-/Seitenoffsets, Fremdquellen, parallele
Worker-Claims, Timeout/Enginefehler, fehlerhafte Veröffentlichung, Auswahl alter
Ergebnisse nach Fehlschlag und neue Wiederholungsläufe. Kontrolliert simulierte
Fehler ergänzen die Tests; erfolgreiche Demo-Ergebnisse werden nie simuliert.
Kontrollierte kanonische Textfixtures decken zusätzliche Suchrandfälle ab; ein
End-to-End-Test führt PDF/JPEG-Upload, echten Worker, Suche und Originalabruf aus.

Worker-Abbruch und Wiederherstellung sind in der README beschrieben. Für diesen
Prototyp sind weder automatische Wiederholungen noch sichere zeitbasierte
Lease-Übernahmen implementiert. Mehrbild-/animierte Bilddateien werden bei der
Verarbeitung explizit abgelehnt, statt nur das erste Bild als vollständigen Inhalt
zu behandeln. Leere Seiten werden vorsichtshalber zur Prüfung markiert.

## Tatsächlich geprüft am 30.10.2026

- Getrennter Compose-Stack `traystack-m4-review` mit neuen PostgreSQL-/Blob-Volumes:
  Build, beide Migrationen und gesunder Start erfolgreich. Der reguläre Datenbestand
  wurde dafür nicht gelöscht. Zusätzlich alle Backendtests auf der separaten,
  flüchtigen PostgreSQL-17-Testdatenbank ausgeführt.
- `scripts/demo_smoke.py` gegen den frischen Stack: alle vier Uploads, Originalbytes,
  reale Extraktion/OCR, Ableitungen und erwartete Suchklassifikation erfolgreich.
  Kein Azure-/SharePoint-Aufruf und keine Handschriftevaluation durchgeführt.
- 102 Backendtests: bestanden, keine übersprungenen Tests. Darunter echte OCR,
  gemischte/Inline-PDFs, Worker-Claims und atomare Veröffentlichung sowie Volltext-
  suche, neueste Revisionen, getrennte Negativ-/Unverifizierbar-Pagination,
  Unicode-Fundstellen und ein Snapshot-Test bei gleichzeitiger Neuverarbeitung.
- Neun Chrome-/Playwright-Szenarien: Upload/Download, echte Verarbeitung, Navigation
  auf Desktop/Mobil, positive/negative Suche mit separaten unverifizierbaren
  Dokumenten, Seitensprung einschließlich wiederholtem Öffnen derselben Fundstelle,
  veraltete Fundstellen und API-Explorer ohne CDN.
  Ein isolierter Renderer-Test prüft Unicode-Codepoint-Hervorhebung; die übrigen
  Abläufe verwenden den echten Compose-Stack.
- TypeScript-Prüfung, Vite-Produktionsbuild, Ruff, Prettier und `git diff --check`:
  bestanden. `docker compose -p traystack-m4-review exec -T api alembic check`
  meldet keine Schemaabweichung. `pip check` meldet keine defekten Abhängigkeiten.

Die installierte Starlette-Version meldet weiterhin eine Deprecation-Warnung für
HTTPX im Testclient. Die Tests laufen erfolgreich; diese Warnung betrifft nicht
die HTTP-Verarbeitung der laufenden Anwendung.
