# Entscheidungen

- **Schmaler erster Durchstich:** Ein kombinierter Upload legt Dokument, Revision 1
  und Original an. Weitere Revisionen und Repräsentationen bleiben im Datenmodell
  möglich; ihre Schreib-APIs und komfortable Verwaltung folgen später.
- **PostgreSQL von Anfang an:** JSONB, Fremdschlüssel und echte Migrationen werden
  gegen PostgreSQL geprüft. `pg_trgm` und Suchsegmente werden erst mit der optionalen
  Fuzzy-Suche hinzugefügt.
- **Originalbytes und Herkunft:** Dateiname ist ein bereinigtes Anzeigefeld,
  niemals ein Dateipfad. SHA-256 adressiert Inhalt, die Artefakt-ID dessen konkrete
  Herkunft. Inhaltsgleiche Uploads werden nicht als dasselbe Dokument behandelt.
- **Lokale Ablage:** Der API-Container läuft ohne root-Rechte. Ein benanntes Volume
  hält Originalbytes; ein späterer Blob-Storage-Adapter kann die Ablage ersetzen.
  Die tatsächliche Storage-Schnittstelle bietet Stream-/Byte-Ablage und Abruf.
- **Ehrlicher Status:** Ein erfolgreicher Upload ist keine erfolgreiche Extraktion.
  Alle Revisionen sind aktuell `not_processed`. Manuelle Prüfung kann vorgemerkt
  werden; daraus wird kein Qualitätssiegel abgeleitet.
- **Lokale API-Dokumentation:** Swagger-JavaScript und CSS kommen aus einer
  installierten Abhängigkeit statt aus einem CDN. Der Core braucht nach dem Build
  keine externen Dienste.
- **Suchprinzip für die nächsten Meilensteine:** Exact/normalized prüfen den ganzen
  ausgewählten Text. Fehlende oder fragwürdige Extraktion wird unverifizierbar;
  ein Treffer wird mit Quelle belegt. Fuzzy und semantische Ähnlichkeit sind
  getrennte spätere Funktionen und keine Beweise für Abwesenheit.
