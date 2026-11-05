"""The collection switch stays off, and launchd does not schedule scrapers."""

import pytest

from crossr_pipeline.collection import (
    COLLECTION_ENABLED,
    LAUNCHD_COLLECTION_LABELS,
    MAC_ONLY_COLLECTION_LABELS,
    refuse_if_off,
)
from crossr_pipeline.launchd import plists


def test_collection_switch_is_off():
    assert COLLECTION_ENABLED is False


def test_refuse_exits_zero_and_names_the_switch(capsys):
    with pytest.raises(SystemExit) as exc:
        refuse_if_off("Jockey Club Report of Mares Bred")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Jockey Club Report of Mares Bred is off" in out
    assert "COLLECTION_ENABLED = False" in out
    assert "Collected data is unchanged" in out


def test_install_launchd_omits_collection_agents():
    written = plists("railway", "/usr/bin/python3")
    labels = set(written)
    assert labels.isdisjoint(LAUNCHD_COLLECTION_LABELS)
    assert labels.isdisjoint(MAC_ONLY_COLLECTION_LABELS)
    for kept in (
        "com.crossr.pipeline.audit",
        "com.crossr.pipeline.push",
        "com.crossr.pipeline.precompute",
        "com.crossr.pipeline.weekly",
        "com.crossr.pipeline.sales-import",
    ):
        assert kept in labels
