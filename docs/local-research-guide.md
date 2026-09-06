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

### Corpuskwaliteit inventariseren

Open **Corpuskwaliteit** en kies **Corpusrapport genereren**, of gebruik:

```bash
isc-helwigii audit onderzoek.db
isc-helwigii audit onderzoek.db --output corpus-audit.json
```

De audit leest bronnen, edities, annotaties en reviewhistorie in één consistente, alleen-lezen momentopname. Tablet-aantallen zijn unieke brongebonden artefacten; editie-aantallen omvatten alle versies. Het bronnenregister toont de ingevoerde licentietekst, adapter en checksum zonder ruwe bronbytes in JSON op te nemen. Een licentietekst is geen juridische verificatie of toestemming voor herdistributie.

Ontbrekende top-level metadata kan voor de inventaris uit `legacy_metadata` worden weergegeven. De rij vermeldt dan het oorspronkelijke pad, zoals `legacy_metadata.period`. Dit is alleen een zichtbare fallback: oude perioden, genres en mythlabels worden niet geaccepteerd bewijs en worden nooit automatisch gold labels.

De probleemrijen markeren onder meer onbekende taal, lege of geheel onleesbare tekst, ontbrekende periode of vindplaats, malformed metadata, legacy/synthetische herkomst, ontbrekende composition family, meerdere edities, identieke genormaliseerde tekst en dezelfde externe identificatie bij verschillende bronnen. Geheel onleesbaar betekent hier: na witruimtenormalisatie blijven alleen haakjes, interpunctie, `x`-markeringen of `lacuna` over. Dit is een technische drempel; de audit verklaart tekst niet inhoudelijk correct of incorrect. De export, tellingen en verdelingen omvatten alle probleemrijen; de interface filtert die volledige verzameling en toont pagina's van maximaal 100 rijen.

### Een referentieset voorbereiden

Maak per tablet twee afzonderlijk beoordeelde categorie-annotaties:

1. Kies bij **Lezen & annoteren** het type `category`, de gewenste as (bijvoorbeeld `genre`) en een inhoudelijk label.
2. Leg nog een `category` vast met as `composition_family` en de redactionele compositiefamilie.
3. Beoordeel beide voorstellen expliciet. Alleen de actuele status `accepted` telt; pending, rejected en door een geaccepteerde herziening superseded voorstellen tellen niet.

Daarna kan **Corpuskwaliteit** de set voorbereiden, of gebruik:

```bash
isc-helwigii reference-set onderzoek.db --axis genre --seed 42
isc-helwigii reference-set onderzoek.db --axis genre --seed 42 --output genre-reference.json
```

Een exportpad moet nieuw zijn en mag niet het projectbestand zijn. De export bewaart per editie de tekst, bron- en recordchecksum, bronrechten, gekozen labels en de betrokken annotatie- en reviewhistorie. Lokale actornamen zijn attributie, geen geauthenticeerde deskundigheidsstatus. Een aanwezige taalwaarde is een technische toegangsdrempel en geen onafhankelijke taalcontrole.

De voorbereiding sluit edities met ontbrekende of conflicterende geaccepteerde labels/families, synthetische data, onbekende taal en lege of geheel onleesbare tekst uit. Een leeg resultaat is een gedocumenteerde onthouding, geen gefabriceerde benchmark. Legacy-records kunnen alleen deelnemen na expliciete annotatie en beoordeling; hun geïmporteerde labels volstaan niet.

Groepering gebeurt vóór uitsluiting over het volledige corpus. Alle edities van één tablet, alle geaccepteerde composition-family-koppelingen en exacte tekstduplicaten vormen transitieve componenten, ook als een tussenliggende editie zelf wordt uitgesloten. Tekstnormalisatie is uitsluitend Unicode NFC, casefolding en samengevouwen witruimte; diacritische tekens, schade-notatie en indexcijfers blijven onderscheiden. Bijna-duplicaten vragen handmatige familiegroepering.

Dezelfde momentopname, as en seed geven dezelfde export. Toegevoegde bronnen, edities, annotaties of beoordelingen veranderen de fingerprints en kunnen componenten — en dus splittoewijzingen — verplaatsen. Behandel de splits daarom als een reproduceerbaar voorstel bij een specifieke corpusstaat, niet als een permanent bevroren of representatieve gold benchmark.

## Productgrenzen en vervolgstappen

Deze versie ondersteunt handmatige filologische workflows en verkennende analyse. Voor een volledig gevalideerd automatisch onderzoeksplatform ontbreken nog: omvangrijke taalgescheiden gold sets, lokale OCR- en vertaalmodellen, geometrische joins, geharmoniseerde laboratoriumreferenties, gekalibreerde herkomstmodellen en echte historische modelvergelijking met resampling en biasanalyse. De productplanning houdt die onderzoekstaken open.

Het project is voor één lokale onderzoeker ontworpen. Namen in beoordelingen zijn geen geauthenticeerde gebruikersrollen. Bijlagen zijn maximaal 32 MiB; herstel ondersteunt bundles tot 4 GiB gedecomprimeerde projectdata. Grote-corpus-, Windows-, GPU-, toegankelijkheids- en meergebruikertests blijven afzonderlijke acceptatiepunten.
