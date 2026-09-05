from importlib.metadata import distribution

from isc_helwigii.cli import main


def test_console_entrypoint_loads_packaged_main() -> None:
    """Catches console metadata that points outside the installable package."""
    entries = [
        entry
        for entry in distribution("isc-helwigii").entry_points
        if entry.group == "console_scripts"
    ]

    assert [(entry.name, entry.value) for entry in entries] == [
        ("isc-helwigii", "isc_helwigii.cli:main")
    ]
    assert entries[0].load() is main
