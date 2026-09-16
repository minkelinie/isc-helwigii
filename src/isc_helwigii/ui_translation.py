"""Editorial translation workspace for one source edition and target language."""

import hashlib
import json
import shlex
from pathlib import Path

import streamlit as st

from isc_helwigii.translation import build_translation_sheet, render_translation_markdown
from isc_helwigii.translation_quality import render_quality_text
from isc_helwigii.translation_recheck import INPUT_FORMATS, recheck_translation

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
        f"{payload['start']}–{payload['end']} · {STATUS[annotation['status']]} · {annotation['id']}"
    )


def _show_annotation(annotation, source):
    payload = annotation["payload"]
    st.caption(
        f"Bronposities {payload['start']}–{payload['end']} · "
        f"Status: {STATUS[annotation['status']]} · Annotatie: {annotation['id']}"
    )
    left, right = st.columns(2)
    left.caption("Toegewezen bronpassage")
    left.code(source[payload["start"] : payload["end"]], language=None, wrap_lines=True)
    right.caption("Voorgestelde vertaling")
    right.code(payload["text"], language=None, wrap_lines=True)
    if model := payload.get("model"):
        st.text(
            f"Model: {model.get('id', 'onbekend')}\n"
            f"Revisie: {model.get('revision', 'onbekend')}\n"
            f"Run-ID: {model.get('run_id', 'onbekend')}"
        )
        st.warning(
            "Experimentele modelvertaling; controleer de lezing en betekenis aan de bron. "
            "Modeluitvoer kan onjuist of onvolledig zijn en vraagt een expliciete beoordeling."
        )
        if checks := payload.get("quality_checks"):
            quantities = checks["quantities"]
            if quantities["missing_count"]:
                st.warning(
                    f"Controleer de aantallen: {quantities['missing_count']} getalgroep(en) "
                    "zijn niet als dezelfde waarde in de vertaling teruggevonden. "
                    "Bekijk hieronder de bronpassage en berekening."
                )
            if checks["names"]["candidates"]:
                st.info("De bron bevat naamsignalen. Vergelijk deze handmatig met de vertaling.")
            with st.expander(
                "Kwaliteitscontrole bekijken", expanded=bool(quantities["missing_count"])
            ):
                st.text(render_quality_text(checks))
        else:
            st.caption("Dit oudere voorstel heeft nog geen vastgelegde kwaliteitscontrole.")
    rechecks = annotation.get("quality_rechecks", [])
    for index, run in enumerate(rechecks, 1):
        checks = run["outputs"]
        with st.expander(
            f"Hercontrole {index} · {run['created_at']}", expanded=index == len(rechecks)
        ):
            st.text(f"Onderzoeker: {run['actor']}\nRun-ID: {run['id']}")
            st.caption("De oorspronkelijke vertaling, controle en beoordeling blijven bewaard.")
            if checks["quantities"]["missing_count"]:
                st.warning(
                    f"Hercontrole: {checks['quantities']['missing_count']} getalgroep(en) "
                    "zijn niet als dezelfde waarde in de vertaling teruggevonden."
                )
            st.text(render_quality_text(checks))
    st.caption("Bibliografische verwijzing of brontekst")
    st.code(payload.get("reference") or "Niet opgegeven", language=None, wrap_lines=True)
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


def _recheck_proposal(store, annotation, edition, actor, scope):
    """A separate action on the selected saved proposal, never the editable draft."""
    from isc_helwigii.local_translation import canonical_language

    key = _key(scope, annotation["id"], "recheck")
    original = annotation["payload"].get("quality_checks") or {}
    language = original.get("source_language") or edition.get("language")
    try:
        language = canonical_language(language)
    except ValueError:
        language = ""
    notation = original.get("input_format", "")
    if notation not in INPUT_FORMATS:
        notation = ""
    with st.expander("Opgeslagen voorstel hercontroleren"):
        st.caption(
            "Controleer de toegewezen bronpassage en opgeslagen vertaling hierboven opnieuw. "
            "De hercontrole krijgt een eigen datum en onderzoeker en komt mee in het vertaalblad."
        )
        languages = {"": "Kies de brontaal", "sux": "Sumerisch", "akk": "Akkadisch"}
        selected_language = st.selectbox(
            "Brontaal voor hercontrole",
            list(languages),
            format_func=languages.get,
            index=list(languages).index(language),
            key=key + "_language",
        )
        formats = {
            "": "Kies de schrijfwijze",
            "transliteration": "Transliteratie",
            "complex-transliteration": "Complexe transliteratie",
            "cuneiform": "Spijkerschrifttekens",
        }
        selected_format = st.selectbox(
            "Schrijfwijze voor hercontrole",
            list(formats),
            format_func=formats.get,
            index=list(formats).index(notation),
            key=key + "_format",
        )
        if annotation["payload"]["target_language"] != "en":
            st.info(
                "De getalcontrole ondersteunt Engelse vertalingen. Voor deze doeltaal "
                "legt de hercontrole vast dat aantallen niet automatisch zijn beoordeeld."
            )
        if st.button(
            "Opgeslagen vertaling opnieuw controleren",
            key=key + "_submit",
            disabled=not (selected_language and selected_format),
        ):
            try:
                recheck_translation(
                    store,
                    annotation["id"],
                    actor=actor,
                    source_language=selected_language,
                    input_format=selected_format,
                )
            except ValueError as exc:
                st.error(f"Hercontrole niet opgeslagen: {exc}")
            else:
                st.session_state[scope + "_notice"] = "Hercontrole vastgelegd bij dit voorstel."
                st.rerun()


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


def _choose_english(project_key, edition_id, passage, start):
    """Change the target before widgets render, carrying the exact source selection."""
    st.session_state[_key(project_key, edition_id, "target")] = "en"
    english_scope = _key(project_key, edition_id, "en")
    st.session_state[english_scope + "_passage"] = passage
    if start is not None:
        st.session_state[_key(english_scope, passage, "occurrence")] = start


def _model_proposal(store, actor, edition, target, project_key, passage, start, end):
    st.subheader("Lokaal modelvoorstel")
    st.warning(
        "Dit lokale model is experimenteel en ondersteunt alleen Sumerisch en Akkadisch "
        "naar Engels. De lokale proef bevat fouten in aantallen en Akkadische zinnen. "
        "Controleer ieder voorstel aan de bron; er is geen garantie op juistheid. "
        "Genereren begint alleen wanneer je op de knop klikt."
    )
    # Keep manual editing available while the optional model integration is unavailable.
    try:
        from isc_helwigii import local_translation
    except ImportError as exc:
        st.warning(f"De lokale modelmodule is niet beschikbaar: {exc}")
        return

    edition_id = edition["id"]
    scope = _key(project_key, edition_id, target)
    model_scope = _key(project_key, edition_id, "model")
    if target != "en":
        st.info(
            "Het lokale model kan alleen een Engels voorstel opslaan. "
            "Kies Engels (en) als doeltaal om het te gebruiken."
        )
        st.button(
            "Engels kiezen",
            key=scope + "_choose_english",
            on_click=_choose_english,
            args=(project_key, edition_id, passage, start),
        )
    try:
        default_language = local_translation.canonical_language(edition.get("language"))
    except ValueError:
        default_language = None
    languages = {
        None: "Kies de brontaal expliciet",
        "sux": "Sumerisch (sux)",
        "akk": "Akkadisch (akk)",
    }
    source_language = st.selectbox(
        "Brontaal voor model",
        list(languages),
        index=list(languages).index(default_language),
        format_func=languages.get,
        key=model_scope + "_language",
    )
    if source_language is None:
        st.info(
            "De brontaal is onbekend of wordt niet ondersteund. Kies alleen Sumerisch of "
            "Akkadisch als de geselecteerde passage daadwerkelijk in die taal is geschreven."
        )
    input_format = st.selectbox(
        "Invoerformaat voor model",
        ["transliteration", "complex-transliteration", "cuneiform"],
        key=model_scope + "_input_format",
        help="Kies het formaat van de ongewijzigde bronpassage hierboven.",
    )
    model_path = st.text_input(
        "Lokaal modelpad",
        value=str(local_translation.default_model_dir()),
        key=_key(project_key, "model_dir"),
        help="Map met lokale gewichten; standaard via ISC_HELWIGII_TRANSLATION_MODEL.",
    )
    st.caption(f"Model: {local_translation.MODEL_ID}")
    model_dir = None
    try:
        if model_path.strip():
            model_dir = Path(model_path).expanduser()
            status = local_translation.model_status(model_dir)
        else:
            status = {"installed": False, "error": "Vul een lokaal modelpad in."}
    except (ValueError, OSError) as exc:
        status = {"installed": False, "error": str(exc)}
    available = status["installed"] and not status.get("error")
    if available:
        st.info("Modelbestanden aangetroffen. Volledige verificatie gebeurt bij het genereren.")
        if status.get("revision"):
            st.text(f"Modelrevisie: {status['revision']}")
    else:
        st.warning(status.get("error") or "Het lokale model is nog niet geïnstalleerd.")
        st.caption("Installeer het model met:")
        st.code(
            "isc-helwigii download-model " + (shlex.quote(str(model_dir)) if model_dir else "PATH"),
            language=None,
        )
    source = edition.get("text", "")
    valid = start is not None and bool(source.strip()) and source[start:end] == passage
    can_generate = valid and available and source_language is not None and target == "en"
    if st.button(
        "Lokaal vertaalvoorstel maken",
        key=scope + "_model_propose",
        disabled=not can_generate,
    ):
        if not can_generate:
            st.error("Controleer de bronpassage, talen en lokale modelbestanden.")
            return
        try:
            with st.spinner("Lokaal vertaalvoorstel maken; modelbestanden worden geverifieerd…"):
                result = local_translation.propose_model_translation(
                    store,
                    edition_id,
                    model_dir=model_dir,
                    actor=actor,
                    start=start,
                    end=end,
                    source_language=source_language,
                    input_format=input_format,
                    target_language=target,
                )
        except (ValueError, OSError) as exc:
            st.error(f"Lokaal vertaalvoorstel niet gemaakt: {exc}")
        else:
            st.session_state[scope + "_review_annotation"] = result["annotation_id"]
            st.session_state[scope + "_notice"] = (
                "Lokaal modelvoorstel opgeslagen; in afwachting van beoordeling. "
                "Controleer het voorstel voordat je een besluit vastlegt."
            )
            st.rerun()


def translation_page(store, actor, choose_artifact):
    st.header("Vertalen")
    st.write("Werk per broneditie en doeltaal aan een controleerbare vertaling.")
    st.info(
        "Voer zelf een vertaling of een vertaling uit een bron in, of laat een lokaal model "
        "een experimenteel voorstel maken. Ieder voorstel wordt in afwachting opgeslagen "
        "en vraagt een afzonderlijke beoordeling."
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
    target_key = _key(project_key, edition_id, "target")
    st.session_state.setdefault(target_key, "nl")
    target = st.text_input(
        "Doeltaal",
        key=target_key,
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
    st.session_state.setdefault(scope + "_passage", source)
    passage = st.text_area(
        "Ongewijzigde bronpassage",
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
                f"…{source[max(0, position - 30) : position]}"
                f"⟦{passage}⟧{source[position + len(passage) : position + len(passage) + 30]}…"
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
    _model_proposal(store, actor, edition, target, project_key, passage, start, end)
    st.subheader("Handmatig voorstel")
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
        _recheck_proposal(store, annotation, edition, actor, scope)
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
