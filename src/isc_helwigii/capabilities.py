"""Product scope visible to researchers, independent of test success rates."""

CAPABILITIES = [
    {
        "workflow": "Bronnen en corpus",
        "available": "Lokale JSON, ATF en ORACC-catalogi; originele bytes, licentie, edities en een deterministische kwaliteitsinventaris",
        "validation": "Controlepunten voor metadata en exacte duplicaten; geen inhoudelijke corpuscertificering",
    },
    {
        "workflow": "Tekens en paleografie",
        "available": "Beeldbijlagen, handmatige tekenlezingen en genormaliseerde beeldregio’s",
        "validation": "Automatische OCR, RTI en 3D-registratie nog niet geïntegreerd",
    },
    {
        "workflow": "Transliteratie en taalanalyse",
        "available": "Passagegebonden lezingen, morfologische notities en alternatieven",
        "validation": "Handmatig; geen gevalideerde Akkadische of Sumerische parser",
    },
    {
        "workflow": "Vertalen",
        "available": "Uitgelijnde handmatige vertalingen; geheugen van beoordeelde exacte parallelpassages",
        "validation": "Geen generatief vertaalmodel; vakinhoudelijke beoordeling vereist",
    },
    {
        "workflow": "Categoriseren",
        "available": "Labels, perioden, plaatsen en herzieningen met bronverwijzing",
        "validation": "Handmatig; benchmark voor voorspelde labels beschikbaar",
    },
    {
        "workflow": "Tekst- en fragmentmatching",
        "available": "Corpusbreed onderzoeksdossier met woordoverlap, sequentie-uitlijning, bronedities en verschillen; fysieke joinvoorstellen vastleggen",
        "validation": "Verkennende scores; fysieke joins niet automatisch berekend",
    },
    {
        "workflow": "Klei en herkomst",
        "available": "Laboratoriummetingen, onzekerheid en vergelijkbare analyten vergelijken",
        "validation": "Geen gekalibreerde geografische herkomstvoorspelling",
    },
    {
        "workflow": "Mythen en verwantschap",
        "available": "Passagemotieven, overlapnetwerk, getuigendatering en concurrerende hypothesen",
        "validation": "Geen geteste stamboom, diffusie-inferentie of prehistorische datering",
    },
    {
        "workflow": "Evaluatie en reproduceerbaarheid",
        "available": "Evidence-linked referentie-export, familiesplits, classificatiematen, vastgelegde experimentinput en broncode",
        "validation": "Softwarecontracten getest; expliciet beoordeelde, representatieve gold sets blijven nodig",
    },
    {
        "workflow": "Lokaal projectbeheer",
        "available": "SQLite, beeldbijlagen, reviewhistorie en gecontroleerde projectbundels",
        "validation": "Eén lokale onderzoeker; geen geauthenticeerde multi-user review",
    },
]
