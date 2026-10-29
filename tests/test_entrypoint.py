import pytest

from app.__main__ import PENDING, main


def test_known_commands_report_their_ticket(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ingest"]) == 2
    assert PENDING["ingest"] in capsys.readouterr().out


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["bogus"])
