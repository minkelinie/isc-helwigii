"""Passage selection and readable, source-linked research results."""

import json

import streamlit as st

from isc_helwigii.research import run_method


def prepare_page(store, actor, choose_artifact):
    st.header("Onderzoeksdossier voorbereiden")
    st.write(
        "Kies een bronpassage. De app zoekt in het volledige corpus en verzamelt tekstparallellen en beoordeelde vertalingen."
    )
    dossier = choose_artifact(store, "prepare_artifact")
    if dossier is None:
        return
    choices = {e["id"]: e for e in dossier["editions"]}
    edition_id = st.selectbox(
        "Broneditie", list(choices), format_func=lambda k: f"{dossier['external_id']} · {k[:10]}"
    )
    edition = choices[edition_id]
    text = edition["record"].get("text", "")
    st.code(text or "(catalogusrecord zonder tekst)")
    if not text:
        st.info("Deze editie bevat geen tekst om te onderzoeken.")
        return
    passage = st.text_area(
        "Passage uit de bron (laat de hele tekst staan of plak een deel)",
        value=text,
        key="dossier_passage_" + edition_id,
    )
    positions = []
    if passage:
        position = text.find(passage)
        while position >= 0:
            positions.append(position)
            position = text.find(passage, position + 1)
    if not positions:
        st.info("Kopieer een ongewijzigde passage uit de brontekst hierboven.")
        return
    start = (
        st.selectbox(
            "Voorkomen in de bron",
            positions,
            format_func=lambda p: f"Positie {p}: …{text[max(0, p - 20) : p + len(passage) + 20]}…",
        )
        if len(positions) > 1
        else positions[0]
    )
    target = st.text_input("Doeltaal voor beoordeelde vertalingen", value="nl")
    limit = st.number_input("Aantal tekstparallellen", min_value=1, max_value=100, value=10)
    parameters = {
        "edition_id": edition_id,
        "start": start,
        "end": start + len(passage),
        "target_language": target,
        "limit": limit,
    }
    selection = (str(store.path), json.dumps(parameters, sort_keys=True))
    if st.button("Onderzoeksdossier voorbereiden", key="prepare_dossier"):
        with st.spinner("Corpus doorzoeken en bewijs verzamelen…"):
            result = run_method(store, "research-dossier", parameters, actor=actor)
        st.session_state["prepared_dossier"] = {"selection": selection, "result": result}
    saved = st.session_state.get("prepared_dossier")
    if not saved or saved["selection"] != selection:
        return
    result = saved["result"]
    output = result["outputs"]
    st.success(
        f"Dossier bewaard · {output['corpus']['edition_count']:,} edities doorzocht · {len(output['parallels'])} kandidaten"
    )
    st.caption(
        "Opgeslagen momentopname. Bereid opnieuw voor na nieuwe bronnen of beoordelingen. Overeenkomstscores zijn geen kans op een juiste vertaling."
    )
    st.download_button(
        "Dossier downloaden (JSON)",
        json.dumps(result, ensure_ascii=False, indent=2),
        file_name="onderzoeksdossier-" + result["run_id"] + ".json",
    )
    if output["status"] == "abstained":
        st.info("Geen voorstel: taal onbekend of geen leesbare tekens in deze passage.")
    st.subheader("Tekstparallellen")
    st.caption(
        "Gerangschikt op woordoverlap met volledige edities in dezelfde geregistreerde taal. Korte parallellen in lange teksten kunnen lager eindigen."
    )
    if not output["parallels"]:
        st.info("Geen tekstparallellen gevonden binnen deze zoekmethode.")
    for i, match in enumerate(output["parallels"], 1):
        with st.expander(
            f"{i}. {match['external_id']} · woordoverlap {match['jaccard']:.1%}", expanded=i == 1
        ):
            if match["synthetic"]:
                st.warning("Synthetisch demonstratierecord.")
            left, right = st.columns(2)
            left.caption("Gekozen passage")
            left.code(output["query"]["text"])
            right.caption("Kandidaateditie")
            right.code(match["text"])
            st.write("Gedeeld: " + ", ".join(match["shared_tokens"]))
            st.write("Alleen in je passage: " + (", ".join(match["query_only_tokens"]) or "—"))
            st.write(
                "Alleen in de kandidaat: " + (", ".join(match["candidate_only_tokens"]) or "—")
            )
            st.caption(
                f"Bron: {match['source']} · editie: {match['id']} · momentopname: {match['snapshot_id']}"
            )
    st.subheader("Beoordeelde vertaalhulp")
    translations = output["translation_memory"]["candidates"]
    if output["translation_memory"].get("truncated"):
        st.caption(
            f"{len(translations)} van {output['translation_memory']['matched_count']} exacte vertaalannotaties getoond. Verhoog het aantal resultaten voor meer alternatieven."
        )
    if not translations:
        st.info(
            "Geen beoordeelde exacte vertaling voor deze passage en doeltaal. De app heeft geen generatief vertaalmodel aangesloten."
        )
    for candidate in translations:
        st.write(candidate["text"])
        st.caption(
            f"Beoordeelde annotatie: {candidate['id']} · Controleer of de context overeenkomt."
        )
