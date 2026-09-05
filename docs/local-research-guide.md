# Lokale onderzoekshandleiding

## Beginnen

Installeer Python 3.11+ en het pakket met de optionele interface: `python -m pip install -e ".[ui]"`. Maak met `isc-helwigii init onderzoek.db` een nieuw project en start met `isc-helwigii start onderzoek.db`. De interface is bereikbaar op `http://127.0.0.1:8501`. Eenmalige installatie kan internet vereisen; geen onderzoeksbewerking vereist een cloudmodel.

Een project bestaat uit één SQLite-bestand. Het bevat bronkopieën, edities, annotaties, beoordelingen, media en experimenten. De standaardinstellingen van de oude `health`-CLI zijn behouden voor compatibiliteit; gebruik voor projectcontrole een expliciet pad: `isc-helwigii health --database onderzoek.db --json`.

## 1. Bronnen importeren

Vul een bronidentiteit en de werkelijke gebruiksrechten in. Identiteiten worden per bron gescheiden; dezelfde museumnummertekst uit twee collecties wordt niet automatisch samengevoegd. Een nieuwe versie van dezelfde bron krijgt een aparte editie. Identieke herimport is idempotent.

Eigen JSON heeft dit formaat:

```json
[
  {
    "external_id": "LOCAL-001",
    "title": "Eigen transcriptie",
    "language": "akk",
    "text": "a-na ...",
    "period": "onzeker",
    "provenience": "onbekend"
  }
]
```

Gebruik `akk` voor Akkadisch en `sux` voor Sumerisch waar die identificatie onderbouwd is. Niet vastgestelde taal blijft `unknown`. Gegevens worden niet automatisch taalkundig geverifieerd.

ATF ondersteunt artifactkoppen `&P…`, `#atf: lang …`, oppervlakmarkeringen en genummerde regels. Beschadigingstekens blijven in de tekst. Andere directives blijven in de ruwe bronkopie, maar worden nog niet semantisch geïnterpreteerd. ORACC vereist een object van type `catalogue` met `members`; manifests en CDL zijn andere formaten en worden geweigerd. Dit volgt de [ORACC-formaatdocumentatie](https://oracc.museum.upenn.edu/doc/opendata/json/index.html). CDLI publiceert zijn exportvormen in de [API-documentatie](https://cdli.earth/docs/api).

Een legacy SQLite-database met `tablets.id` en `tablets.transliteration` kan met `import-legacy` worden gelezen. De bron blijft intact. De momentopname is de exacte geselecteerde query-export, niet een kopie van de volledige database. Automatische mythlabels blijven herkenbaar als oude metadata.

## 2. Lezen, vertalen en beoordelen

Selecteer een tablet en een specifieke editie. Passagegrenzen zijn Python/Unicode-tekenposities: begin inclusief, einde exclusief. Voor een hele tekst van 20 tekens gebruikt u 0 en 20. De weergegeven brontekst verandert niet als u een alternatieve lezing of vertaling toevoegt.

Een voorstel bevat auteur, herkomst (`observed`, `imported` of `inferred`), bronverwijzing en inhoud. Het krijgt eerst status `pending`. Beoordelen voegt een acceptatie of afwijzing met reden toe. Een nieuwe geaccepteerde herziening kan dezelfde passage en doeltaal vervangen; een andere passage of taal krijgt een apart voorstel.

Het vertaalgeheugen zoekt exacte, eerder geaccepteerde bronpassages in dezelfde taal. U ziet de bestaande vertaling en haar bewijs. Dit is een hulpmiddel bij redactie; voor een onbekende passage wordt geen vertaling verzonnen. Morphologie is momenteel een handmatige annotatieworkflow, geen geïntegreerde automatische parser.

Tekenregio’s gebruiken vier genormaliseerde beeldcoördinaten `[links,boven,rechts,onder]` tussen 0 en 1. Het mediabestand blijft via zijn checksum traceerbaar. RTI/3D-bestanden kunnen worden bewaard en gedownload, maar er is nog geen interactieve 3D-registreerder.

## 3. Teksten, fragmenten en materiaal

Tekstvergelijking toont gedeelde tokens, Jaccard-overlap en sequentie-uitlijning. De normalisatie beperkt zich tot Unicode NFC, kleine letters en witruimte; indexcijfers en filologische tekens blijven staan. Volledig onleesbare of onbekende-talige passages leiden tot onthouding. Fysieke joins kunnen als onderbouwde voorstellen worden vastgelegd. Tekstoverlap wordt niet omgerekend naar een fysiek joinpercentage.

Materiaalgegevens vereisen meetmethode, laboratorium, kalibratie, referentiegroep en analyten. Een meettabel ziet er bijvoorbeeld zo uit (uitsluitend formaatvoorbeeld):

```csv
element,value,uncertainty,unit
Fe,100,5,ppm
Ti,20,2,ppm
```

Bewaar het laboratoriumrapport bij de tablet. `uncertainty` is één standaardafwijking, positief en in dezelfde eenheid als de meting. Alleen analyten met dezelfde eenheid en dezelfde methode/lab/kalibratie worden vergeleken. De uitvoer toont verschillen en een gestandaardiseerde RMS-afstand onder onafhankelijkheidsaannames. Compositionaliteit, gecorreleerde meetfouten en een geografisch referentiemodel zijn nog niet gemodelleerd. Een vergelijkbare samenstelling bewijst geen gemeenschappelijke vervaardigingsplaats.

## 4. Motieven en ouderdomshypothesen

Definieer een motief en wijs de exacte passage aan. Leg aanwezigheid, expliciete afwezigheid of onzekerheid vast. Alleen beoordeelde aanwezige motieven voeden netwerkranden; ontbrekende beoordeling blijft onbekend. De netwerkafstand geldt alleen voor ingevoerde motieven, niet voor een volledige motiefinventaris.

Een hypothese bevat een toetsbare bewering, ten minste twee concurrerende verklaringen, toetsplan, mogelijke weerlegging en tegenbewijs. Het netwerk berekent gedeelde motieven; het kiest geen mechanisme uit overerving, verspreiding, convergentie, contaminatie of bewaarselectie.

Datums zijn intervallen in astronomische jaartelling: jaar 0 is 1 v.Chr., -1999 is 2000 v.Chr. Twee intervallen kunnen overlappen of gescheiden zijn. Ze dateren tekstgetuigen; hiermee is de oorsprong of mondelinge leeftijd van een mythe niet vastgesteld.

## 5. Evalueren en reproduceren

Voer gold labels en modelvoorspellingen in als identificatie-naar-label-objecten. `null` of een ontbrekende voorspelling is onthouding. De uitvoer bevat tellingen, coverage, nauwkeurigheid op alle voorbeelden en op beantwoorde voorbeelden. Kleine aantallen moeten zichtbaar blijven; een score is geen algemene vertaalnauwkeurigheid.

Datasetsplits combineren composition families met exact gelijke genormaliseerde teksten tot ondeelbare groepen. Een seed bepaalt de verdeling. Kleine datasets kunnen lege splits krijgen. Bijna-identieke edities moeten aanvullend door onderzoekers in dezelfde familie worden geplaatst.

Elk experiment bewaart invoer, annotatiestatussen, uitkomst, methode, auteur en gebruikte implementatiecode. Herstel voert opgeslagen code nooit automatisch uit. Download een experiment als JSON of maak een projectbundel. Bundels controleren bron- en mediachecksums, SQLite-integriteit en schemabescherming vóór herstel naar een nieuw bestand.

## Productgrenzen en vervolgstappen

Deze versie ondersteunt handmatige filologische workflows en verkennende analyse. Voor een volledig gevalideerd automatisch onderzoeksplatform ontbreken nog: omvangrijke taalgescheiden gold sets, lokale OCR- en vertaalmodellen, geometrische joins, geharmoniseerde laboratoriumreferenties, gekalibreerde herkomstmodellen en echte historische modelvergelijking met resampling en biasanalyse. De productplanning houdt die onderzoekstaken open.

Het project is voor één lokale onderzoeker ontworpen. Namen in beoordelingen zijn geen geauthenticeerde gebruikersrollen. Bijlagen zijn maximaal 32 MiB; herstel ondersteunt bundles tot 4 GiB gedecomprimeerde projectdata. Grote-corpus-, Windows-, GPU-, toegankelijkheids- en meergebruikertests blijven afzonderlijke acceptatiepunten.
