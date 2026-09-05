import json

from isc_helwigii.cli import main


def test_cli_full_offline_lifecycle(tmp_path, capsys):
    project = tmp_path / "project.db"
    assert main(["init", str(project)]) == 0
    assert main(["demo", str(project)]) == 0
    capsys.readouterr()
    assert main(["list", str(project)]) == 0
    artifacts = json.loads(capsys.readouterr().out)
    assert len(artifacts) == 3
    assert main(["dossier", str(project), artifacts[0]["id"]]) == 0
    dossier = json.loads(capsys.readouterr().out)
    assert dossier["editions"][0]["record"]["synthetic"] is True
    bundle = tmp_path / "project.zip"
    assert main(["export", str(project), str(bundle)]) == 0
    assert main(["restore", str(bundle), str(tmp_path / "restored.db")]) == 0


def test_bad_input_reports_error_without_traceback(tmp_path, capsys):
    assert main(["list", str(tmp_path / "missing.db")]) == 2
    assert "initialize" in capsys.readouterr().err
