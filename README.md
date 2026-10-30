# TrayStack

Lokaler Prototyp für nachvollziehbare Vertragsablage und Volltextsuche.
**Meilensteine 1–4 sind umgesetzt:** PDF/JPEG/PNG und UTF-8-TXT/HTML hochladen, Originalbytes
herunterladen und Dokumente im Hintergrund auslesen. Ein eigener Worker erzeugt
Seitentext, strukturierte JSON-Daten und Markdown. Oberfläche und API zeigen
Jobstatus, Seitenabdeckung, Qualitätswarnungen und die Herkunft des ausgewählten
Textes. Exakte und normalisierte Volltextsuche liefern Fundstellen, negative
Ergebnisse im vollständig verarbeiteten Text und getrennte unverifizierbare Dokumente.
Eine [18-Minuten-Präsentation](docs/presentation.md) mit Demo, vorgeschlagener
Azure-Architektur, Microsoft-Vergleich und Nutzerpilot ergänzt den lokalen Core.
Die App-Oberfläche ist auf Englisch. Datumsanzeigen verwenden englische Monatsnamen
und das 24-Stunden-Format in der lokalen Zeitzone des Browsers. Dokumenttitel,
Metadaten und Vertragsinhalte bleiben in ihrer ursprünglichen Sprache erhalten.
Der [Daten- und Evaluationsunterbau](docs/data-evaluation.md) ergänzt lokale
Importwerkzeuge und 300 reproduzierbare Handschrift-Simulationen mit Ground Truth.
Die [drei Bildbeispiele](examples/synthetic-handwriting/samples/manifest.json)
können direkt in der App geprüft werden; das vollständige Bildset wird lokal erzeugt.

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

PostgreSQL, Migration, API, Worker und Webserver starten in der richtigen Reihenfolge.
Die Migration endet nach erfolgreicher Ausführung mit Exit-Code 0. Daten und
Originaldateien liegen in benannten Docker-Volumes. `docker compose down` stoppt
den Stack und erhält die Volumes.

Die Standardwerte funktionieren ohne `.env`. Für Anpassungen `.env.example`
nach `.env` kopieren. `WEB_PORT`, `API_PORT` und `UPLOAD_MAX_BYTES` sind konfigurierbar.
Der Webserver begrenzt den gesamten Request zusätzlich auf 26 MiB; für höhere
Dateilimits auch `frontend/nginx.conf` anpassen. Die Datenbank wird nicht zum Host
veröffentlicht; API und Oberfläche sind an Loopback gebunden. Die Zugangsdaten
sind ausschließlich lokale Demo-Standardwerte.

## Demo in fünf Minuten

1. Oberfläche öffnen und einen Titel eingeben.
2. `examples/synthetic-contracts/A-confidentiality.pdf` auswählen und speichern.
3. Dokumentdetails zeigen Dokument-, Revisions- und Artefakt-ID, Dateityp, Größe und SHA-256.
4. **Download original** wählen und mit der Eingabedatei vergleichen.
5. In den Dokumentdetails **Start processing** wählen. Der Jobstatus aktualisiert sich automatisch.
6. Seitenabdeckung und Qualität getrennt ansehen; **View page text** öffnen.
7. JSON-/Markdown-Artefakte in der Textvorschau ansehen oder herunterladen.
8. `D-delivery.pdf` als Beispiel ohne Zielpassage verarbeiten. `P-printed-scan.jpg`
   hochladen und echte OCR durchführen. Bei `E-difficult-scan.jpg`
   **Manual review required** setzen: Der Eintrag bleibt auch nach Verarbeitung
   in der Prüfgruppe. Die Vormerkung lässt sich nicht durch Neuverarbeitung beseitigen.
9. **Reprocess** erzeugt neue Artefakte und wählt deren Textbestand aus.
   Frühere Artefakte bleiben erhalten. Fehlgeschlagene Läufe lassen sich als neue
   Läufe wiederholen; der bisher ausgewählte Text bleibt bei Fehlschlag unverändert.

10. Oben die Vertraulichkeitspassage eingeben und **Run search** wählen.
    Zwischen **Contains the passage** und **Not found in extracted text**
    wechseln. Die Prüfgruppe der Suche bleibt separat; Treffer öffnen die Quellseite.

Die [Demo-Dateien](examples/synthetic-contracts/README.md) sind synthetisch. Ihre
Hashwerte und Sucherwartungen stehen im Manifest. Es gibt keine
vorgetäuschten Extraktions- oder Suchergebnisse.

Die vier Beispiele lassen sich auch automatisch über die echte API prüfen und
für die Präsentation vorbereiten (Python 3.12+, keine zusätzlichen Pakete):

```sh
python3 scripts/demo_smoke.py
```

Das Skript legt pro Aufruf vier neue synthetische Dokumente an, prüft
Originalbytes, echte Verarbeitung, Ableitungen und Suchergebnisse. Es löscht keine
Daten. Es erwartet einen laufenden Worker und meldet bei Fehlern einen Exit-Code
ungleich null. Bereits angelegte Dokumente bleiben bei Abbruch erhalten.
Den [isolierten Demo-Aufbau](docs/demo.md#frischer-prüf-stack) verwenden, um
Präsentation und Tests vom bisherigen Datenbestand zu trennen.

## Entwicklung und Checks

Python 3.13 (mindestens 3.12), Node 20.19+ oder 22+ und npm verwenden.
Lockdateien wurden mit Python 3.13 erstellt. Für lokale OCR-Tests muss Tesseract
mit englischem Sprachpaket installiert sein, z. B. unter Debian/Ubuntu mit
`sudo apt-get install tesseract-ocr tesseract-ocr-eng`. Die Docker-Images bringen
Englisch und Deutsch bereits mit; `OCR_LANGUAGES=eng+deu` aktiviert beide.
Ein OCR-Aufruf hat standardmäßig 30 Sekunden Zeit, ein Lauf maximal 100 Seiten.
Parameter und tatsächlich verwendete Engine-Versionen werden am Lauf festgehalten.

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

Browser-Tests gegen den laufenden Stack (legen synthetische Datensätze an):

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
`.venv/bin/uvicorn traystack.main:app --reload` starten. Zusätzlich mit denselben
DB-/Storage-Einstellungen `.venv/bin/python -m traystack.worker` in einem zweiten
Terminal starten. Keine SQLite-Ersatzdatenbank.

Fixtures regenerieren: `.venv/bin/python scripts/generate_fixtures.py`.
Abhängigkeiten aktualisieren: mit `pip-tools` aus `backend/pyproject.toml`
beide Python-Lockdateien neu erzeugen; Frontend-Lockdatei mit npm pflegen.

## Architektur und Grenzen

FastAPI + SQLAlchemy/Alembic + PostgreSQL speichern die Beziehungen und Metadaten.
Ein lokaler, nach SHA-256 adressierter Dateispeicher bewahrt die Originalbytes.
React/TypeScript zeigt ausschließlich Daten der API; Nginx liefert den gebauten
Client und leitet API-Aufrufe weiter.

[Architektur](docs/architecture.md), [Entscheidungen](docs/decisions.md) und
[Demo/Prüfstand](docs/demo.md) beschreiben den aktuellen Stand.
[Präsentation](docs/presentation.md) und [Produktionskonzept](docs/production.md)
trennen gelieferte Funktionen von Azure-Vorschlag, Technologieevaluation und Pilot.
Die [Implementierungsanleitung](TrayStack_Codex_Instructions.md) enthält den
weiteren Plan: Fuzzy-Suche und komfortable Revisionsverwaltung sind optionale
Erweiterungen nach dem abgeschlossenen Core.
Der [Suchvertrag](docs/search.md) erklärt Literalität, Qualität, Pagination,
Seitenoffsets und konsistente Momentaufnahmen.

Dieser lokale Prototyp hat noch keine Anmeldung, Mandantentrennung oder
Vertragsprüfung. Für die Demo synthetische Daten verwenden. Ein vorgemerkter
Prüfbedarf ist keine abgeschlossene manuelle Prüfung. Vollständige Verarbeitung
und hohe OCR-Wortscores garantieren keine korrekte Erkennung. Handschrift muss
am Original geprüft werden. Leere oder fehlerhafte Seiten gelten konservativ als
nicht vollständig ausgelesen. „Nicht gefunden“ ist ausdrücklich eine Aussage
über den ausgewählten extrahierten Text, keine juristische Klauselbewertung.

## Worker nach einem Abbruch wieder freigeben

Es gibt bewusst keine automatischen Wiederholungen oder zeitbasierten Lease-
Übernahmen. Bei hartem Prozessabbruch bleibt ein laufender Job als `running`
stehen und sperrt weitere Läufe derselben Revision. **Zuerst alle Worker stoppen**,
dann unterbrochene Läufe als fehlgeschlagen markieren:

```sh
docker compose stop worker
docker compose run --rm --no-deps worker python -m traystack.worker --recover-running
docker compose start worker
```

Anschließend in der Oberfläche den fehlgeschlagenen Job als neuen Lauf wiederholen.
Die Wiederherstellung erhält den ausgewählten Text und alle bisherigen Artefakte.
Eine reguläre Worker-Beendigung wartet bis zu 45 Sekunden auf den aktuellen Lauf;
größere OCR-Läufe können länger dauern und benötigen dann diese Wiederherstellung.
