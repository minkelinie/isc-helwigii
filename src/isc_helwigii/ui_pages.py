"""Task-based local UI. Domain rules remain in the tested core."""

import csv
import io
import json
from pathlib import Path

import streamlit as st

from isc_helwigii.bundles import export_bundle, restore_bundle
from isc_helwigii.capabilities import CAPABILITIES
from isc_helwigii.demo import seed_demo
from isc_helwigii.ingest import PARSERS
from isc_helwigii.research import editions, run_method
from isc_helwigii.store import ANNOTATION_KINDS
from isc_helwigii.ui_corpus import corpus_page
from isc_helwigii.ui_dossier import prepare_page
from isc_helwigii.ui_translation import translation_page


def choose_artifact(store, key="artifact"):
    query = st.text_input("Zoek tablet of metadata", key=key + "_query")
    page = st.number_input("Resultaatpagina (vanaf 0)", min_value=0, value=0, key=key + "_page")
    rows = store.artifacts(query, limit=200, offset=page * 200)
    if not rows:
        st.info(
            "Geen tabletten op deze resultaatpagina. Pas de zoekterm of pagina aan, of importeer een bron bij Project."
        )
        return None
    labels = {r["id"]: f"{r['external_id']} · {r['source']}" for r in rows}
    chosen = st.selectbox("Tablet", list(labels), format_func=labels.get, key=key)
    return store.dossier(chosen)


def show_annotations(dossier):
    rows = [
        {k: a[k] for k in ("id", "kind", "origin", "actor", "status")}
        for a in dossier["annotations"]
    ]
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.caption("Nog geen annotaties.")


def project_page(store, actor):
    st.header("Project en bronnen")
    st.write(
        "Maak een lokaal onderzoeksproject, importeer edities en houd de oorspronkelijke bron intact."
    )
    if st.button("Project initialiseren", key="init"):
        store.initialize()
        st.success("Project beschikbaar.")
    if not store.path.exists():
        st.info("Initialiseer dit nieuwe project om te beginnen.")
        return
    st.metric("Tabletten", store.statistics()["artifacts"])
    st.caption(str(store.path))
    if st.button("Synthetische demonstratie laden", key="demo"):
        seed_demo(store)
        st.success("Drie fictieve getuigen geladen; deze zijn geen historische onderzoeksdata.")
    with st.form("import"):
        st.subheader("Bron importeren")
        kind = st.selectbox("Bestandsformaat", list(PARSERS))
        upload = st.file_uploader("Bronbestand", type=["json", "atf", "txt"])
        source = st.text_input("Bron of collectie", placeholder="Bijvoorbeeld CDLI-export-2026")
        license_text = st.text_input(
            "Licentie of gebruiksbeperking",
            value="private — geen toestemming voor herdistributie vastgelegd",
        )
        submitted = st.form_submit_button("Importeren")
    if submitted:
        if upload is None:
            raise ValueError("selecteer een bronbestand")
        raw = upload.getvalue()
        records = PARSERS[kind](raw)
        snapshot = store.import_records(
            raw, records, source=source, license=license_text, adapter=kind + "-v1"
        )
        st.success(f"{len(records)} records verwerkt.")
        st.code(snapshot)
    st.caption(
        "ATF: genummerde tekstregels en taalcode. ORACC: catalogue.json; volledige CDL-edities worden nog niet automatisch ingelezen. Bronbytes blijven beschikbaar."
    )


def dossier_page(store, actor):
    st.header("Tabletdossier")
    query = st.text_input("Zoek in identificaties en editiemetadata")
    st.dataframe(store.artifacts(query, limit=200), hide_index=True)
    dossier = choose_artifact(store, "dossier_artifact")
    if dossier is None:
        return
    for index, edition in enumerate(dossier["editions"], 1):
        with st.expander(f"Editie {index} · {edition['source']}", expanded=index == 1):
            if edition["record"].get("synthetic"):
                st.warning("Synthetisch demonstratierecord.")
            st.json(edition["record"])
            st.caption(f"Licentie: {edition['license']} | SHA-256: {edition['checksum']}")
            st.download_button(
                "Oorspronkelijke bron downloaden",
                store.source_bytes(edition["snapshot_id"]),
                file_name="source.bin",
                key="raw_" + edition["id"],
            )
    show_annotations(dossier)
    with st.form("media"):
        media = st.file_uploader("Beeld, scan, laboratoriumrapport of 3D-bestand (maximaal 32 MiB)")
        rights = st.text_input("Mediarechten", value="private")
        submitted = st.form_submit_button("Bijlage opslaan")
    if submitted:
        if media is None:
            raise ValueError("selecteer een bijlage")
        store.add_asset(
            dossier["id"],
            media.getvalue(),
            name=media.name,
            media_type=media.type or "application/octet-stream",
            license=rights,
            actor=actor,
        )
        st.success("Bijlage met checksum opgeslagen.")
        dossier = store.dossier(dossier["id"])
    for asset in dossier["assets"]:
        with st.expander(asset["name"]):
            st.caption(f"{asset['license']} · {asset['checksum']}")
            content = store.asset_bytes(asset["id"])
            if asset["media_type"] in ("image/png", "image/jpeg", "image/webp"):
                st.image(content)
            st.download_button(
                "Bijlage downloaden", content, file_name=asset["name"], key=asset["id"]
            )


def reading_page(store, actor):
    st.header("Lezen, vertalen en annoteren")
    dossier = choose_artifact(store, "reading_artifact")
    if dossier is None:
        return
    choices = {e["id"]: e for e in dossier["editions"]}
    edition_id = st.selectbox(
        "Broneditie",
        list(choices),
        format_func=lambda key: (
            f"{choices[key]['record'].get('title', dossier['external_id'])} · {key[:10]}"
        ),
    )
    edition = choices[edition_id]
    text = edition["record"].get("text", "")
    st.code(text or "(catalogusrecord zonder tekst)")
    kind = st.selectbox(
        "Annotatietype",
        [k for k in ANNOTATION_KINDS if k not in ("material", "hypothesis", "physical_match")],
    )
    with st.form("annotation"):
        payload = {}
        if kind in ("translation", "transliteration", "morphology", "motif", "sign"):
            st.caption("Passagegrenzen tellen Unicode-tekens: begin inclusief, einde exclusief.")
            start = st.number_input(
                "Beginpositie", min_value=0, max_value=max(len(text), 1), value=0
            )
            end = st.number_input(
                "Eindpositie", min_value=0, max_value=max(len(text), 1), value=len(text)
            )
            payload = {"edition_id": edition_id, "start": start, "end": end}
        if kind == "translation":
            payload.update(
                text=st.text_area("Vertaling"),
                target_language=st.text_input("Doeltaal", value="nl"),
            )
        elif kind == "motif":
            payload.update(
                name=st.text_input("Motief"),
                definition=st.text_area("Definitie en wetenschappelijke referentie"),
                presence=st.selectbox("Waarneming", ["present", "absent", "uncertain"]),
            )
        elif kind == "category":
            payload.update(
                label=st.text_input("Categorie"),
                axis=st.selectbox(
                    "Classificatie",
                    ["genre", "language", "period", "archive", "composition_family", "other"],
                ),
            )
            st.caption(
                "Gebruik composition_family voor expliciete redactionele groepering; "
                "beoordeling blijft nodig voordat een referentieset dit label gebruikt."
            )
        elif kind == "date":
            st.caption("Astronomische jaartelling: jaar 0 = 1 v.Chr.; -1999 = 2000 v.Chr.")
            payload["interval"] = [
                st.number_input("Vroegste jaar", value=-1999),
                st.number_input("Laatste jaar", value=-1899),
            ]
            payload["basis"] = st.text_area("Dateringsgrond")
        elif kind == "place":
            payload.update(
                name=st.text_input("Plaats"),
                relation=st.selectbox(
                    "Relatie", ["findspot", "clay_source", "mentioned_place", "composition_origin"]
                ),
                basis=st.text_area("Onderbouwing"),
            )
        elif kind == "sign":
            payload.update(
                reading=st.text_input("Voorgestelde tekenlezing"),
                alternatives=st.text_input("Alternatieve lezingen"),
            )
            if dossier["assets"]:
                asset_map = {a["id"]: a["name"] for a in dossier["assets"]}
                payload["asset_id"] = st.selectbox(
                    "Beeldbijlage", list(asset_map), format_func=asset_map.get
                )
                payload["bbox"] = [
                    st.number_input(label, min_value=0.0, max_value=1.0, value=default)
                    for label, default in [
                        ("Links", 0.0),
                        ("Boven", 0.0),
                        ("Rechts", 1.0),
                        ("Onder", 1.0),
                    ]
                ]
        else:
            payload["text"] = st.text_area("Lezing of onderzoeksnotitie")
        origin = st.selectbox("Herkomst interpretatie", ["observed", "imported", "inferred"])
        revisions = {a["id"]: a for a in dossier["annotations"] if a["kind"] == kind}
        supersedes = st.selectbox(
            "Herziening van",
            [""] + list(revisions),
            format_func=lambda key: "Nieuwe annotatie" if not key else key[:12],
        )
        submitted = st.form_submit_button("Annotatie voorstellen")
    if submitted:
        annotation = store.annotate(
            dossier["id"],
            kind,
            payload,
            actor=actor,
            evidence=[edition["snapshot_id"], edition_id],
            origin=origin,
            supersedes=supersedes or None,
        )
        st.success(f"Voorstel opgeslagen: {annotation}")
    dossier = store.dossier(dossier["id"])
    show_annotations(dossier)
    if dossier["annotations"]:
        labels = {
            a["id"]: f"{a['kind']} · {a['status']} · {a['id'][:12]}" for a in dossier["annotations"]
        }
        chosen = st.selectbox("Annotatie beoordelen", list(labels), format_func=labels.get)
        annotation = next(a for a in dossier["annotations"] if a["id"] == chosen)
        st.json(annotation)
        with st.form("review"):
            decision = st.selectbox("Besluit", ["accepted", "rejected"])
            reason = st.text_area("Beoordelingsgrond")
            if st.form_submit_button("Beoordeling vastleggen"):
                store.review(chosen, decision, actor=actor, reason=reason)
                st.success("Beoordeling aan de historie toegevoegd.")
    st.subheader("Beoordeelde parallelvertaling zoeken")
    with st.form("translation_memory"):
        query = st.text_area("Passage om op te zoeken", value=text)
        target = st.text_input("Gewenste doeltaal", value="nl")
        if st.form_submit_button("Vertaalgeheugen raadplegen"):
            st.json(
                run_method(
                    store,
                    "translation-memory",
                    {
                        "query": query,
                        "language": edition["record"].get("language", "unknown"),
                        "target_language": target,
                    },
                    actor=actor,
                )
            )


def comparison_page(store, actor):
    st.header("Teksten en fragmenten vergelijken")
    rows = editions(store, query=st.text_input("Zoek de te vergelijken edities"), limit=200)
    if len(rows) < 2:
        st.info("Twee edities nodig voor vergelijking.")
        return
    labels = {
        e["id"]: f"{e['external_id']} · {e.get('language', 'unknown')} · {e['id'][:8]}"
        for e in rows
    }
    left = st.selectbox("Linkereditie", list(labels), format_func=labels.get)
    right = st.selectbox("Rechtereditie", list(labels), index=1, format_func=labels.get)
    by_id = {e["id"]: e for e in rows}
    a, b = st.columns(2)
    a.code(by_id[left].get("text", ""))
    b.code(by_id[right].get("text", ""))
    if st.button("Tekstvergelijking uitvoeren"):
        st.json(run_method(store, "text", {"left": left, "right": right}, actor=actor))
    st.caption(
        "Tokenoverlap en sequentie-uitlijning zijn verkennende tekstmaten. Automatische breukvlak- of 3D-matching is nog niet geïntegreerd."
    )
    with st.form("join"):
        basis = st.text_area(
            "Onderbouwing fysiek joinvoorstel",
            placeholder="Breukvlak, schaal, dikte, kromming, materiaal, schrift en tegenbewijs",
        )
        if st.form_submit_button("Joinvoorstel bewaren"):
            record = by_id[left]
            result = store.annotate(
                record["artifact_id"],
                "physical_match",
                {"target_artifact": by_id[right]["artifact_id"], "basis": basis},
                actor=actor,
                evidence=[left, right],
                origin="inferred",
            )
            st.success(result)


def material_page(store, actor):
    st.header("Klei en laboratoriumgegevens")
    st.write(
        "Leg gemeten waarden vast met methode, laboratorium, kalibratie en eenheid. De vergelijking vereist positieve onzekerheden op één standaardafwijking."
    )
    dossier = choose_artifact(store, "material_artifact")
    if dossier is None:
        return
    with st.form("material"):
        method = st.text_input("Meetmethode", placeholder="pXRF, INAA, …")
        lab = st.text_input("Laboratorium")
        calibration = st.text_input("Kalibratie-identificatie")
        reference = st.text_input("Referentiegroep")
        csv_text = st.text_area(
            "Metingen (CSV: element,value,uncertainty,unit)",
            value="element,value,uncertainty,unit\n",
        )
        if st.form_submit_button("Materiaalannotatie voorstellen"):
            measurements = {}
            for row in csv.DictReader(io.StringIO(csv_text)):
                if row["element"] in measurements:
                    raise ValueError("dubbele analyten in meettabel")
                measurements[row["element"]] = {
                    "value": float(row["value"]),
                    "uncertainty": float(row["uncertainty"]),
                    "unit": row["unit"],
                }
            payload = {
                "method": method,
                "laboratory": lab,
                "calibration": calibration,
                "reference_group": reference,
                "measurements": measurements,
            }
            store.annotate(
                dossier["id"],
                "material",
                payload,
                actor=actor,
                evidence=[dossier["editions"][0]["snapshot_id"]],
            )
            st.success(
                "Voorstel bewaard. Beoordeel het in Lezen & annoteren voordat het aan analyses deelneemt."
            )
    artifacts = store.artifacts(
        st.text_input("Zoek tabletten voor materiaalvergelijking"), limit=200
    )
    labels = {a["id"]: a["external_id"] for a in artifacts}
    selected = st.multiselect(
        "Twee tabletten met beoordeelde materiaalmetingen", list(labels), format_func=labels.get
    )
    if st.button("Materiaal vergelijken"):
        st.json(run_method(store, "material", {"artifacts": selected}, actor=actor))


def mythology_page(store, actor):
    st.header("Mythen, getuigen en hypothesen")
    labels = {
        a["id"]: a["external_id"]
        for a in store.artifacts(st.text_input("Zoek het onderzoekscohort"), limit=200)
    }
    selected = st.multiselect("Onderzoekscohort", list(labels), format_func=labels.get)
    if st.button("Motiefoverlap onderzoeken"):
        result = run_method(store, "motif-network", {"artifacts": selected}, actor=actor)
        st.json(result)
        edges = result["outputs"]["edges"]
        if edges:
            # JSON quoting prevents user labels from becoming DOT syntax.
            graph = (
                "graph G {"
                + ";".join(
                    json.dumps(labels[e["source"]]) + " -- " + json.dumps(labels[e["target"]])
                    for e in edges
                )
                + "}"
            )
            st.graphviz_chart(graph)
    if st.button("Dateringsintervallen vergelijken"):
        st.json(run_method(store, "chronology", {"artifacts": selected}, actor=actor))
    st.caption(
        "Geen motiefannotatie betekent onbekend. Overlap bewijst geen afstamming. Een tabletdatum dateert een getuige, niet het begin van een mondelinge traditie."
    )
    dossier = choose_artifact(store, "hypothesis_artifact")
    if dossier is None:
        return
    with st.form("hypothesis"):
        statement = st.text_area("Toetsbare hypothese")
        alternatives = st.multiselect(
            "Concurrerende verklaringen",
            ["inheritance", "diffusion", "convergence", "contamination", "preservation bias"],
        )
        test_plan = st.text_area("Voorspellingen, toetsmethode en mogelijke weerlegging")
        counter = st.text_area("Tegenbewijs, onzekerheid en ontbrekende gegevens")
        if st.form_submit_button("Hypothese vastleggen"):
            evidence = [
                e["snapshot_id"]
                for aid in selected or [dossier["id"]]
                for e in store.dossier(aid)["editions"]
            ]
            store.annotate(
                dossier["id"],
                "hypothesis",
                {
                    "statement": statement,
                    "alternatives": alternatives,
                    "test_plan": test_plan,
                    "counter_evidence": counter,
                    "cohort": selected,
                },
                actor=actor,
                evidence=sorted(set(evidence)),
                origin="inferred",
            )
            st.success("Hypothese en alternatieven vastgelegd voor beoordeling.")


def evaluation_page(store, actor):
    st.header("Evaluatie en datasetsplits")
    st.write(
        "Meet modeluitvoer tegen expliciete gold labels. Lege voorspellingen tellen als onthouding. Families en identieke teksten blijven bij elkaar in de splits."
    )
    with st.form("evaluation"):
        evaluation_type = st.selectbox(
            "Evaluatietaak", ["evaluation", "ranking-evaluation", "reading-evaluation"]
        )
        st.caption(
            "Labels: id naar label. Rankings: query-id naar lijst tablet-IDs. Lezingen: id naar tekst; null als ontbrekende voorspelling."
        )
        gold = st.text_area("Gold labels (JSON: identificatie naar label)", value="{}")
        predictions = st.text_area("Voorspelde labels (JSON; null = onthouding)", value="{}")
        if st.form_submit_button("Evaluatie opslaan"):
            st.json(
                run_method(
                    store,
                    evaluation_type,
                    {"gold": json.loads(gold), "predicted": json.loads(predictions)},
                    actor=actor,
                )
            )
    with st.form("split"):
        records = st.text_area("Datasetrecords (JSON: id, family, text)", value="[]")
        seed = st.number_input("Seed", value=42)
        if st.form_submit_button("Familiesplits maken"):
            st.json(
                run_method(
                    store, "split", {"records": json.loads(records), "seed": seed}, actor=actor
                )
            )


def exports_page(store, actor):
    st.header("Experimenten en projectbundels")
    runs = store.runs()
    for run in runs:
        with st.expander(f"{run['method']} · {run['created_at']} · {run['id'][:10]}"):
            st.json(run)
            st.download_button(
                "Experiment als JSON",
                json.dumps(run, ensure_ascii=False, indent=2),
                file_name=run["id"] + ".json",
                key=run["id"],
            )
    st.caption(
        "Een projectbundel bevat ook bronbestanden en media. De vastgelegde gebruiksrechten blijven van toepassing."
    )
    with st.form("export"):
        destination = st.text_input(
            "Nieuw exportbestand", value=str(store.path.with_suffix(".zip"))
        )
        if st.form_submit_button("Projectbundel maken"):
            st.json(export_bundle(store, Path(destination)))
            st.success(f"Bundel opgeslagen: {destination}")
    with st.form("restore"):
        source = st.text_input("Bestaande projectbundel (.zip)")
        target = st.text_input("Nieuw projectbestand voor herstel")
        if st.form_submit_button("Bundel controleren en herstellen"):
            restored = restore_bundle(Path(source), Path(target))
            st.success(
                f"Hersteld naar {restored.path}. Selecteer dit bestand links om het te openen."
            )


def capabilities_page(store, actor):
    st.header("Mogelijkheden en methodegrenzen")
    st.write(
        "Dit is een lokaal onderzoekswerkstation met verkennende methoden. De onderstaande grenzen horen bij het product en zijn ook bij de analyses zichtbaar."
    )
    st.dataframe(CAPABILITIES, hide_index=True)
    st.write(
        "Er worden geen externe modellen aangeroepen. Geautomatiseerde taal-, beeld-, herkomst- en ouderdomsmodellen vragen afzonderlijke datasets, hardwaretests en wetenschappelijke validatie."
    )


PAGES = {
    "Project": project_page,
    "Onderzoeksdossier": lambda store, actor: prepare_page(store, actor, choose_artifact),
    "Vertalen": lambda store, actor: translation_page(store, actor, choose_artifact),
    "Tabletten": dossier_page,
    "Lezen & annoteren": reading_page,
    "Vergelijken": comparison_page,
    "Materiaal": material_page,
    "Mythen & hypothesen": mythology_page,
    "Evaluatie": evaluation_page,
    "Corpuskwaliteit": corpus_page,
    "Experimenten & export": exports_page,
    "Mogelijkheden": capabilities_page,
}
