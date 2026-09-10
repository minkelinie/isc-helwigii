"""Editorial translation workspace for one source edition and target language."""

import hashlib
import json

import streamlit as st

from isc_helwigii.translation import build_translation_sheet, render_translation_markdown

STATUS = {
    "pending": "In afwachting",
    "accepted": "Geaccepteerd",
    "rejected": "Afgewezen",
    "superseded": "Vervangen",
}
ORIGIN = {
    "observed": "Eigen waarneming",
    "imported": "Overgenomen uit bron",
    "inferred": "Afgeleid",
}


def _key(*parts):
    return "translation_" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _annotation_label(annotation):
    payload = annotation["payload"]
    return (
        f"{payload['start']}–{payload['end']} · {STATUS[annotation['status']]} · "
        f"{annotation['id']}"
    )


def _show_annotation(annotation, source):
    payload = annotation["payload"]
    st.caption(
        f"Bronposities {payload['start']}–{payload['end']} · "
        f"Status: {STATUS[annotation['status']]} · Annotatie: {annotation['id']}"
    )
    left, right = st.columns(2)
    left.caption("Toegewezen bronpassage")
    left.code(source[payload["start"] : payload["end"]], language=None)
    right.caption("Voorgestelde vertaling")
    right.code(payload["text"], language=None)
    st.caption("Bibliografische verwijzing of brontekst")
    st.code(payload.get("reference") or "Niet opgegeven", language=None)
    st.caption(
        f"Voorsteller: {annotation['actor']} · Herkomst: {ORIGIN.get(annotation['origin'], annotation['origin'])}"
    )
    review = annotation["review"]
    if review:
        st.caption(
            f"Beoordelaar: {review['actor']} · Laatste besluit: {STATUS[review['decision']]} · "
            f"{review['created_at']} · Beoordeling {review['seq']}"
        )
        st.text(review["reason"])
    else:
        st.caption("Beoordelaar: nog niet beoordeeld.")


def _show_blocks(sheet, selected):
    """Keep each candidate intact; its selected review card is rendered below."""
    shown = set()
    for status, heading in (
        ("translated", "Beoordeelde vertaalpassages"),
        ("conflict", "Conflicterende passages"),
        ("untranslated", "Nog te vertalen passages"),
    ):
        blocks = [segment for segment in sheet["segments"] if segment["status"] == status]
        if not blocks:
            continue
        st.subheader(heading)
        if status == "conflict":
            st.warning(
                "Geaccepteerde voorstellen overlappen. Het hele samenhangende bronbereik "
                "telt als conflict totdat een expliciete beoordeling dit oplost."
            )
        for block in blocks:
            st.caption(f"Bronposities {block['start']}–{block['end']}")
            if status != "translated":
                st.code(block["source_text"], language=None)
            for annotation in block["candidates"]:
                if annotation["id"] in shown:
                    continue
                shown.add(annotation["id"])
                if annotation["id"] == selected:
                    st.caption(
                        "Dit voorstel staat volledig bij ‘Gekozen voorstel en beoordeling’ hieronder."
                    )
                else:
                    _show_annotation(annotation, sheet["edition"].get("text", ""))


def translation_page(store, actor, choose_artifact):
    st.header("Vertalen")
    st.write("Werk per broneditie en doeltaal aan een controleerbare vertaling.")
    st.info(
        "Er is geen generatief vertaalmodel aangesloten. Je voert zelf een vertaling "
        "of een vertaling uit een bron in; ieder voorstel vraagt een afzonderlijke beoordeling."
    )
    project_key = _key(str(store.path.resolve()))
    dossier = choose_artifact(store, project_key + "_artifact")
    if dossier is None:
        return
    editions = {edition["id"]: edition for edition in dossier["editions"]}
    if not editions:
        st.info("Dit tablet heeft nog geen broneditie.")
        return
    edition_id = st.selectbox(
        "Broneditie",
        list(editions),
        format_func=lambda value: (
            f"{editions[value]['record'].get('title') or dossier['external_id']} · {value[:12]}"
        ),
        key=_key(project_key, dossier["id"], "edition"),
    )
    target = st.text_input(
        "Doeltaal",
        value="nl",
        key=_key(project_key, edition_id, "target"),
        help="Taalcode, bijvoorbeeld nl voor Nederlands of en voor Engels.",
    ).strip()
    if not target:
        st.info("Vul een doeltaal in om het vertaalblad te openen.")
        return
    scope = _key(project_key, edition_id, target)
    sheet = build_translation_sheet(store, edition_id, target)
    edition = sheet["edition"]
    source = edition.get("text", "")
    st.subheader("Bron en doeltaal")
    st.caption(
        f"{edition['external_id']} · Bron: {edition['source']} · "
        f"Brontaal: {edition.get('language') or 'onbekend'} · Doeltaal: {target}"
    )
    if edition.get("synthetic"):
        st.warning("Synthetisch demonstratierecord; geen historische onderzoeksdata.")
    st.code(source or "(catalogusrecord zonder tekst)", language=None)
    st.caption(
        f"Editie: {edition_id} · Momentopname: {edition['snapshot_id']} · "
        f"Licentie: {edition['license']} · SHA-256: {edition['checksum']}"
    )
    coverage = sheet["coverage"]
    ratio = coverage["ratio"]
    columns = st.columns(4)
    columns[0].metric("Redactionele dekking", f"{ratio:.1%}" if ratio is not None else "—")
    columns[1].metric("Vertaalde tekens", coverage["translated_characters"])
    columns[2].metric("Tekens met conflict", coverage["conflict_characters"])
    columns[3].metric("Nog te vertalen tekens", coverage["untranslated_characters"])
    st.caption(
        "Redactionele dekking telt alleen geaccepteerde vertalingen zonder overlap, "
        "op basis van brontekens zonder witruimte. Dit is geen nauwkeurigheidsmaat "
        "en zegt niet of de vertaling juist is. Voorstellen in afwachting tellen niet mee."
    )
    notice = st.session_state.pop(scope + "_notice", None)
    if notice:
        st.success(notice)

    st.subheader("Vertaling voorstellen")
    passage = st.text_area(
        "Ongewijzigde bronpassage",
        value=source,
        key=scope + "_passage",
        disabled=not source.strip(),
        help="Kopieer exact uit de bron; behoud spaties, regeleinden en Unicode-tekens.",
    )
    positions = []
    if passage:
        position = source.find(passage)
        while position >= 0:
            positions.append(position)
            position = source.find(passage, position + 1)
    start = positions[0] if positions else None
    if len(positions) > 1:
        start = st.selectbox(
            "Voorkomen in de bron",
            positions,
            format_func=lambda position: (
                f"Positie {position}–{position + len(passage)}: "
                f"…{source[max(0, position - 30):position]}"
                f"⟦{passage}⟧{source[position + len(passage):position + len(passage) + 30]}…"
            ),
            key=_key(scope, passage, "occurrence"),
        )
    valid = start is not None and bool(source.strip())
    end = start + len(passage) if start is not None else None
    if not source.strip():
        st.info("Deze editie bevat geen leesbare brontekst om te vertalen.")
    elif not positions:
        st.info("Kopieer een ongewijzigde passage uit de brontekst hierboven.")
    else:
        st.caption(f"Gekozen Unicode-posities: {start}–{end} (begin inclusief, einde exclusief).")
    span_key = _key(scope, start, end, passage)
    generation_key = span_key + "_generation"
    form_key = _key(span_key, st.session_state.get(generation_key, 0))
    revisions = {
        annotation["id"]: annotation
        for annotation in sheet["annotations"]
        if all(
            annotation["payload"].get(key) == value
            for key, value in (
                ("edition_id", edition_id),
                ("target_language", target),
                ("start", start),
                ("end", end),
            )
        )
    }
    with st.form(form_key):
        translation = st.text_area("Vertaling", key=form_key + "_text", disabled=not valid)
        reference = st.text_area(
            "Bibliografische verwijzing of brontekst",
            key=form_key + "_reference",
            disabled=not valid,
        )
        origin = st.selectbox(
            "Herkomst interpretatie",
            list(ORIGIN),
            format_func=ORIGIN.get,
            key=form_key + "_origin",
            disabled=not valid,
        )
        supersedes = st.selectbox(
            "Herziening van",
            [""] + list(revisions),
            format_func=lambda value: (
                _annotation_label(revisions[value]) if value else "Nieuw voorstel"
            ),
            key=form_key + "_supersedes",
            disabled=not valid,
        )
        submitted = st.form_submit_button("Vertaling voorstellen", disabled=not valid)
    if submitted:
        if not valid or source[start:end] != passage:
            st.error("Selecteer eerst een ongewijzigde bronpassage.")
        elif not translation.strip():
            st.error("Vul een vertaling in voordat je het voorstel opslaat.")
        else:
            try:
                annotation_id = store.annotate(
                    edition["artifact_id"],
                    "translation",
                    {
                        "edition_id": edition_id,
                        "start": start,
                        "end": end,
                        "target_language": target,
                        "text": translation,
                        "reference": reference,
                    },
                    actor=actor,
                    evidence=[edition["snapshot_id"], edition_id],
                    origin=origin,
                    supersedes=supersedes or None,
                )
            except ValueError as exc:
                st.error(f"Voorstel niet opgeslagen: {exc}")
            else:
                # New widget identities clear successful input only. A rerun reads a
                # fresh sheet and consumes the submit event without creating a duplicate.
                st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1
                st.session_state[scope + "_review_annotation"] = annotation_id
                st.session_state[scope + "_notice"] = (
                    "Voorstel opgeslagen; in afwachting van beoordeling."
                )
                st.rerun()

    annotations = {annotation["id"]: annotation for annotation in sheet["annotations"]}
    selected = None
    if annotations:
        choices = list(annotations)
        previous = st.session_state.get(scope + "_review_annotation")
        selected = st.selectbox(
            "Voorstel beoordelen",
            choices,
            index=choices.index(previous) if previous in annotations else 0,
            format_func=lambda value: _annotation_label(annotations[value]),
            # Refresh the selected option's displayed label after a review.
            key=_key(scope, sheet["last_review_seq"], len(choices), "review_selector"),
        )
        st.session_state[scope + "_review_annotation"] = selected
    _show_blocks(sheet, selected)
    if selected:
        st.subheader("Gekozen voorstel en beoordeling")
        annotation = annotations[selected]
        _show_annotation(annotation, source)
        review = annotation["review"]
        review_key = _key(scope, selected, review["seq"] if review else None, "review")
        with st.form(review_key):
            decision = st.selectbox(
                "Besluit",
                ["accepted", "rejected"],
                format_func=STATUS.get,
                key=review_key + "_decision",
            )
            reason = st.text_area("Beoordelingsgrond", key=review_key + "_reason")
            reviewed = st.form_submit_button("Beoordeling vastleggen")
        if reviewed:
            if not reason.strip():
                st.error("Vul een niet-lege beoordelingsgrond in.")
            else:
                try:
                    store.review(selected, decision, actor=actor, reason=reason)
                except ValueError as exc:
                    st.error(f"Beoordeling niet opgeslagen: {exc}")
                else:
                    st.session_state[scope + "_notice"] = (
                        "Beoordeling vastgelegd; vertaalblad bijgewerkt."
                    )
                    st.rerun()
    else:
        st.caption("Nog geen vertaalvoorstellen voor deze broneditie en doeltaal.")

    st.subheader("Vertaalblad bewaren")
    st.caption(
        "Downloads bevatten de huidige bron, voorstellen, beoordelingen en openstaande passages."
    )
    filename = f"vertaalblad-{edition_id}-{target}"
    st.download_button(
        "Vertaalblad downloaden (Markdown)",
        render_translation_markdown(sheet),
        file_name=filename + ".md",
        mime="text/markdown",
        key=scope + "_markdown",
    )
    st.download_button(
        "Vertaalblad downloaden (JSON)",
        json.dumps(sheet, ensure_ascii=False, indent=2),
        file_name=filename + ".json",
        mime="application/json",
        key=scope + "_json",
    )
