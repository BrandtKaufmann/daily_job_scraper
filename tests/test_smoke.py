"""Smoke tests \u2014 verify modules import and pure functions work."""
from datetime import date
from pathlib import Path

from src.scrapers.apple import _parse_posted as apple_parse
from src.scrapers.base import Job
from src.scrapers.riot import _extract_job_id as riot_extract_job_id
from src.scrapers.riot import _parse_listing_text as riot_parse_listing_text
from src.scrapers.riot import KEYWORDS as riot_keywords
from src.main import _apply_filters as apply_job_filters
from src.seen_store import SeenStore


def test_apple_parse_posted_with_prefix():
    assert apple_parse("Posted: Apr 15, 2026") == date(2026, 4, 15)


def test_apple_parse_posted_plain():
    assert apple_parse("Apr 15, 2026") == date(2026, 4, 15)


def test_apple_parse_posted_bad():
    assert apple_parse("") is None
    assert apple_parse("nonsense") is None


def test_seen_store_filters_duplicates(tmp_path: Path):
    store = SeenStore(path=tmp_path / "seen.json")
    jobs = [
        Job(company="Apple", job_id="A1", title="ML Engineer", location="Cupertino", url="https://apple.com/a1"),
        Job(company="Google", job_id="G1", title="Data Scientist", location="MTV", url="https://google.com/g1"),
    ]
    first = store.filter_new(jobs)
    assert len(first) == 2
    # Second pass with the same jobs yields nothing.
    second = store.filter_new(jobs)
    assert second == []
    # Adding a new job surfaces only it.
    jobs.append(Job(company="Apple", job_id="A2", title="Research Scientist", location="Austin", url="https://apple.com/a2"))
    third = store.filter_new(jobs)
    assert len(third) == 1 and third[0].job_id == "A2"


def test_seen_store_persists(tmp_path: Path):
    path = tmp_path / "seen.json"
    s1 = SeenStore(path=path)
    s1.filter_new([Job(company="Apple", job_id="X", title="t", location="", url="u")])
    s1.save()

    s2 = SeenStore(path=path)
    again = s2.filter_new([Job(company="Apple", job_id="X", title="t", location="", url="u")])
    assert again == []


def test_riot_extract_job_id_from_relative_url():
    assert riot_extract_job_id("https://www.riotgames.com/en/j/7412544") == "7412544"


def test_riot_extract_job_id_missing():
    assert riot_extract_job_id("https://www.riotgames.com/en/work-with-us/jobs") is None


def test_riot_parse_listing_text():
    parsed = riot_parse_listing_text(
        "Principal Machine Learning Engineer\nData\nRiot Operations & Support\nLos Angeles, USA"
    )
    assert parsed["title"] == "Principal Machine Learning Engineer"
    assert parsed["location"] == "Los Angeles, USA"
    assert parsed["team"] == "Data | Riot Operations & Support"


def test_riot_keyword_filter_matches_data_and_ml_titles():
    assert riot_keywords.search("Senior Data Engineer - Team Insights")
    assert riot_keywords.search("Principal Machine Learning Engineer")
    assert not riot_keywords.search("Art Director - Characters")


def test_main_filters_out_seniority_titles_and_non_us_locations():
    jobs = [
        Job(company="Riot Games", job_id="1", title="Data Scientist II", location="Los Angeles, USA", url="u1"),
        Job(company="Riot Games", job_id="2", title="Senior Data Scientist", location="Los Angeles, USA", url="u2"),
        Job(company="Google", job_id="3", title="Principal ML Engineer", location="Mountain View, CA, USA", url="u3"),
        Job(company="Google", job_id="7", title="Staff ML Engineer", location="Mountain View, CA, USA", url="u7"),
        Job(company="Google", job_id="8", title="Lead Data Scientist", location="New York, USA", url="u8"),
        Job(company="Apple", job_id="4", title="Data Scientist", location="London, UK", url="u4"),
        Job(company="Apple", job_id="5", title="Director, Applied AI", location="Austin, TX, USA", url="u5"),
        Job(company="Riot Games", job_id="9", title="Machine Learning Manager", location="Los Angeles, USA", url="u9"),
        Job(company="Google", job_id="6", title="Machine Learning Engineer", location="Seattle, US", url="u6"),
    ]
    filtered = apply_job_filters(jobs)
    assert [j.job_id for j in filtered] == ["1", "6"]


def test_main_filters_principle_spelling_and_requires_us_location():
    jobs = [
        Job(company="X", job_id="10", title="Principle Data Scientist", location="New York, USA", url="u10"),
        Job(company="X", job_id="11", title="Data Scientist", location="Remote", url="u11"),
        Job(company="X", job_id="13", title="Sr. Data Scientist", location="Seattle, USA", url="u13"),
        Job(company="X", job_id="12", title="Data Scientist", location="United States", url="u12"),
    ]
    filtered = apply_job_filters(jobs)
    assert [j.job_id for j in filtered] == ["12"]
