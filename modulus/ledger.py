"""SQLite journal: every verdict, every order, every outcome. The calibration source of truth."""
from __future__ import annotations
import json, os, sqlite3, time

SCHEMA = """
create table if not exists verdicts(
  id integer primary key, ts integer, ticker text, symbol text, address text, action text,
  raw_p real, confidence real, dissent real, price real, payload text,
  resolved_ts integer, exit_price real, outcome integer);
create table if not exists orders(
  id integer primary key, ts integer, verdict_id integer, mode text, side text, usd real,
  status text, ref text, detail text);
create table if not exists elder_votes(
  verdict_id integer, elder text, direction integer, p real, outcome integer);
"""


class Ledger:
    def __init__(self, path="data/modulus.sqlite"):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def record_verdict(self, v, price) -> int:
        cur = self.db.execute(
            "insert into verdicts(ts,ticker,symbol,address,action,raw_p,confidence,dissent,price,payload)"
            " values(?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), v.ticker, v.symbol, v.address, v.action, v.raw_p, v.confidence, v.dissent,
             price, json.dumps(v.as_dict(), default=str)))
        vid = cur.lastrowid
        for o in v.opinions:
            if o.direction:
                self.db.execute("insert into elder_votes values(?,?,?,?,null)", (vid, o.elder, o.direction, o.p))
        self.db.commit()
        return vid

    def record_order(self, vid, mode, side, usd, status, ref="", detail=None):
        self.db.execute("insert into orders(ts,verdict_id,mode,side,usd,status,ref,detail) values(?,?,?,?,?,?,?,?)",
                        (int(time.time()), vid, mode, side, usd, status, ref, json.dumps(detail or {}, default=str)))
        self.db.commit()

    def spent_today(self) -> float:
        r = self.db.execute("select coalesce(sum(usd),0) from orders where ts>? and status in ('FINISHED','FILLED','SUBMITTED')",
                            (int(time.time()) - 86400,)).fetchone()
        return float(r[0])

    def open_verdicts(self, older_than_s=6 * 3600):
        return self.db.execute("select id,address,action,price from verdicts where outcome is null and action in ('BUY','SELL') and ts<?",
                               (int(time.time()) - older_than_s,)).fetchall()

    def resolve(self, vid, exit_price):
        row = self.db.execute("select action,price from verdicts where id=?", (vid,)).fetchone()
        if not row or not row[1]:
            return
        up = exit_price > row[1]
        outcome = int(up if row[0] == "BUY" else not up)
        self.db.execute("update verdicts set resolved_ts=?,exit_price=?,outcome=? where id=?",
                        (int(time.time()), exit_price, outcome, vid))
        self.db.execute("update elder_votes set outcome = case when (direction>0)=? then 1 else 0 end where verdict_id=?",
                        (int(up), vid))
        self.db.commit()

    def pairs(self):
        return [(p, y) for p, y in self.db.execute("select raw_p,outcome from verdicts where outcome is not null")]

    def elder_pairs(self):
        out = {}
        for e, p, y in self.db.execute("select elder,p,outcome from elder_votes where outcome is not null"):
            out.setdefault(e, []).append((p, y))
        return out
