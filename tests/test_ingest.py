import pytest

from isc_helwigii.ingest import parse_atf, parse_native, parse_oracc


def test_native_preserves_fields_and_rejects_duplicate_identifiers():
    assert parse_native(b'[{"external_id":"A","period":"unknown"}]')[0]["period"] == "unknown"
    with pytest.raises(ValueError):
        parse_native(b'[{"external_id":"A"},{"external_id":"A"}]')


def test_atf_preserves_damage_and_languages():
    records = parse_atf(
        b"&P000001 = Synthetic\n#atf: lang akk\n@obverse\n1. [a]-bu x\n2. ...\n&P000002 = Other\n#atf: lang sux\n1. lugal\n"
    )
    assert records[0]["text"] == "[a]-bu x\n..."
    assert records[0]["language"] == "akk"
    assert records[0]["lines"][0]["label"] == "1"
    assert records[0]["lines"][0]["surface"] == "obverse"
    assert records[1]["language"] == "sux"
    with pytest.raises(ValueError):
        parse_atf(b"1. orphan line")


def test_oracc_catalogue_is_not_misread_as_edition():
    records = parse_oracc(
        b'{"type":"catalogue","project":"test","members":{"P1":{"designation":"A","period":"OB","provenience":"Ur"}}}'
    )
    assert records[0]["external_id"] == "P1"
    assert records[0]["text"] == ""
    assert records[0]["provenience"] == "Ur"
    with pytest.raises(ValueError, match="catalogue"):
        parse_oracc(b'{"type":"corpus","members":{"P1":"corpusjson/P1.json"}}')
