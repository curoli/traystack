# TrayStack

Lokaler Prototyp für nachvollziehbare Vertragsablage und spätere Textsuche.
**Meilenstein 1 ist umgesetzt:** PDF/JPEG/PNG hochladen, Dokumente auflisten,
Revision und Originalartefakt ansehen und die unveränderten Bytes herunterladen.
OCR, Worker, abgeleitete Texte und Suche sind noch nicht implementiert.

## Start

Voraussetzungen: Docker mit Compose v2+ und Zugriff auf den Docker-Daemon.
Der erste Build lädt Images und Abhängigkeiten; die laufende Anwendung benötigt
keine Cloud-Dienste, API-Schlüssel oder externen Netzaufrufe. Auch die API-Dokumentation
wird lokal ausgeliefert.

```sh
docker compose up --build
```

- Oberfläche: <http://localhost:8080>
- API-Dokumentation: <http://localhost:8080/docs> oder <http://localhost:8000/docs>
- Bereitschaftsprüfung: <http://localhost:8000/api/health>

PostgreSQL, Migration, API und Webserver starten in der richtigen Reihenfolge.
Die Migration endet nach erfolgreicher Ausführung mit Exit-Code 0. Daten und
Originaldateien liegen in benannten Docker-Volumes. `docker compose down` stoppt
den Stack und erhält die Volumes.

Die Standardwerte funktionieren ohne `.env`. Für Anpassungen `.env.example`
nach `.env` kopieren. `WEB_PORT`, `API_PORT` und `UPLOAD_MAX_BYTES` sind konfigurierbar.
Der Webserver begrenzt den gesamten Request zusätzlich auf 26 MiB; für höhere
Dateilimits auch `frontend/nginx.conf` anpassen. Die Datenbank wird nicht zum Host
veröffentlicht; API und Oberfläche sind an Loopback gebunden. Die Zugangsdaten
sind ausschließlich lokale Demo-Standardwerte.

## Demo in zwei Minuten

1. Oberfläche öffnen und einen Titel eingeben.
2. `examples/synthetic-contracts/A-confidentiality.pdf` auswählen und speichern.
3. Dokumentdetails zeigen Dokument-, Revisions- und Artefakt-ID, Dateityp, Größe und SHA-256.
4. **Original herunterladen** wählen und mit der Eingabedatei vergleichen.
5. Weitere Demo-Dateien hochladen. Bei `E-difficult-scan.jpg` **Manuelle Prüfung erforderlich** setzen.
6. Seite neu laden: Dokumente bleiben gespeichert. Der Status lautet **Nicht verarbeitet**.

Die [Demo-Dateien](examples/synthetic-contracts/README.md) sind synthetisch. Ihre
Hashwerte und späteren Sucherwartungen stehen im Manifest. Es gibt keine
vorgetäuschten Extraktions- oder Suchergebnisse.

## Entwicklung und Checks

Python 3.13 (mindestens 3.12), Node 20.19+ oder 22+ und npm verwenden.
Lockdateien wurden mit Python 3.13 erstellt.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.lock
.venv/bin/pip install --no-deps -e backend
npm ci --prefix frontend

.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm run build --prefix frontend
npm run format:check --prefix frontend
```

Integrationstests verwenden eine **separate** PostgreSQL-Datenbank auf Port 55432.
Die Test-Fixture leert deren Dokumenttabellen vor jedem Test. Nie die
Anwendungsdatenbank als Testziel verwenden; der Datenbankname muss auf `_test` enden.

```sh
docker compose -f compose.test.yaml up -d --wait
TEST_DATABASE_URL=postgresql+psycopg://traystack:traystack_test@127.0.0.1:55432/traystack_test .venv/bin/pytest backend/tests -q
docker compose -f compose.test.yaml down
```

Ohne `TEST_DATABASE_URL` werden Datenbanktests ausdrücklich übersprungen.
Die isolierte Testdatenbank liegt im flüchtigen Speicher; ihre Daten gehen beim
Entfernen des Testcontainers verloren. Eine frische Instanz testet die Migration
von einer leeren Datenbank. Storage-Tests benötigen keine Datenbank.

Browser-Test gegen den laufenden Stack (legt einen synthetischen Datensatz an):

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

Alternativ mit vorhandenem Chrome:

```sh
cd frontend
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm run test:e2e
```

Für Frontend-Entwicklung `npm run dev --prefix frontend`; Vite leitet API-Anfragen
an `localhost:8000` weiter. Für Backend-Entwicklung `DATABASE_URL` und
`STORAGE_PATH` als Umgebungsvariablen setzen, Migrationen mit
`.venv/bin/alembic -c backend/alembic.ini upgrade head` ausführen und
`.venv/bin/uvicorn traystack.main:app --reload` starten. Keine SQLite-Ersatzdatenbank.

Fixtures regenerieren: `.venv/bin/python scripts/generate_fixtures.py`.
Abhängigkeiten aktualisieren: mit `pip-tools` aus `backend/pyproject.toml`
beide Python-Lockdateien neu erzeugen; Frontend-Lockdatei mit npm pflegen.

## Architektur und Grenzen

FastAPI + SQLAlchemy/Alembic + PostgreSQL speichern die Beziehungen und Metadaten.
Ein lokaler, nach SHA-256 adressierter Dateispeicher bewahrt die Originalbytes.
React/TypeScript zeigt ausschließlich Daten der API; Nginx liefert den gebauten
Client und leitet API-Aufrufe weiter.

[Architektur](docs/architecture.md), [Entscheidungen](docs/decisions.md) und
[Demo/Prüfstand](docs/demo.md) beschreiben den aktuellen Stand. Die
[Implementierungsanleitung](TrayStack_Codex_Instructions.md) enthält den weiteren
Plan: Worker und ehrliche Qualitätsbewertung, Volltextsuche und Präsentation.

Dieser lokale Prototyp hat noch keine Anmeldung, Mandantentrennung oder
Vertragsprüfung. Für die Demo synthetische Daten verwenden. Ein vorgemerkter
Prüfbedarf ist noch keine OCR-Bewertung und keine abgeschlossene manuelle Prüfung.
