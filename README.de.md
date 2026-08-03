# c2pa-scanner

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <a href="README.md">English</a> &middot;
  <img src="docs/flags/de.svg" height="13" alt=""> <b>Deutsch</b>
</p>

---

Erkennt den **C2PA-Herkunftsnachweis** in Bildern und filtert die **KI-generierten**
heraus - damit Du sie nach dem EU AI Act (Art. 50) kennzeichnen kannst.

Es liest den `digitalSourceType` aus einem C2PA-Manifest (z.B. von Adobe / Firefly automatisch
eingebettet) und bewertet jedes Bild: KI-generiert, KI-bearbeitet, andere Herkunft oder keine.

## Wofür dieses Tool gedacht ist - und wofür nicht

> **Dieses Tool prüft Deine eigenen Bilder und Seiten** auf die KI-Kennzeichnung nach dem
> EU AI Act und macht sie rechtssicher - nicht mehr und nicht weniger.
>
> Es ist **ausdrücklich NICHT** dazu gedacht, fremde Webseiten zu durchleuchten, Verstöße zu
> sammeln und daraus Abmahnungen zu basteln. Wer das damit vorhat, ist hier falsch.
>
> Zur Einordnung: Der C2PA-Scan ist nur ein **Indiz** - er findet ausschließlich Bilder mit
> Herkunfts-Manifest (z.B. Adobe / Firefly), niemals alle KI-Bilder. Er ist kein Rechtsgutachten
> und kein Beweis für einen Verstoß. Nutze ihn fair.
>
> **Rechtsgrundlage:** EU AI Act (Verordnung (EU) 2024/1689), insbesondere Artikel 50
> (Transparenzpflichten), gültig ab 2. August 2026.
> Gesetzestext (EUR-Lex): https://eur-lex.europa.eu/eli/reg/2024/1689/oj
> Artikel 50 (lesbar): https://artificialintelligenceact.eu/article/50/

## Last auf dem Zielsystem - bitte lesen

Eine Sitemap zu crawlen heißt, **jede darin aufgeführte Seite und jedes Bild** abzurufen. Ist
Browser-Rendering eingeschaltet, läuft jede Seite zusätzlich durch ein echtes Chromium und damit
an den Zwischenspeichern des Servers vorbei. Auf einer großen Website kommen so schnell mehrere
hundert Requests pro Minute zusammen - genug, um ein Produktivsystem spürbar zu verlangsamen
oder im ungünstigsten Fall an seine Speichergrenze zu bringen.

Der Scanner ist deshalb **von Haus aus gedrosselt**: 60 Requests pro Minute, Seiten, Renderings
und Bilder zusammengezählt. Ändern kannst Du das unter *Einstellungen -> Scan* oder auf der
Kommandozeile:

```bash
c2pa-scanner scan https://www.example.com/sitemap.xml --rate-limit 20   # schonender
c2pa-scanner scan https://www.example.com/sitemap.xml --rate-limit 0    # ohne Limit - Vorsicht
```

Zwei Dinge, die man wissen sollte:

- **"Parallele Requests" ist kein Rate-Limit.** Die Einstellung begrenzt, wie viele Abrufe
  gleichzeitig laufen, nicht wie viele pro Minute rausgehen. Das macht allein das Rate-Limit.
- **Mit Rendering werden nur die Seitenaufrufe gedrosselt.** Was der Browser danach selbst
  nachlädt - Skripte, Schriften, Bilder -, zählt nicht mit. Die tatsächliche Last liegt also
  höher als die eingestellte Zahl.

`robots.txt` wird für die Seiten aus der Sitemap standardmäßig beachtet; gesperrte Seiten werden
übersprungen und im Log ausgewiesen. Bilder werden nicht dagegen geprüft, weil sie oft auf einer
eigenen CDN-Domain mit eigenen Regeln liegen. Für Deine eigenen Systeme lässt sich das in den
Einstellungen abschalten - etwa für ein Testsystem, das pauschal alles sperrt.

## Nutzung auf eigene Verantwortung

Dieses Programm ruft Webseiten automatisiert ab und erzeugt dabei Last auf den Zielsystemen. Je
nach Einstellung kann diese Last die eines normalen Besuchers um ein Vielfaches übersteigen und
die Erreichbarkeit des Zielsystems beeinträchtigen.

Mit der Nutzung erklären Sie:

1. Sie setzen das Programm ausschließlich gegen Systeme ein, für die Ihnen eine ausdrückliche
   Berechtigung des Betreibers vorliegt.
2. Sie tragen die alleinige Verantwortung für den Einsatz, die gewählten Einstellungen und alle
   daraus entstehenden Folgen.
3. Vor einem Lauf gegen ein Produktivsystem prüfen Sie, ob die eingestellten Grenzwerte für
   dieses System angemessen sind.

Die Software wird unentgeltlich und ohne jede Gewährleistung bereitgestellt ("as is"), wie in
Abschnitt 7 der Apache-Lizenz 2.0 beschrieben. Eine Haftung des Autors (Michael Blaess) für
Schäden, die aus der Nutzung entstehen, ist ausgeschlossen, soweit dies gesetzlich zulässig ist.
Unberührt bleibt die Haftung für Vorsatz und grobe Fahrlässigkeit, für Schäden aus der Verletzung
des Lebens, des Körpers oder der Gesundheit sowie nach dem Produkthaftungsgesetz.

Beim ersten Start fragt das Programm diesen Hinweis ab. Auf der Kommandozeile bestätigst Du ihn
einmalig mit `--accept-disclaimer`.

## Verwendung

```bash
# Grafische TUI starten (Standard ohne Befehl)
c2pa-scanner
c2pa-scanner tui https://www.example.com/sitemap.xml

# Sitemap crawlen und alle Bilder auf C2PA-/KI-Herkunft prüfen (auch nur die Domain -
# die Sitemap wird dann automatisch gesucht)
c2pa-scanner scan https://www.example.com/sitemap.xml --accept-disclaimer
c2pa-scanner scan ./sitemap.xml

# Jede Seite zusätzlich in Chromium rendern (findet JS-/Shadow-DOM-Bilder, deutlich schwerer)
c2pa-scanner scan https://www.example.com/sitemap.xml --render --rate-limit 20

# Cookie-Banner stehen lassen, statt sie zu bestätigen (wirkt nur mit --render)
c2pa-scanner scan https://www.example.com/sitemap.xml --render --no-consent

# Signiertes C2PA-Testbild erzeugen (Positiv-Testfall)
c2pa-scanner make-testimage ./test-ki.jpg
c2pa-scanner make-testimage ./test-bearbeitet.jpg --edited
```

## Wie es funktioniert

Die Erkennung ist mehrstufig und bewusst auf wenige Falsch-Positive ausgelegt:

- **C2PA-Manifest** (Primärsignal): die offizielle `c2pa`-Lib liest das signierte Manifest; die
  `digitalSourceType`-Assertion entscheidet das Verdict (`trainedAlgorithmicMedia` = KI-generiert,
  `compositeWithTrainedAlgorithmicMedia` = KI-bearbeitet).
- **XMP/EXIF-`digitalSourceType`** (Zweitsignal): denselben IPTC-Marker liest das Tool auch aus dem
  XMP, wenn kein gültiges C2PA vorhanden ist - so werden Bilder erkannt, die ihre Signatur beim
  Verkleinern verloren, das XMP aber behalten haben.
- **Erzeugendes Tool** (Fallback): fehlt jeder `digitalSourceType`, wird der `Software`- bzw.
  `CreatorTool`-Tag gegen eine kuratierte Liste eindeutiger Generativ-KI-Tools geprüft (Midjourney,
  DALL-E, Stable Diffusion, Adobe Firefly, ...). Mehrdeutige Editoren wie Photoshop oder GIMP zählen
  bewusst NICHT, um Falsch-Positive zu vermeiden.
- **Seiten-Crawl:** aus einer Sitemap werden alle Seiten geladen und die Bild-URLs per Regex über das
  rohe HTML extrahiert - das findet auch Bilder in Web-Component-Attributen/Shadow-DOM, nicht nur
  klassische `<img src>`. Fehlt eine direkte Sitemap-URL, wird sie automatisch gesucht (robots.txt,
  danach übliche Standardpfade). Eine vollständigere Sitemap als die offizielle liefert das
  Schwester-Tool [Sitemap-Tracker](https://github.com/michaelblaess/sitemap-tracker) - dessen
  XML-Ausgabe lädst Du einfach als lokale Datei.
- **Browser-Rendering** (optional, Standard aus): zuschaltbar rendert das Tool jede Seite zusätzlich in
  einem headless Chromium (Playwright) und ergänzt so Bilder, die erst per JavaScript ins (Shadow-)DOM
  geladen werden - als Union mit der Regex-Extraktion.
- **Cookie-Consent** (Standard an): sobald ein Banner geladen ist, wird es automatisch bestätigt
  (Usercentrics, OneTrust, Cookiebot; sonst ein Klick auf den Zustimmen-Knopf im Banner). Das ist
  nötig, weil viele Seiten Bilder erst nach der Zustimmung freigeben - und weil das Banner sonst die
  Seiten-Vorschau verdeckt. Der Manager wird per Skript nachgeladen und ist beim Laden der Seite noch
  nicht da, deshalb wird auf ihn gewartet statt einmal zu raten. Abschaltbar unter
  *Einstellungen -> Scan*, auf der Kommandozeile mit `--no-consent`.

**Grenzen:** Bilder ganz ohne Herkunftssignal (kein C2PA, kein XMP/EXIF) sind nicht als KI erkennbar.
Metadaten lassen sich entfernen - Screenshot, erneutes Speichern, und viele Plattformen strippen sie
beim Upload. Ein Treffer ist ein belastbares Indiz **für** KI; das Fehlen ist **kein** Beweis dagegen.
Jedes Verkleinern/Zuschneiden bricht die C2PA-Signatur - also möglichst das Original prüfen.

### In der TUI

- **Live-Bildvorschau** rechts neben der Trefferliste, mit klickbarem Link zur Fundseite und einem
  Dialog für das rohe C2PA-Manifest.
- **Seiten-Vorschau** (optional): unter dem Bild ein Screenshot der gerenderten Fundseite, zum Bild
  gescrollt - so siehst Du ohne Absprung, ob ein KI-Label auf/am Bild dargestellt wird. Ein
  Cookie-Banner wird dabei vorher weggeklickt (siehe oben).
- **Scan abbrechen** mit `x`: die Taste steht nur während eines Laufs im Fuß. Der Abbruch ist
  kooperativ - angestoßene Abrufe laufen aus, neue kommen keine mehr dazu, und die bis dahin
  gefundenen Bilder bleiben in der Tabelle stehen. Vorher blieb nur `q`, und damit war auch das
  Zwischenergebnis weg.
- **Filter & Sortierung**, Toggle "Nur KI-Bilder", **Export** per Rechtsklick (JSON, JIRA-Tabelle,
  Klartext) und **Testbild-Signierung** als Positiv-Testfall. Die JIRA-Tabelle gibt es in zwei
  Formaten (Einstellungen -> Export): **Markdown** für Jira Cloud (wandelt sich beim Einfügen ins
  Kommentarfeld automatisch in eine echte Tabelle um) und **Wiki Markup** für ältere
  Jira-Server/Data-Center-Instanzen.

- **Zweisprachig**: die Oberfläche gibt es auf Deutsch und Englisch. Beim ersten Start richtet sie
  sich nach Deiner Systemumgebung - Deutsch nur bei nachweislich deutschsprachiger Umgebung, jeder
  andere Fall (auch ein Fehler beim Auslesen) führt zu Englisch. Umschalten kannst Du jederzeit
  unter *Einstellungen -> Sprache*; die Änderung wirkt nach einem Neustart.

### Andere Erkennungsmethoden - und warum (noch) nicht implementiert

Vollständigkeitshalber die Alternativen, die es gibt, aber bewusst NICHT eingebaut sind:

- **Unsichtbare Wasserzeichen** (Google SynthID, Meta, Amazon Titan): robust gegen Bearbeitung, aber
  jedes Verfahren braucht den Detektor seines Anbieters - es gibt keinen offenen, universellen Reader.
  SynthID ist nur über Googles eigenes Portal prüfbar, nicht als Bibliothek. **Grund: nicht
  integrierbar.**
- **ML-Klassifikatoren** ("ist das KI?", z.B. Hive, Sensity, Illuminarty): generatorübergreifend und
  nach Kompression/Verkleinern unzuverlässig (hohe Falsch-Positiv- UND Falsch-Negativ-Raten), veralten
  schnell, adversarial fragil. **Grund: für eine Kennzeichnungs-Entscheidung nicht verteidigbar** - das
  würde die belastbare Aussage untergraben; höchstens als separat markiertes "unsicheres Indiz" denkbar,
  das das Ergebnis nicht steuert.
- **Forensik/Statistik** (Frequenzspektrum, Rausch-Residuen, Diffusions-Fingerprints): Forschungsgrad,
  kein fertiges Werkzeug, gleiche Zuverlässigkeits-Vorbehalte wie ML-Klassifikatoren. **Grund:
  Aufwand/Nutzen passt nicht.**
- **Fingerprint-/Hash-Abgleich** gegen eine Registry bekannter KI-Bilder: funktioniert nur, wenn das
  Bild dort registriert ist - keine allgemeine Lösung. **Grund: zu geringe Abdeckung.**

Die Leitlinie: lieber wenige, belastbare Signale (Provenienz) als viele unsichere - passend zum Zweck,
eine rechtssichere KI-Kennzeichnung nach EU AI Act Art. 50 zu unterstützen.

## Wenn etwas schiefgeht

Stuerzt das Programm ab, landet der Bericht auf Platte statt nur im Terminal -
zwei Dateien neben den Einstellungen, beide im Speicherort-Tab der
Einstellungen verlinkt, sobald es sie gibt:

| Datei | Wofuer |
| --- | --- |
| `last-crash.txt` | Python-Fehler samt Traceback. Wird geschrieben, **bevor** der Fehlerdialog laeuft - faellt dieser beim Neuaufbau selbst mit, waere der Bericht sonst verloren. |
| `fault.log` | Alles darunter: native Speicherzugriffsfehler, Stack-Overflow, fataler Interpreter-Fehler. Solche Abstuerze laufen an Pythons Fehlerbehandlung vorbei. |

Beide Dateien werden **angehaengt**, nicht ersetzt - ein zweiter Absturz
verdeckt den ersten nicht.

`fault.log` bekommt ausserdem je Programmlauf eine Start- und eine Endzeile.
Damit ist ablesbar, was passiert ist:

| Was in der Datei steht | Was es bedeutet |
| --- | --- |
| Start, Traceback, Ende | Python-Fehler, das Programm hat ihn gesehen |
| Start, Ende | sauber beendet |
| Start, dann nichts | Prozess hart abgeraeumt - **kein** Python-Fehler |

Ein hart abgeraeumter Prozess und ein Absturz sehen im Terminal gleich aus.
Erst die fehlende Endzeile trennt beide Faelle.

Unter Windows startest Du das Programm am besten ueber `run.ps1`: das Skript
setzt das Terminal auch dann wieder zurueck, wenn das Programm hart abstuerzt
und selbst nichts mehr tun kann. Sonst bleibt die Maus-Erfassung aktiv, und
jede Mausbewegung kippt Steuerzeichen in die Eingabezeile.

## Lizenz

Apache-2.0.
