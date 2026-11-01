# TrayStack benutzen

Dieses Handbuch erklärt den aktuellen lokalen Prototyp aus Anwendersicht. Die
Oberfläche ist auf Englisch; die englischen Beschriftungen stehen deshalb auch
in den folgenden Arbeitsschritten. Dokumente und Suchausdrücke dürfen auf Deutsch
oder in anderen Sprachen vorliegen. Stand: 1. November 2026.

## Wegweiser

1. [App starten und beenden](#1-app-starten-und-beenden)
2. [Komponenten und Begriffe](#2-komponenten-und-begriffe)
3. [Dokument hochladen](#3-dokument-hochladen)
4. [Verarbeitung starten und Ergebnisse verstehen](#4-verarbeitung-starten-und-ergebnisse-verstehen)
5. [Unterschiede zwischen den Dateitypen](#5-unterschiede-zwischen-den-dateitypen)
6. [Dokumente finden, die eine Phrase enthalten](#6-dokumente-finden-die-eine-phrase-enthalten)
7. [Dokumente finden, in denen eine Phrase nicht gefunden wurde](#7-dokumente-finden-in-denen-eine-phrase-nicht-gefunden-wurde)
8. [Ähnliche Formulierungen finden und prüfen](#8-ähnliche-formulierungen-finden-und-prüfen)
9. [Suchläufe wieder öffnen und Ergebnisse exportieren](#9-suchläufe-wieder-öffnen-und-ergebnisse-exportieren)
10. [Probleme und Grenzen](#10-probleme-und-grenzen)

## 1. App starten und beenden

### Voraussetzungen

Benötigt werden der ausgecheckte TrayStack-Quellcode, Docker mit Compose v2 und
Zugriff auf den Docker-Daemon. Python, Node und Tesseract müssen für den normalen
Docker-Betrieb nicht separat auf dem Rechner installiert werden.

Beim ersten Build braucht Docker Internetzugriff für Container-Images,
Abhängigkeiten und das lokale Sprachmodell einschließlich Tokenizer (etwa
135 MB). Die fertig gebaute App verarbeitet Dokumente und berechnet Embeddings
lokal, ohne Cloud-Dienst oder API-Schlüssel.

### Start

Im Terminal in das Projektverzeichnis wechseln und starten:

```sh
cd /home/oliver/git/traystack
docker compose up -d --build --wait
```

Auf einem anderen Rechner den Pfad entsprechend ändern. Danach öffnen:

| Adresse | Zweck |
| --- | --- |
| <http://localhost:8080> | Die eigentliche App |
| <http://localhost:8080/docs> | Interaktive Dokumentation der REST-API |
| <http://localhost:8000/api/health> | Prüfung, ob API, Datenbank und Dateispeicher erreichbar sind |

Der erste Build dauert länger. Für den Zustand der Dienste und Fehlermeldungen:

```sh
docker compose ps -a
docker compose logs --tail=100 api worker migrate
```

Der Dienst `migrate` führt die Datenbankmigrationen aus und beendet sich danach
regulär mit Exit-Code 0. Er muss nicht dauerhaft laufen. Für weitere Starts ohne
Quellcodeänderungen reicht normalerweise `docker compose up -d --wait`.

### Einstellungen und Sprache der OCR

Die Standardwerte funktionieren ohne `.env`. Für Anpassungen `.env.example` nach
`.env` kopieren und die gewünschten Werte ändern. Beispielsweise:

```dotenv
OCR_LANGUAGES=eng+deu
```

Damit verwendet OCR Englisch und Deutsch. Die Sprachpakete sind im Container
bereits installiert; standardmäßig ist nur Englisch aktiviert. Anschließend
`docker compose up -d --wait` ausführen, damit die geänderten Einstellungen in die
Container übernommen werden. Bereits gespeicherte Texte werden dadurch nicht neu
berechnet: Die betreffenden Dokumente anschließend mit **Reprocess** verarbeiten.
Die OCR-Sprache ist unabhängig von der englischen Sprache der Oberfläche.

`WEB_PORT` und `API_PORT` ändern bei Bedarf die lokalen Ports. Bei einem anderen
`WEB_PORT` die Oberfläche entsprechend unter diesem Port öffnen.

### Beenden und Daten behalten

```sh
docker compose down
```

Das stoppt die Dienste. Dokumente, Suchläufe und Prüfentscheidungen bleiben in
Docker-Volumes erhalten und stehen beim nächsten Start wieder zur Verfügung.
**`docker compose down -v` löscht dagegen die zugehörigen Daten-Volumes.** Diesen
Befehl nicht verwenden, wenn die gespeicherten Daten erhalten bleiben sollen.
Für eine vollständige Sicherung werden Datenbank und Dateispeicher gemeinsam
benötigt; ein Ergebnisexport ersetzt diese Sicherung nicht.

## 2. Komponenten und Begriffe

### Welche Komponenten laufen?

| Komponente | Aufgabe |
| --- | --- |
| Weboberfläche: React/TypeScript | Uploads, Dokumentdetails, Suche, Prüfung und Export bedienen |
| Webserver: Nginx | Liefert die Oberfläche aus und leitet deren API-Aufrufe an FastAPI weiter |
| API: Python/FastAPI | Prüft Eingaben, speichert Metadaten, legt Verarbeitungsaufträge an, sucht und speichert Entscheidungen/Suchläufe |
| Worker | Holt wartende Aufträge ab, extrahiert Text oder führt OCR aus und speichert die Ergebnisse |
| PostgreSQL | Speichert Dokument-/Revisionsbeziehungen, Aufträge, Suchtexte, Qualitätsangaben, Suchläufe und Prüfentscheidungen |
| Dateispeicher | Bewahrt unveränderte Originaldateien und abgeleitete Dateien in einem Docker-Volume auf |
| Migrationsdienst | Passt beim Start das Datenbankschema an den aktuellen Programmstand an |
| Lokales Embedding-Modell | Vergleicht bei aktivierter semantischer Suche den Suchausdruck mit bereits textuell gefundenen Passagen; ist kein eigener Compose-Dienst |

Im Worker liest PyMuPDF PDF-Dateien; Tesseract übernimmt die OCR von
Seitenbildern. Die API verwendet einen Zeichenvergleich für textuelle Ähnlichkeit
und optional das lokale Embedding-Modell für den semantischen Vergleich.

Der Worker arbeitet unabhängig vom Browser. Ein bereits angenommener Auftrag
kann weiterlaufen, wenn das Browserfenster geschlossen wird, solange die Dienste
laufen. Ein Upload allein löst in der Oberfläche noch keine Verarbeitung aus.

### Dokument, Revision, Datei und Verarbeitungslauf

- **Dokument**: der logische Vertrag mit Titel.
- **Revision**: ein bestimmter inhaltlicher Stand dieses Vertrags. Ein geänderter
  Vertrag gehört in eine neue Revision.
- **Artefakt/Dateidarstellung**: eine Datei zu einer Revision, etwa das Original
  oder daraus erzeugtes JSON und Markdown. Ein zusätzlicher Scan desselben
  Vertragsstands ist keine neue inhaltliche Revision.
- **Verarbeitungslauf/Job**: ein Versuch, eine bestimmte Quelldatei auszulesen.
  Erneute OCR erzeugt einen neuen Lauf und neue Ableitungen.

Der normale Upload legt ein Dokument mit erster Revision und Originaldatei an.
Ein weiterer Upload über **Add a contract** erzeugt ein weiteres Dokument; die
App führt Dateien nicht automatisch zu Revisionen zusammen. Die komfortable
Anlage weiterer Revisionen und Dateidarstellungen direkt in der Oberfläche ist
noch keine gelieferte Funktion. Die Unterscheidung ist im Datenmodell vorhanden.

## 3. Dokument hochladen

1. Die Oberfläche öffnen und **Add a contract** suchen.
2. Unter **Title** einen aussagekräftigen Titel eingeben, beispielsweise
   `Liefervertrag – Altname GmbH – 2022`.
3. Unter **Original file** eine Datei auswählen. Unterstützt werden PDF, JPEG,
   PNG sowie UTF-8-kodierte TXT- und HTML-Dateien.
4. Bei Handschrift oder schwer lesbaren Scans **Manual review required** setzen.
5. **Save document** wählen.

Standardmäßig sind Dateien bis 25 MiB erlaubt. Die App prüft die Datei; eine bloß
umbenannte, beschädigte oder nicht unterstützte Datei kann abgelehnt werden.
DOCX, E-Mail-Dateien und ZIP-Archive gehören nicht zu den unterstützten Uploads.

### Was passiert unmittelbar danach?

Die API speichert die Originalbytes unverändert, berechnet einen SHA-256-Prüfwert
und legt Dokument, erste Revision und Original-Artefakt an. Der Eintrag erscheint
in der Dokumentliste; die Details werden geöffnet. Dort lassen sich unter anderem
Dateityp, Größe, IDs und Prüfwert ansehen. **Download original** lädt dieselben
Originalbytes wieder herunter.

Der Zustand ist zunächst **Not processed** bzw. **Not processed yet**. Die Datei
ist abgelegt, aber ihr Inhalt steht noch nicht als verarbeiteter Suchtext bereit.
Ein solches Dokument gilt bei der Suche nicht als nachweislich ohne Zielphrase.

**Manual review required** ist eine dauerhafte Prüfvormerkung für die Quelle.
Ein erfolgreicher OCR-Lauf hebt sie nicht auf. Auch ein späteres **Keep** für eine
Fundstelle ist keine Freigabe der Extraktionsqualität.

## 4. Verarbeitung starten und Ergebnisse verstehen

### Verarbeitung auslösen

1. Das Dokument in der Liste anklicken.
2. Unter **Processing source** die Originaldatei auswählen. Bei genau einer
   Quelle ist sie üblicherweise bereits ausgewählt.
3. Falls erforderlich **Manual review required** setzen.
4. **Start processing** wählen.
5. Den Jobstatus beobachten. Er aktualisiert sich automatisch.

| Anzeige | Bedeutung |
| --- | --- |
| **Queued for processing** | Auftrag wartet auf den Worker |
| **Processing** | Worker liest die Quelle gerade aus |
| **Processed** | Verarbeitungslauf wurde abgeschlossen; Qualität und Seitenabdeckung zusätzlich prüfen |
| **Processing failed** | Auftrag ist fehlgeschlagen; Fehlerdetails ansehen |

### Was macht der Worker?

Er liest die Quelldatei, extrahiert Text oder führt OCR aus und bildet daraus
Seitentexte sowie einen zusammenhängenden Suchtext. Zusätzlich entsteht eine
normalisierte Fassung für die Suche. Der Lauf hält Methode, Versionen,
Quellenbezug, Seitenabdeckung und Qualitätswarnungen fest. Als abgeleitete Dateien
werden strukturierte Extraktionsdaten in JSON und extrahierter Text in Markdown
bereitgestellt. Das Original wird dabei nicht umgeschrieben.

Mit **View page text** den Seitentext prüfen. Die Seitenwahl erlaubt den Wechsel
zwischen den ausgelesenen Seiten. Für JSON-/Markdown-Artefakte stehen **Text
preview** (bei geeigneter Dateigröße) und **Download file** zur Verfügung. Diese
Textansichten sind keine originalgetreue PDF- oder Bilddarstellung. Für den
Vergleich mit dem tatsächlichen Vertragsbild **Download original** verwenden.

### Drei unterschiedliche Aussagen auseinanderhalten

| Ebene | Beispiele | Was daraus folgt |
| --- | --- | --- |
| Auftrag | **Processed**, **Processing failed** | Ob der Verarbeitungslauf abgeschlossen wurde |
| Abdeckung | **Fully processed**, **Partially processed**, **Text unavailable** | Ob alle Seiten verarbeitet wurden oder Text fehlt |
| Qualität | **No known quality issue**, **Manual review required**, **Quality not assessed** | Ob bekannte Qualitätsprobleme oder Prüfbedarf vorliegen |

**Processed** allein bedeutet nicht, dass der Vertrag fehlerfrei erkannt wurde.
Auch **No known quality issue** ist keine Garantie vollständiger inhaltlicher
Richtigkeit. OCR-Wortscores sind Hinweise der Erkennungssoftware, keine
Wahrscheinlichkeit juristischer Korrektheit. Leere oder nicht lesbare Seiten
werden vorsichtig als problematisch behandelt.

### Erneut verarbeiten und Fehler behandeln

**Reprocess** erzeugt einen neuen Lauf. Frühere Artefakte bleiben erhalten; ein
veröffentlichter neuer Textbestand ersetzt den aktuell ausgewählten Suchtext der
Revision. Schlägt die erneute Verarbeitung fehl, bleibt ein zuvor ausgewählter
Textbestand erhalten. Suchergebnisse zeigen entsprechende Laufwarnungen.

Fehlgeschlagene Aufträge können über **Retry as a new run** erneut eingereicht
werden. Fehlerursachen wie beschädigte Dateien oder ungeeignete Scanqualität
verschwinden durch Wiederholen nicht automatisch. Gespeicherte Suchläufe behalten
auch nach erfolgreicher Neuverarbeitung ihre damaligen Fundstellen und Quelltexte.

## 5. Unterschiede zwischen den Dateitypen

| Eingabe | Verarbeitung | Worauf achten? |
| --- | --- | --- |
| Digitales PDF mit brauchbarem eingebettetem Text und ohne Bildinhalte auf der Seite | Text direkt aus dem PDF auslesen | Lesereihenfolge, Sonderzeichen und ungewöhnliche Layouts prüfen |
| Gescanntes PDF oder PDF-Seite mit Bildinhalten bzw. zu wenig eingebettetem Text | Ganze Seite als Bild rendern und mit Tesseract OCR auslesen | Auch Mischseiten mit Text und Bildern werden vorsichtig über OCR verarbeitet; Erkennungsfehler sind möglich |
| JPEG/PNG | Bild mit OCR auslesen; ein Bild entspricht einer Seite | Auflösung, Schräglage, Unschärfe und Handschrift beeinflussen das Ergebnis |
| UTF-8-TXT | Text direkt lesen, ohne OCR | Logische Textseite statt gedruckter Seitenangabe |
| UTF-8-HTML | Text aus HTML gewinnen, ohne Skripte auszuführen oder externe Inhalte nachzuladen | Bildinhalt und Darstellung sind damit nicht vollständig geprüft; HTML erhält Prüfbedarf |

Ein mehrseitiges PDF wird seitenweise beurteilt; nicht jede Seite muss dieselbe
Extraktionsmethode haben. JPEG ist nicht automatisch Handschrift: Ein Foto einer
gedruckten Seite wird ebenfalls per OCR verarbeitet.

Handschrift wird mit demselben OCR-Werkzeug versucht. Es gibt keine Garantie,
dass echte handschriftliche Verträge zuverlässig erkannt werden. Deshalb solche
Dateien ausdrücklich vormerken und das Original prüfen. Die synthetischen
Handschriftbeispiele im Repository sind Testmaterial, kein Nachweis allgemeiner
Handschrifterkennung.

Standardgrenzen sind unter anderem 100 Seiten pro Lauf und 30 Sekunden pro
OCR-Aufruf. Geschützte/verschlüsselte PDFs oder nicht unterstützte Bildvarianten
können fehlschlagen. Fehler und fehlende Seiten werden nicht als gelesener Inhalt
erfunden. Die konkreten Verarbeitungsdetails sind in den Laufdaten nachvollziehbar.

## 6. Dokumente finden, die eine Phrase enthalten

### Beispiel: alter Firmenname

Gesucht werden Verträge, in deren extrahiertem Text `Altname GmbH` vorkommt.

1. Die betreffenden Dokumente hochladen und verarbeiten.
2. Oben **Literal search** wählen.
3. Unter **Text passage** `Altname GmbH` eingeben.
4. **Search mode: Normalized** wählen.
5. **Find documents: Contains the passage** wählen.
6. **Run search** drücken.

Die Suche betrachtet die neueste Revision jedes Dokuments und deren ausgewählten
Textbestand. Das Öffnen eines Dokuments schränkt diese Literal-Suche nicht auf
jenes Dokument ein. Die sichtbaren Seiten der Dokumentliste begrenzen den
Suchbestand ebenfalls nicht.

### Exact oder Normalized?

**Exact** sucht eine wörtliche Zeichenfolge im extrahierten Text, einschließlich
Groß-/Kleinschreibung, Leerzeichen und Zeilenumbrüchen.

**Normalized** vereinheitlicht Unicode-Schreibformen, Groß-/Kleinschreibung und
zusammenhängende Leerraumzeichen. Dadurch kann `ALTNAME` gefolgt von einem
Zeilenumbruch und `GmbH` zur Eingabe `Altname GmbH` passen. Unicode-Casefolding kann
auch `ß` zu `ss` abbilden.

Zahlen, Satzzeichen, Bindestriche und Verneinungen werden nicht entfernt.
`Altname-GmbH` ist deshalb nicht dasselbe wie `Altname GmbH`. Trennstriche am
Zeilenende werden nicht automatisch als Silbentrennung aufgelöst. Beide Modi
suchen Textfolgen, keine Firmenidentitäten, Wortvarianten oder juristischen
Bedeutungen; es handelt sich auch nicht um eine Regex-Suche.

### Ergebnisse ansehen

Unter **Documents found** stehen die gefundenen Dokumente mit einer Fundstelle,
Kontext und Quellen-/Qualitätsangaben. Über den angebotenen Seiten- oder
Dokumentaufruf den Text in den Dokumentdetails öffnen. Bei mehreren Ergebnisseiten
weiterblättern. Die Literal-Suche liefert Dokumenttreffer und eine Belegstelle,
keine vollständige Liste aller Vorkommen je Dokument.

Eine positive Fundstelle kann auch aus einem nur teilweise ausgelesenen oder
qualitativ zweifelhaften Dokument stammen: Die Phrase wurde im vorhandenen Text
gefunden, die Warnung bleibt trotzdem wichtig. Die separate Gruppe
**Unverifiable** betrifft Dokumente ohne belastbaren positiven oder negativen
Nachweis für diese Suche; sie ist keine Liste bestätigter Nichttreffer.

## 7. Dokumente finden, in denen eine Phrase nicht gefunden wurde

### Beispiel: bestimmte Klauselformulierung

Gesucht werden Verträge, in deren ausgelesenem Text die folgende Formulierung
nicht vorkommt:

> The receiving party shall not disclose confidential information

1. **Literal search** wählen.
2. Die vollständige Zielphrase unter **Text passage** eingeben.
3. **Normalized** wählen, wenn Großschreibung und Zeilenumbrüche nicht relevant
   sein sollen; andernfalls **Exact** verwenden.
4. Unter **Find documents** **Not found in extracted text** auswählen.
5. **Run search** wählen.
6. Sowohl die negativen Ergebnisse als auch **Unverifiable** prüfen.

Die Gruppen bedeuten:

| Ergebnis | Bedeutung | Sinnvoller nächster Schritt |
| --- | --- | --- |
| **Not found in extracted text** | Die Phrase wurde im ausgewählten, vollständig verarbeiteten Text ohne bekannten Qualitätsmangel oder Prüfvormerkung nicht gefunden | Original und mögliche alternative Formulierungen prüfen |
| **Unverifiable** | Ein negativer Befund ist nicht belastbar, etwa weil Verarbeitung, Text, Seiten oder Qualität fehlen bzw. Prüfbedarf besteht | Verarbeiten, Fehler klären, bessere Quelle verwenden oder manuell prüfen |
| Phrase tatsächlich gefunden | Gehört nicht in die Liste negativer Ergebnisse | Für die konkrete Belegstelle auf **Contains the passage** umschalten |

**„Diese Phrase wurde nicht gefunden“ bedeutet nicht „diese rechtliche Klausel
fehlt“.** Eine inhaltlich ähnliche Klausel kann anders formuliert sein. Auch ein
als vollständig eingestufter OCR-Text kann Erkennungsfehler enthalten. Für eine
vertragliche Entscheidung das Original und alternative Formulierungen prüfen.

Eine neue, noch unverarbeitete Revision darf nicht durch den sauberen Text einer
älteren Revision als erfolgreich geprüft erscheinen. Bei erneuter Verarbeitung
innerhalb derselben Revision kann dagegen der bisher ausgewählte Text weiterhin
verwendet werden, solange kein neuer Text veröffentlicht wurde; Hinweise auf
wartende oder fehlgeschlagene neuere Läufe beachten.

Die Abwesenheitssuche hat keine semantische Schwelle. Aus dem Ausbleiben eines
ähnlichen oder semantischen Treffers wird kein negativer Klauselnachweis erzeugt.

## 8. Ähnliche Formulierungen finden und prüfen

### Wann diesen Ablauf benutzen?

**Similar passages** eignet sich, wenn Varianten, OCR-Fehler oder leicht geänderte
Formulierungen gefunden und einzeln geprüft werden sollen. Beispielsweise kann
`Altname GrnbH` ein OCR-Fehler für `Altname GmbH` sein. Dieser Ablauf findet positive
Kandidaten; er ersetzt nicht die Abwesenheitssuche.

1. **Similar passages** öffnen und gegebenenfalls **Search parameters** aufklappen.
2. Einen **Search name** optional vergeben.
3. **Text passage** und **Text comparison mode** einstellen.
4. **Minimum textual match** festlegen. Beispielsweise mit 85 experimentieren,
   Ergebnisse prüfen und die Schwelle anpassen; 85 ist kein allgemeiner sicherer
   Grenzwert. 100 verlangt identischen Text im gewählten Vergleichsmodus.
5. Falls gewünscht **Compare meaning with local embeddings** aktivieren und
   **Minimum semantic match** einstellen.
6. **Review status** zunächst auf **All review states** belassen.
7. Optional ein Dokument in der Bibliothek öffnen und **Search only the open
   document** aktivieren.
8. **Find passages** wählen.

### Was bedeuten die beiden Schwellen?

Die textuelle Suche findet Wortfenster und bewertet ihre Zeichenunterschiede zum
Suchausdruck. Der Score beschreibt Zeichenähnlichkeit, nicht den Anteil gleicher
Wörter. Textuell 0 ist nicht erlaubt. Bei kurzen oder wenig aussagekräftigen
Ausdrücken können bereits relativ hohe Schwellen viele ungeeignete Stellen liefern;
die Oberfläche gibt vom Suchausdruck abhängige Hinweise.

Erst die textuell gefundenen Stellen werden bei aktivierter Semantik mit dem
Suchausdruck verglichen. Das Modell berücksichtigt dabei die gefundene Passage,
nicht den zusätzlich angezeigten Umgebungstext. Beide Mindestschwellen müssen
bestehen. Eine nur sinngleiche Formulierung, die die textuelle Schwelle verfehlt,
wird durch die semantische Stufe nicht zusätzlich gefunden.

- Semantik ausgeschaltet: kein semantischer Vergleich und kein semantischer Score.
- Semantik 0: Scores berechnen und anzeigen, ohne Kandidaten semantisch auszufiltern.
- Semantik zwischen 0 und 100: zusätzlich nach Modellähnlichkeit filtern.
- Semantik 100: nach der Produktregel nur identischen Vergleichstext behalten.

Ein Score von 95 % ist keine 95-prozentige Wahrscheinlichkeit korrekter Bedeutung.
Ein geänderter Firmenname, Betrag oder ein hinzugefügtes „nicht“ kann trotz hoher
Ähnlichkeit entscheidend sein. Deshalb zeigt die App Textunterschiede an. Bei zu
breiten Suchen kann sie kontrolliert abbrechen, ohne eine erfolgreiche Teilliste
anzuzeigen. Dann Ausdruck verlängern, Schwelle erhöhen oder die Auswahl eingrenzen.

### Die Fundstellen durchgehen

Links steht die kompakte Trefferliste, rechts die ausgewählte Fundstelle. Auf
kleinen Bildschirmen stehen beide Bereiche untereinander. Die Detailansicht zeigt
Textscore, gegebenenfalls Semantikscore, Kontext und den textuellen Vergleich mit
der Suchphrase. **View source text** bzw. der Seitenaufruf öffnet den gespeicherten
Quelltext. Für das tatsächliche Seitenbild weiterhin das Original herunterladen.

- **Previous passage / Next passage**: durch die Fundstellen navigieren, auch
  über Dokumentgrenzen hinweg.
- **Next unreviewed**: zur nächsten ungeprüften Stelle im aktuellen Review-Filter;
  bei Bedarf zum Anfang dieses Bereichs zurückspringen.
- In der Trefferliste mit ↑/↓ oder Home/End navigieren. Mit Tab die Schaltflächen
  erreichen und mit Enter/Leertaste bedienen.
- **Search parameters** einklappen, um beim Prüfen mehr Platz zu haben.

### Entscheidungen speichern

| Entscheidung | Bedeutung im Prüfablauf |
| --- | --- |
| **Not reviewed** | Noch keine Entscheidung oder ausdrücklich zurückgesetzt |
| **Keep** | Diese Fundstelle für den gesuchten Ausdruck beibehalten |
| **Dismiss** | Diese Fundstelle für den gesuchten Ausdruck verwerfen |
| **Decide later** | Entscheidung vertagen |
| **Reset review** | Eine bestehende Entscheidung auf ungeprüft zurücksetzen |

Die App bestätigt den gespeicherten Zustand nach erfolgreicher Serverantwort.
**Final decisions** zählt Keep + Dismiss; vertagte und ungeprüfte Stellen bleiben
noch offen. Der Fortschritt bezieht sich auf die gesamte gespeicherte Menge nach
den Ähnlichkeitsschwellen, vor dem Review-Filter.

**Review saved results** filtert bereits gespeicherte Treffer nach aktuellem
Entscheidungszustand. Ändert sich eine Entscheidung so, dass sie nicht mehr in den
Filter passt, verschwindet die Stelle aus dieser Ansicht und die nächste verbleibende
wird ausgewählt. **Refresh reviews** lädt Entscheidungen aus anderen Ansichten
neu; die Auswahl bleibt erhalten, sofern sie noch passt.

Entscheidungen werden lokal gemeinsam genutzt, ohne persönliche Reviewer-Konten.
Bei gleichzeitigen Änderungen verhindert eine Versionsprüfung blindes Überschreiben.
Bei einem Konflikt aktualisieren und die Entscheidung erneut prüfen. Keep oder
Dismiss ändern weder den Vertragsinhalt noch die OCR-Qualität und lösen keine
automatische Änderung von Firmennamen aus.

## 9. Suchläufe wieder öffnen und Ergebnisse exportieren

### Zwei unterschiedliche Arten von Suchergebnissen

| Funktion | Literal search | Similar passages |
| --- | --- | --- |
| Wörtliche Phrase suchen | Ja | Ja, mit textueller Schwelle 100 im jeweiligen Modus |
| Negative Ergebnisse mit Unsicherheitsgruppe | Ja | Nein |
| Mehrere Fundstellen je Dokument einzeln prüfen | Nicht als vollständige Vorkommensliste | Ja |
| Keep / Dismiss / Decide later | Nein | Ja |
| Automatisch dauerhaft gespeicherter Suchlauf | Nein | Ja, bei erfolgreicher Suche |
| CSV-/JSON-Ergebnisexport in der Oberfläche | Nein | Ja |

Wenn die Literal-Suche einen alten Firmennamen findet und anschließend eine
speicherbare Prüfung aller Vorkommen benötigt wird, denselben Ausdruck unter
**Similar passages** mit textueller Schwelle 100 und demselben Modus suchen.
Damit wird keine bereits erfolgte Literal-Suche nachträglich gespeichert, sondern
ein eigener neuer Suchlauf erzeugt. Negative Literal-Ergebnislisten haben derzeit
keine entsprechende Speicher-/Exportfunktion in der Oberfläche.

### Gespeicherten Suchlauf benutzen

Erfolgreiche Suchen unter **Similar passages** speichern automatisch sämtliche
Treffer nach den Ähnlichkeitsschwellen, auch außerhalb sichtbarer Listenbereiche,
samt damaligem Dokumentbestand, Scores und passenden Quelltexten.

- Unter **Saved searches** einen Lauf öffnen oder seine URL mit `search_run` als
  Lesezeichen speichern.
- **Save name** ändert die Bezeichnung, nicht die Treffer.
- Wiederöffnen liest die damaligen Ergebnisse ohne neue Suche oder Embeddings.
- **Run again** erstellt mit den ursprünglichen Kriterien einen neuen verknüpften
  Lauf gegen den aktuellen Bestand. Der alte Lauf bleibt erhalten.
- Für geänderte Kriterien die Suchparameter bearbeiten und **Find passages** wählen.

Später hochgeladene Dokumente und neue OCR-Ergebnisse verändern den alten Lauf
nicht. Seine Prüfentscheidungen bleiben dagegen aktuell bearbeitbar; der Zustand
bei Erfassung ist zusätzlich gespeichert. Neue Verarbeitungsläufe erhalten eigene
Fundstellenidentitäten und übernehmen alte Entscheidungen nicht automatisch.

### Exportieren

1. Den gespeicherten Lauf öffnen und **Export results** aufklappen.
2. **Export review status** auswählen: alle oder nur Keep, Dismiss, Decide later
   bzw. Not reviewed. Dieser Filter ist unabhängig von der Bildschirmansicht.
3. **Download CSV** oder **Download JSON** wählen.

Der Export umfasst alle ausgewählten Treffer des Laufs, nicht nur die sichtbare
Stelle. Aktuelle Prüfentscheidungen werden zu einem einheitlichen Exportzeitpunkt
ermittelt. Suchzeitpunkt und Exportzeitpunkt werden getrennt angegeben.
Unverarbeitbare Dokumente werden unabhängig vom Review-Filter separat mitgeführt.

**CSV** ist für Tabellenkalkulationen gedacht. Die Spalte `row_type` unterscheidet
Zusammenfassungszeile (`summary`), Fundstellen (`passage`) und unverarbeitbare
Dokumente (`unsearchable`). Für eine reine Trefferliste nach `passage` filtern.
Formelähnlicher Text erhält zum Schutz vor Tabellenformeln ein vorangestelltes
Apostroph. **JSON** bewahrt den unveränderten Text, Vergleichsdetails, den
vollständigen damaligen Dokumentbestand und Versions-/Quellenreferenzen.
Originaldateien selbst sind nicht im Ergebnisexport enthalten.

## 10. Probleme und Grenzen

| Beobachtung | Was prüfen oder tun? |
| --- | --- |
| Oberfläche nicht erreichbar | `docker compose ps -a` und Logs ansehen; verwendeten `WEB_PORT` prüfen |
| Webserver liefert nach Austausch des API-Containers 502 | `docker compose restart frontend`, damit Nginx die neue interne API-Adresse auflöst |
| Upload wurde gespeichert, aber Suche findet nichts | Verarbeitung starten; Dateiablage allein erzeugt keinen Suchtext |
| Auftrag bleibt in der Warteschlange | Prüfen, ob der Worker läuft; `docker compose logs --tail=100 worker` ansehen |
| Einzelne Wörter wurden falsch erkannt | Seitentext mit Original vergleichen; bessere Quelle, passende OCR-Sprache und erneute Verarbeitung erwägen |
| Positive Suche liefert nichts | Modus, Schreibweise, Satzzeichen, Trennstriche, Revision und Verarbeitungszustand prüfen; gegebenenfalls Similar passages versuchen |
| Negativsuche liefert weniger Dokumente als erwartet | Gruppe Unverifiable prüfen; diese Dokumente sind keine bestätigten Nichttreffer |
| Zu breite Suche wird abgebrochen | Schwelle erhöhen, Ausdruck präzisieren oder unter Similar passages ein einzelnes Dokument auswählen; es wird keine erfolgreiche Teilliste ausgegeben |
| Nach Neuverarbeitung stehen im gespeicherten Lauf alte Texte | Erwartetes Verhalten: für aktuelle Ergebnisse Run again wählen |
| Bewertung wurde in einer anderen Ansicht verändert | Refresh reviews verwenden und die aktuelle Entscheidung prüfen |

Bei hartem Worker-Abbruch kann ein Job als laufend stehen bleiben. Die sichere
Wiederherstellung erfordert zuerst das Stoppen aller Worker; die genaue Anleitung
steht im [README](../README.md#worker-nach-einem-abbruch-wieder-freigeben).
Nicht einfach parallel weitere Worker zur Übernahme desselben Jobs starten.

Die App ist ein lokaler Prototyp ohne Anmeldung, Mandantentrennung oder vollständiges
Reviewer-Ereignisaudit. Sie verändert Verträge nicht automatisch und bewertet ihre
juristische Gleichwertigkeit nicht. Große Bestände können an die vorhandenen
Suchbudgets stoßen; die aktuelle textuelle Kandidatensuche ist ein begrenzter
Vollscan, kein skalierender Suchindex.

### Zum Ausprobieren und Weiterlesen

Ein kleiner, synthetischer Ablauf ohne eigene Verträge:

1. [A-confidentiality.pdf](../examples/synthetic-contracts/A-confidentiality.pdf)
   und [D-delivery.pdf](../examples/synthetic-contracts/D-delivery.pdf) hochladen
   und jeweils verarbeiten.
2. Mit der Vertraulichkeitsphrase aus Abschnitt 7 unter Literal search einmal
   Contains und einmal Not found in extracted text suchen.
3. [P-printed-scan.jpg](../examples/synthetic-contracts/P-printed-scan.jpg)
   verarbeiten und den OCR-Text mit dem Original vergleichen.
4. Unter Similar passages die Phrase suchen, Fundstellen bewerten, den Suchlauf
   wieder öffnen und die Keep-Treffer exportieren.

Weiterführende technische Verträge: [Literal-Suche](search.md),
[textuelle Suche](textual-search.md), [Semantik](semantic-search.md),
[Prüfansicht](review-workspace.md), [gespeicherte Suchläufe](saved-search-runs.md)
und [Exportformate](search-exports.md).
