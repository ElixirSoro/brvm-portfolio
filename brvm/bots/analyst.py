"""Bot analyste : lit les articles collectés et note leur impact probable sur chaque action.

Avec une clé API Claude : résumé, catégorie, portée, actions touchées, score −2..+2, horizon, confiance.
Sans clé : score par mots-clés (noms de sociétés, facteurs, mots de hausse/baisse), plus grossier.
"""
from __future__ import annotations

import json
import re
import unicodedata

from .. import config, db
from . import exposures

SYSTEM = """Tu es analyste actions sur la BRVM (Bourse régionale des valeurs mobilières, UEMOA).
Pour chaque article, tu évalues son impact probable sur le cours des actions cotées à la BRVM.
Sois sobre : la plupart des articles n'ont qu'un impact faible ou nul. N'invente aucun fait absent de l'article.
Échelle : +2 très favorable, +1 favorable, 0 neutre, −1 défavorable, −2 très défavorable.
Horizon : "court" (jours-semaines), "moyen" (mois), "long" (années). Confiance : 0 à 1.
Catégorie : "endogène" si l'information concerne directement la société (résultats, dividende, AG, gouvernance,
contrat, sinistre, dirigeants, opération sur titres) ; "exogène" sinon (macro, matières premières, politique, taux, secteur).
Portée : "Société", "Côte d'Ivoire", "UEMOA", "Afrique" ou "Monde".
Réponds UNIQUEMENT par un tableau JSON, un objet par article, dans l'ordre reçu :
[{"id": <id>, "pertinent": true/false, "resume": "<2 phrases max, en français>", "categorie": "...", "portee": "...",
  "impacts": [{"ticker": "<ticker BRVM>", "score": <entier -2..2>, "horizon": "...", "confiance": <0..1>, "raison": "<1 phrase>"}]}]
Ne mets dans "impacts" que les actions réellement concernées (aucune si l'article n'est pas pertinent)."""

# racines de mots (comptées comme sous-chaînes, sans accents)
POS_WORDS = ["hausse", "progress", "augment", "record", "rebond", "bondi", "benefice", "croissance", "dividende",
             "amelior", "releve", "grimpe", "contrat", "accord", "acquisition", "rise", "surge", "gain", "jump"]
NEG_WORDS = ["baisse", "recul", "chute", "chut", "diminu", "perte", "deficit", "greve", "sanction", "suspen", "crise",
             "coup d'etat", "attaque", "defaut", "degrad", "plonge", "amende", "litige", "incendie", "fall", "drop", "plunge"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _direction(text: str) -> int:
    t = _norm(text)
    pos = sum(t.count(_norm(w)) for w in POS_WORDS)
    neg = sum(t.count(_norm(w)) for w in NEG_WORDS)
    return (pos > neg) - (neg > pos)


def keyword_analysis(article: dict) -> dict:
    text = f"{article['title']} {article.get('content') or ''}"
    nt = _norm(text)
    direction = _direction(text)
    impacts = {}
    for t, e in exposures.EXPOSURES.items():
        if any(re.search(r"(?<![a-z0-9])" + re.escape(_norm(a)) + r"(?![a-z0-9])", nt) for a in e["aliases"]):
            impacts[t] = {"score": direction, "confidence": 0.35, "horizon": "court",
                          "rationale": "Société citée dans l'article (score par mots-clés)."}
    theme = article.get("theme") or ""
    if theme in exposures.FACTORS and direction:
        for t, sign in exposures.tickers_for_factor(theme).items():
            if sign and t not in impacts:
                impacts[t] = {"score": direction * sign, "confidence": 0.2, "horizon": "moyen",
                              "rationale": f"Exposé au facteur « {exposures.FACTORS[theme]['label']} » (mots-clés)."}
    category = "endogène" if any(v["confidence"] >= 0.35 for v in impacts.values()) else "exogène"
    return {"summary": None, "category": category, "scope": article.get("scope") or "", "impacts": impacts,
            "method": "mots-clés"}


def _client():
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("["), text.rfind("]")
    return json.loads(text[start:end + 1])


def ai_analysis(client, batch: list[dict]) -> dict[int, dict]:
    articles = "\n\n".join(
        f"[id {a['id']}] {a['title']}\nSource : {a['source']} · {a['published'][:10]} · thème de recherche : {a['theme']}\n"
        f"{(a.get('content') or '')[:800]}" for a in batch)
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL, max_tokens=4000, system=SYSTEM,
        messages=[{"role": "user", "content": f"Carte d'exposition des actions :\n{exposures.context_for_ai()}\n\n"
                                              f"Articles à analyser :\n\n{articles}"}])
    data = _parse_json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
    out = {}
    valid = set(exposures.EXPOSURES)
    for item in data:
        impacts = {}
        if item.get("pertinent"):
            for imp in item.get("impacts", []):
                t = str(imp.get("ticker", "")).upper()
                if t in valid:
                    impacts[t] = {"score": max(-2, min(2, int(imp.get("score", 0)))),
                                  "confidence": float(imp.get("confiance", 0.5)),
                                  "horizon": imp.get("horizon", "moyen"), "rationale": imp.get("raison", "")}
        out[int(item["id"])] = {"summary": item.get("resume"), "category": item.get("categorie"),
                                "scope": item.get("portee"), "impacts": impacts, "method": "IA"}
    return out


def analyze_pending(limit: int = 120, batch_size: int = 10, progress=None) -> dict:
    pending = db.df("SELECT id, title, source, published, content, theme, scope FROM news WHERE analyzed=0 "
                    "ORDER BY published DESC LIMIT ?", (limit,)).to_dict("records")
    client = _client()
    done, ai, errors = 0, 0, []
    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        results: dict[int, dict] = {}
        if client:
            try:
                results = ai_analysis(client, batch)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:200])
        for a in batch:
            r = results.get(a["id"]) or keyword_analysis(a)
            ai += r["method"] == "IA"
            with db.session() as con:
                con.execute("UPDATE news SET analyzed=1, summary=?, category=?, scope=COALESCE(NULLIF(?, ''), scope), method=? "
                            "WHERE id=?", (r["summary"], r["category"], r["scope"], r["method"], a["id"]))
                con.execute("DELETE FROM impacts WHERE news_id=?", (a["id"],))
                con.executemany("INSERT INTO impacts VALUES (?,?,?,?,?,?)",
                                [(a["id"], t, v["score"], v["horizon"], v["confidence"], v["rationale"])
                                 for t, v in r["impacts"].items()])
            done += 1
        if progress:
            progress(min(1.0, (i + batch_size) / max(len(pending), 1)), "")
    return {"analyzed": done, "by_ai": ai, "errors": errors, "ai_enabled": client is not None}
