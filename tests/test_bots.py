from brvm import db
from brvm.bots import analyst, collector, exposures, signals, sources


def test_fingerprint_matches_syndicated_titles():
    a = collector.fingerprint("Sonatel : hausse de 10 % du résultat net - Agence Ecofin")
    b = collector.fingerprint("SONATEL: hausse de 10% du résultat net - Senego")
    assert a == b


def test_every_security_has_exposure():
    from brvm import universe

    missing = [t for t, *_ in universe.SECURITIES if t not in exposures.EXPOSURES]
    assert missing == []


def test_feeds_cover_factors_and_companies():
    feeds = sources.google_news_feeds()
    themes = {f["theme"] for f in feeds}
    assert "caoutchouc" in themes and "societe:SNTS" in themes


def test_keyword_analysis_company_and_factor():
    r = analyst.keyword_analysis(
        {"title": "Sonatel annonce une hausse record de son bénéfice", "content": "", "theme": "", "scope": ""}
    )
    assert r["impacts"]["SNTS"]["score"] == 1
    r2 = analyst.keyword_analysis(
        {"title": "Le caoutchouc naturel en forte baisse", "content": "", "theme": "caoutchouc", "scope": "Monde"}
    )
    assert r2["impacts"]["SPHC"]["score"] == -1


def test_analyze_and_signal_without_api_key(monkeypatch):
    monkeypatch.setattr(analyst.config, "ANTHROPIC_API_KEY", "")
    with db.session() as con:
        con.execute(
            "INSERT INTO news (url, fingerprint, title, source, query, published, content, scope, theme) "
            "VALUES ('u1','f1','SAPH : la production de caoutchouc progresse','test','', ?,'','CI','caoutchouc')",
            (db.now_utc(),),
        )
    r = analyst.analyze_pending()
    assert r["analyzed"] >= 1 and not r["ai_enabled"]
    s = signals.ticker_signals()
    assert s.loc["SPHC", "signal"] > 0


def test_ai_json_parsing():
    data = analyst._parse_json('```json\n[{"id": 1, "pertinent": false}]\n```')
    assert data[0]["id"] == 1


class _FakeBlock:
    type = "text"
    text = (
        '[{"id": 99, "pertinent": true, "resume": "R", "categorie": "exogène", "portee": "Monde",'
        ' "impacts": [{"ticker": "SPHC", "score": 3, "horizon": "moyen", "confiance": 0.8, "raison": "x"},'
        ' {"ticker": "XXXX", "score": 1}]}]'
    )


class _FakeClient:
    class messages:
        @staticmethod
        def create(**kwargs):
            assert "SPHC" in kwargs["messages"][0]["content"]
            return type("M", (), {"content": [_FakeBlock()]})()


def test_ai_analysis_clamps_scores_and_drops_unknown_tickers():
    out = analyst.ai_analysis(
        _FakeClient(), [{"id": 99, "title": "t", "source": "s", "published": "2026-10-28", "theme": "caoutchouc", "content": ""}]
    )
    assert out[99]["impacts"]["SPHC"]["score"] == 2
    assert "XXXX" not in out[99]["impacts"]


def test_bad_security_news_is_negative_for_sahel_banks():
    r = analyst.keyword_analysis(
        {
            "title": "Burkina Faso : nouvelles attaques, crise sécuritaire",
            "content": "",
            "theme": "sahel_securite",
            "scope": "UEMOA",
        }
    )
    assert r["impacts"]["BOABF"]["score"] == -1


def test_alias_matching_uses_word_boundaries():
    r = analyst.keyword_analysis(
        {"title": "Sonatel publie ses résultats du troisième trimestre en hausse", "content": "", "theme": "", "scope": ""}
    )
    assert "SNTS" in r["impacts"]
    assert "ONTBF" not in r["impacts"] and "SEMC" not in r["impacts"]
