"""Stallion status corrections and registry scope (crossr_core.stallion_status)."""

from crossr_core import stallion_status as ss

TABLE = {"WOOTTON BASSETT": {"status": "deceased", "foal_year": 2008, "note": "died"},
         "SOME SIRE": {"status": "pensioned", "foal_year": None, "note": None}}


def test_override_beats_the_card():
    assert ss.off_duty("Wootton Bassett (GB)", 2008, TABLE)
    assert ss.off_duty("Some Sire", None, TABLE)
    assert not ss.off_duty("Into Mischief", 2005, TABLE)


def test_namesake_with_another_year_is_not_affected():
    assert not ss.off_duty("Wootton Bassett", 2023, TABLE)
    assert ss.off_duty("Wootton Bassett", None, TABLE)  # no year: the recorded horse


def test_scope_defaults_to_north_america(monkeypatch):
    monkeypatch.delenv("CROSSR_STALLION_SCOPE", raising=False)
    assert ss.scope() == "north_america"
    monkeypatch.setenv("CROSSR_STALLION_SCOPE", "World")
    assert ss.scope() == "world"
    monkeypatch.setenv("CROSSR_STALLION_SCOPE", "mars")
    assert ss.scope() == "north_america"


def _watch():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).parents[1] / "scripts" / "stallion_news_watch.py"
    spec = importlib.util.spec_from_file_location("stallion_news_watch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NAMES = {"WAR FRONT": ("War Front", 2002), "FROSTED": ("Frosted", 2012), "FROSTED OVER": ("Frosted Over", 2021),
         "TAPIT": ("Tapit", 2001)}


def story(title):
    return {"title": title, "link": "https://x/" + title.replace(" ", "-"), "published": ""}


def test_news_headlines_become_suggestions():
    w = _watch()
    found = w.matches([story("War Front Pensioned at Claiborne"), story("Champion Sire Frosted Dies at 14")], NAMES)
    assert [(f["name"], f["status"]) for f in found] == [("War Front", "pensioned"), ("Frosted", "deceased")]


def test_news_without_a_status_word_or_stallion_is_ignored():
    w = _watch()
    assert w.matches([story("Frosted Over Wins the Jerome"), story("Tapit Filly Tops Keeneland Book 2")], NAMES) == []
    assert w.matches([story("Trainer Dies at 80")], NAMES) == []


def test_longest_name_wins():
    w = _watch()
    (f,) = w.matches([story("Frosted Over Euthanized After Injury")], NAMES)
    assert f["name"] == "Frosted Over" and f["status"] == "deceased"
