from datetime import date

from brvm.data import sika


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Session:
    def __init__(self):
        self.calls = 0

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls += 1
        return _Resp({"lst": [{"Date": "27/10/2026", "Open": 4600, "High": 4750, "Low": 4580, "Close": 4700, "Volume": 1200},
                              {"Date": "28/10/2026", "Open": 4700, "High": 4800, "Low": 4650, "Close": 4760, "Volume": 900}]})


def test_fetch_history_windows_and_dedup():
    s = _Session()
    rows = sika.fetch_history("SNTS.sn", date(2026, 1, 1), date(2026, 10, 28), session=s, delay=0)
    assert s.calls >= 4                      # fenêtres de 88 jours
    assert [r[0] for r in rows] == ["2026-10-27", "2026-10-28"]   # doublons des fenêtres supprimés
    assert rows[-1][4] == 4760


def test_nodata_returns_empty(monkeypatch):
    class S(_Session):
        def post(self, *a, **k):
            return _Resp({"error": "nodata"})
    assert sika.fetch_period(S(), "XXXX.ci", date(2026, 1, 1), date(2026, 2, 1)) == []
