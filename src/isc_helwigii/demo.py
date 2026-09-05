"""Small synthetic data for learning the workflow; never a scholarly source."""

from isc_helwigii.store import canonical


def seed_demo(store):
    records = [
        {
            "external_id": "DEMO-A",
            "title": "Synthetic witness A",
            "text": "water rises boat survives",
            "language": "demo",
            "synthetic": True,
            "period": "invented",
        },
        {
            "external_id": "DEMO-B",
            "title": "Synthetic witness B",
            "text": "water rises mountain survives",
            "language": "demo",
            "synthetic": True,
            "period": "invented",
        },
        {
            "external_id": "DEMO-C",
            "title": "Synthetic witness C",
            "text": "grain bread worker",
            "language": "demo",
            "synthetic": True,
            "period": "invented",
        },
    ]
    return store.import_records(
        canonical(records).encode(),
        records,
        source="synthetic-tutorial",
        license="CC0-1.0 (synthetic tutorial only)",
        adapter="demo-v1",
    )
