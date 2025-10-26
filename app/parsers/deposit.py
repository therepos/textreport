import re
from typing import List, Dict, Any
from . import register

MONTH = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def _date(d, m, year): return f"{year:04d}-{MONTH[m.upper()]:02d}-{int(d):02d}"

_money = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})")

@register("deposit")
class _:
    @staticmethod
    def detect(text: str) -> bool:
        return bool(re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", text, re.I))

    @staticmethod
    def parse_from_table(rows: List[Dict[str, str]], year: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in rows:
            m = re.match(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", r["date"], re.I)
            if not m:
                continue
            day, mon = m.group(1), m.group(2)
            w = _money.search(r.get("withdrawal","") or "")
            d = _money.search(r.get("deposit","") or "")
            if not (w or d):
                continue
            amt = float((d or w).group(1).replace(",", ""))
            credit = bool(d)  # deposit column → credit
            out.append({
                "date": _date(day, mon, year),
                "payee": r.get("desc","").strip(),
                "memo": "",
                "amount": amt,           # absolute; main.py will sign
                "credit": credit
            })
        return out
