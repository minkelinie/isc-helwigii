"""Streamlit corpus-quality workspace backed by the shared read-only core."""

from __future__ import annotations

import json

import streamlit as st

from isc_helwigii.corpus import REFERENCE_AXES, audit_corpus, prepare_reference_set


def _json_download(label, value, file_name, key):
    st.download_button(
        label,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        file_name=file_name,
        mime="application/json",
        key=key,
    )


def corpus_page(store, actor):
    st.header("Corpuskwaliteit")
    st.write(
        "Inventariseer bronmetadata en bereid een door beoordelingen begrensde referentieset voor. "
        "De rapportage verandert het project niet."
    )
    cache_key = str(store.path)
    audit_key = "corpus_audit_result"
    reference_key = "corpus_reference_result"
    if st.button("Corpusrapport genereren", key="corpus_audit"):
        st.session_state[audit_key] = (cache_key, audit_corpus(store))

    cached = st.session_state.get(audit_key)
    if cached and cached[0] == cache_key:
        report = cached[1]
        st.caption(
            "Momentopname van de laatste generatie. Genereer het corpusrapport opnieuw na "
            "imports, annotaties of beoordelingen."
        )
        counts = report["counts"]
        columns = st.columns(3)
        columns[0].metric("Tabletten", counts["artifacts"])
        columns[1].metric("Edities", counts["editions"])
        columns[2].metric("Bronmomentopnamen", counts["snapshots"])
        st.subheader("Bronnenregister")
        st.dataframe(report["sources"], hide_index=True)
        st.caption(
            "Een vastgelegde licentietekst is bronmetadata, geen onafhankelijke rechtencontrole."
        )

        rows = report["editions"]
        source_options = ["[alle]"] + sorted({row["source"] for row in rows})
        language_options = ["[alle]"] + sorted(
            {str(row["metadata"]["language"]) for row in rows}
        )
        issue_options = ["[alle]"] + sorted(
            {issue for row in rows for issue in row["issues"]}
        )
        filters = st.columns(3)
        selected_source = filters[0].selectbox("Bron", source_options, key="corpus_source")
        selected_language = filters[1].selectbox("Taal", language_options, key="corpus_language")
        selected_issue = filters[2].selectbox(
            "Probleemtype", issue_options, key="corpus_issue"
        )
        filtered = [
            row
            for row in rows
            if (selected_source == "[alle]" or row["source"] == selected_source)
            and (
                selected_language == "[alle]"
                or str(row["metadata"]["language"]) == selected_language
            )
            and (selected_issue == "[alle]" or selected_issue in row["issues"])
        ]
        page = st.number_input(
            "Probleempagina (vanaf 0)", min_value=0, value=0, key="corpus_issue_page"
        )
        st.caption(
            f"{len(filtered)} passende probleemrijen; maximaal 100 per pagina. "
            "De audit markeert controlepunten en beoordeelt geen inhoudelijke geldigheid."
        )
        st.dataframe(filtered[page * 100 : (page + 1) * 100], hide_index=True)
        _json_download(
            "Corpusrapport downloaden",
            report,
            f"corpus-audit-{report['fingerprint'][:12]}.json",
            "download_corpus_audit",
        )
    else:
        st.info("Genereer een rapport om bronnen, tellingen en controlepunten te bekijken.")

    st.subheader("Referentieset voorbereiden")
    st.write(
        "Alleen huidige, geaccepteerde categorielabels én een geaccepteerde "
        "composition_family komen in aanmerking. Pending, rejected en vervangen voorstellen "
        "worden niet als gold evidence gebruikt."
    )
    with st.form("corpus_reference"):
        axis = st.selectbox("Referentie-as", REFERENCE_AXES, key="reference_axis")
        seed = st.number_input("Split-seed", value=42, step=1, key="reference_seed")
        submitted = st.form_submit_button("Referentieset voorbereiden")
    if submitted:
        st.session_state[reference_key] = (
            cache_key,
            prepare_reference_set(store, axis=axis, seed=int(seed)),
        )
    reference = st.session_state.get(reference_key)
    if reference and reference[0] == cache_key:
        result = reference[1]
        st.caption(
            "Momentopname van de laatste voorbereiding. Bereid opnieuw voor na wijzigingen "
            "aan corpus of beoordelingen."
        )
        if result["status"] == "abstained":
            st.warning(
                "Geen in aanmerking komende records: dit resultaat is geen gecertificeerde benchmark."
            )
        else:
            st.success(f"{result['counts']['eligible']} edities voorbereid voor beoordeling.")
        st.json(result["counts"])
        _json_download(
            "Referentieset downloaden",
            result,
            f"reference-{result['parameters']['axis']}-{result['fingerprint'][:12]}.json",
            "download_corpus_reference",
        )
    st.caption(
        "Leg composition_family vast als category-annotatie bij Lezen & annoteren en laat zowel "
        "familie als doellabel expliciet beoordelen. Lokale namen zijn attributie, geen "
        "geauthenticeerde deskundigheidsstatus."
    )
