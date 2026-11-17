from brvm import glossary


def test_glossary_is_sorted_and_searchable():
    names = list(glossary.TERMS)
    assert len(names) == len(set(names)) >= 20
    assert all(len(v) > 20 and v.endswith(".") for v in glossary.TERMS.values())
    assert "PER" in glossary.search("per") and "SGI" in glossary.search("intermédiaire")
    assert glossary.search("") == glossary.TERMS and glossary.search("zzz") == {}
