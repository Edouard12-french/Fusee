"""Données de marché réelles (gratuites, sans clé), indicateurs et backtests de stratégies.

Sources : Yahoo Finance (actions, ETF, indices, crypto, devises : AAPL, CW8.PA, ^FCHI, BTC-EUR, EURUSD=X…),
avec Stooq en secours pour les actions. Les résultats passés ne préjugent pas des résultats futurs."""
import csv
import io
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_cache: dict[str, tuple[float, dict]] = {}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Fusee/1.0"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def _yahoo(symbol: str, days: int) -> dict:
    rng = "5y" if days > 730 else "2y" if days > 365 else "1y" if days > 180 else "6mo"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?range={rng}&interval=1d&includeAdjustedClose=true")
    res = json.loads(_get(url))["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    rows = [(datetime.fromtimestamp(t, timezone.utc).date().isoformat(), float(c))
            for t, c in zip(ts, adj) if c is not None]
    meta = res.get("meta", {})
    return {"symbol": symbol, "currency": meta.get("currency", ""), "name": meta.get("longName") or meta.get("shortName", ""),
            "source": "Yahoo Finance", "dates": [r[0] for r in rows], "closes": [r[1] for r in rows],
            "last_price": meta.get("regularMarketPrice") or (rows[-1][1] if rows else None)}


def _stooq(symbol: str) -> dict:
    s = symbol.lower() if "." in symbol else f"{symbol.lower()}.us"
    data = _get(f"https://stooq.com/q/d/l/?s={urllib.parse.quote(s)}&i=d").decode()
    rows = [(r["Date"], float(r["Close"])) for r in csv.DictReader(io.StringIO(data)) if r.get("Close") not in (None, "", "N/D")]
    if not rows:
        raise ValueError("symbole inconnu")
    return {"symbol": symbol, "currency": "", "name": "", "source": "Stooq", "dates": [r[0] for r in rows],
            "closes": [r[1] for r in rows], "last_price": rows[-1][1]}


def history(symbol: str, days: int = 365) -> dict:
    """Historique quotidien (clôtures ajustées). Cache de 15 minutes."""
    symbol = symbol.strip().upper()
    key = f"{symbol}:{days > 365}"
    if key in _cache and time.time() - _cache[key][0] < 900:
        h = _cache[key][1]
    else:
        errors = []
        for fetch in (lambda: _yahoo(symbol, days), lambda: _stooq(symbol)):
            try:
                h = fetch()
                if len(h["closes"]) >= 2:
                    break
            except Exception as e:  # noqa: BLE001
                errors.append(str(e)[:120])
        else:
            raise RuntimeError(f"pas de données pour {symbol} ({' | '.join(errors)}). Exemples de symboles : "
                               "AAPL, MC.PA, CW8.PA, ^FCHI, BTC-EUR")
        _cache[key] = (time.time(), h)
    n = min(len(h["closes"]), max(days, 2))
    return {**h, "dates": h["dates"][-n:], "closes": h["closes"][-n:]}


def last_price(symbol: str) -> float:
    h = history(symbol, 30)
    return float(h["last_price"] or h["closes"][-1])


# --- indicateurs ------------------------------------------------------------------
def sma(xs: list[float], n: int) -> list[float | None]:
    out, s = [], 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def rsi(xs: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    gains = [max(xs[i] - xs[i - 1], 0) for i in range(1, len(xs))]
    losses = [max(xs[i - 1] - xs[i], 0) for i in range(1, len(xs))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(xs)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def max_drawdown(values: list[float]) -> float:
    peak, mdd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return mdd


def _pct(a: float, b: float) -> float | None:
    return round(100 * (b / a - 1), 2) if a else None


def analyze(symbol: str, days: int = 365) -> dict:
    h = history(symbol, max(days, 260))
    c = h["closes"]
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)) * math.sqrt(252)
    last = c[-1]
    s20, s50, s200, r14 = sma(c, 20)[-1], sma(c, 50)[-1], sma(c, 200)[-1], rsi(c)[-1]
    year = c[-252:] if len(c) >= 252 else c
    trend = ("haussière" if s50 and s200 and last > s50 > s200 else
             "baissière" if s50 and s200 and last < s50 < s200 else "neutre / indécise")
    return {
        "symbole": h["symbol"], "nom": h["name"], "devise": h["currency"], "source": h["source"],
        "date": h["dates"][-1], "dernier_prix": round(float(h["last_price"] or last), 4),
        "variation_1j_pct": _pct(c[-2], last), "variation_1m_pct": _pct(c[-22], last) if len(c) > 22 else None,
        "variation_1an_pct": _pct(year[0], last), "plus_haut_1an": round(max(year), 4), "plus_bas_1an": round(min(year), 4),
        "moyenne_20j": s20 and round(s20, 4), "moyenne_50j": s50 and round(s50, 4), "moyenne_200j": s200 and round(s200, 4),
        "rsi_14": r14 and round(r14, 1), "volatilite_annuelle_pct": round(100 * vol, 1),
        "pire_baisse_1an_pct": round(100 * max_drawdown(year), 1), "tendance": trend,
    }


# --- backtests ----------------------------------------------------------------------
STRATEGIES = ("achat_conservation", "croisement_moyennes", "rsi", "dca")


def backtest(symbol: str, strategy: str, days: int = 730, capital: float = 1000.0, fast: int = 20, slow: int = 50,
             rsi_low: float = 30, rsi_high: float = 70, monthly: float = 100.0, fee_pct: float = 0.2) -> dict:
    """Rejoue une stratégie sur l'historique réel. Frais appliqués à chaque achat/vente."""
    if strategy not in STRATEGIES:
        raise ValueError(f"stratégie inconnue ; choix : {', '.join(STRATEGIES)}")
    h = history(symbol, days)
    c, d = h["closes"], h["dates"]
    if len(c) < 30:
        raise ValueError("historique trop court")
    fee = fee_pct / 100
    cash, units, trades, values, invested, in_market_days = capital, 0.0, 0, [], capital, 0
    if strategy == "dca":
        cash, invested = 0.0, 0.0
    fs, ss, rs = sma(c, fast), sma(c, slow), rsi(c)

    def buy(i: int) -> None:
        nonlocal cash, units, trades
        if cash > 0:
            units += cash * (1 - fee) / c[i]
            cash, trades = 0.0, trades + 1

    def sell(i: int) -> None:
        nonlocal cash, units, trades
        if units > 0:
            cash += units * c[i] * (1 - fee)
            units, trades = 0.0, trades + 1

    for i in range(len(c)):
        if strategy == "achat_conservation" and i == 0:
            buy(i)
        elif strategy == "croisement_moyennes" and fs[i] is not None and ss[i] is not None:
            buy(i) if fs[i] > ss[i] else sell(i)
        elif strategy == "rsi" and rs[i] is not None:
            if rs[i] < rsi_low:
                buy(i)
            elif rs[i] > rsi_high:
                sell(i)
        elif strategy == "dca" and i % 21 == 0:  # environ une fois par mois de bourse
            cash += monthly
            invested += monthly
            buy(i)
        in_market_days += units > 0
        values.append(cash + units * c[i])

    final = values[-1]
    years = max(len(c) / 252, 1 / 252)
    bh = c[-1] / c[0] - 1
    total = final / invested - 1 if invested else 0
    return {
        "symbole": h["symbol"], "strategie": strategy, "periode": f"{d[0]} → {d[-1]}", "jours_de_bourse": len(c),
        "investi": round(invested, 2), "valeur_finale": round(final, 2), "rendement_total_pct": round(100 * total, 2),
        "rendement_annuel_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if total > -1 else -100.0,
        "pire_baisse_pct": round(100 * max_drawdown(values), 2), "nombre_ordres": trades,
        "temps_investi_pct": round(100 * in_market_days / len(c), 1),
        "comparaison_achat_conservation_pct": round(100 * bh, 2),
        "frais_par_ordre_pct": fee_pct,
        "avertissement": "Performance passée, frais simplifiés, sans impôts : ne garantit rien pour l'avenir.",
    }
