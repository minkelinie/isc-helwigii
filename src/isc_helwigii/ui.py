"""Launch with isc-helwigii start PROJECT, bound to localhost by default."""

import argparse
import os
from pathlib import Path

import streamlit as st

from isc_helwigii.store import ResearchStore
from isc_helwigii.ui_pages import PAGES


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project")
    args, _ = parser.parse_known_args()
    st.set_page_config(page_title="I.S.C. Helwigii · onderzoek", page_icon="𒀭", layout="wide")
    st.title("𒀭 I.S.C. Helwigii")
    st.caption("Lokaal spijkerschriftonderzoek · van bron naar toetsbare hypothese")
    project = st.sidebar.text_input(
        "Projectbestand",
        value=args.project
        or os.environ.get("ISC_HELWIGII_PROJECT", str(Path.cwd() / "research.db")),
    )
    actor = st.sidebar.text_input("Onderzoeker", value="lokale onderzoeker")
    page = st.sidebar.radio("Werkruimte", list(PAGES))
    st.sidebar.caption(
        "Bronnen blijven behouden. Beoordelingen worden toegevoegd aan de historie. Onderzoekersnamen zijn lokale attributie, geen geverifieerde identiteit."
    )
    try:
        PAGES[page](ResearchStore(project), actor)
    except Exception as exc:
        # Keep the project usable after a rejected import or invalid form submission.
        st.error(f"Bewerking niet uitgevoerd: {exc}")


if __name__ == "__main__":
    main()
