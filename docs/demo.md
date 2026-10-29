# Demo und Prüfstand — Meilenstein 1

## Reproduzierbarer Ablauf

1. `docker compose up --build` starten; Migration muss erfolgreich enden und API
   gesund werden. <http://localhost:8080> öffnen.
2. `examples/synthetic-contracts/A-confidentiality.pdf` mit einem Titel hochladen.
3. Dokumentdetails öffnen: drei getrennte IDs, Originaltyp, Größe und voller
   SHA-256-Hash müssen erscheinen. Es gibt genau eine Revision und ein Original.
4. Original herunterladen. Bytes und SHA-256 müssen zur Eingabedatei passen.
5. `P-printed-scan.jpg` und `D-delivery.pdf` hochladen.
6. `E-difficult-scan.jpg` mit aktivierter manueller Prüfvormerkung hochladen.
   Die Vormerkung muss in den Dateidetails stehen.
7. Seite neu laden und einen Eintrag erneut öffnen. Die Daten bleiben erhalten.
   Es gibt noch keine OCR oder Suche; alle Einträge sind nicht verarbeitet.
8. Optional einen ungültigen Upload versuchen: Die Oberfläche meldet den echten
   Fehler und zeigt keinen erfolgreich angelegten Eintrag.

API-Beispiel (vom Repository-Stammverzeichnis):

```sh
curl --fail http://localhost:8000/api/health
curl --fail -X POST http://localhost:8000/api/documents/upload \
  -F 'title=Vertraulichkeitsvereinbarung' \
  -F 'metadata={"company":"Example Company"}' \
  -F 'file=@examples/synthetic-contracts/A-confidentiality.pdf'
```

Artefakt-ID aus der Antwort übernehmen und herunterladen:

```sh
curl --fail http://localhost:8000/api/artifacts/ARTEFAKT-ID/content -o /tmp/traystack-original.pdf
sha256sum examples/synthetic-contracts/A-confidentiality.pdf /tmp/traystack-original.pdf
```

## Prüfungen

Die genauen Start- und Testkommandos stehen in der README. Backendtests prüfen
Storage-Verhalten, ungültige Schlüssel, Migrationen über eine leere PostgreSQL-
Testdatenbank, Upload/Listen/Details/Download, Hashwerte, Limit-/Typvalidierung,
Metadaten, fehlende Objekte und relationale Invarianten. Ein Browser-Smoke-Test
prüft den echten Upload, Persistenz nach Neuladen, Prüfvormerkung, bytegleichen
Download und das Layout bei schmalem Viewport.

Die Sucherwartungen im Fixture-Manifest sind bewusst spätere Akzeptanzziele.
Die schwierige Demo-Datei ist ein degradierter Druckscan; sie ersetzt keine
Evaluation historischer Handschrift.

## Tatsächlich geprüft am 29.10.2026

- Vollständiger Docker-Compose-Build und Start mit automatischer Migration:
  erfolgreich; PostgreSQL und API gesund, Readiness für Datenbank/Storage `ok`.
- 31 Backendtests gegen PostgreSQL 17: bestanden, keine übersprungenen Tests.
  Die erste Ausführung erfolgte auf einer frisch gestarteten leeren Testdatenbank.
  Der Schemaabgleich zwischen Migration und ORM ergab keine Abweichungen.
- Zwei Chrome-/Playwright-Tests gegen den Compose-Stack: bestanden, einschließlich
  Upload/Download und API-Explorer mit blockierten externen Netzaufrufen.
- TypeScript-Prüfung und Vite-Produktionsbuild: bestanden.
- Ruff-Prüfung/-Formatkontrolle, Prettier-Kontrolle und `git diff --check`: bestanden.

Die aktuelle Starlette-Testclient-Version meldet eine Deprecation-Warnung für die
Verwendung von HTTPX im Testclient. Die Tests laufen erfolgreich; dies betrifft
nicht die HTTP-Verarbeitung der laufenden Anwendung.
