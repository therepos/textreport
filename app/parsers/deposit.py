import re
from typing import List, Dict, Any
from . import register

MONTH = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def _date(d, m, year): return f"{year:04d}-{MONTH[m.upper()]:02d}-{int(d):02d}"

@register("deposit")
class _:
    @staticmethod
    def detect(text: str) -> bool:
        return bool(re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", text, re.I))

    @staticmethod
    def parse(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines() if ln.strip()]

        txns, cur = [], None
        date_re = re.compile(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.I)
        amt_re  = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})")

        for ln in lines:
            m = date_re.match(ln)
            if m:
                if cur and ('amount' in cur): txns.append(cur)
                day, mon = m.group(1), m.group(2)
                rest = ln[m.end():].strip()
                cur = {"date": _date(day, mon, year), "payee": rest, "memo": ""}
                continue

            if not cur: continue

            amts = amt_re.findall(ln)
            if len(amts) == 2:
                withdraw, deposit = [float(a.replace(',', '')) for a in amts]
                cur["amount"] = deposit - withdraw   # +deposit / -withdrawal
            elif len(amts) == 1:
                cur["amount"] = float(amts[0].replace(',', ''))
            else:
                cur["memo"] = (cur["memo"] + " " + ln).strip()

        if cur and ('amount' in cur): txns.append(cur)
        # normalize CC-style fields for the rest of the app
        for t in txns:
            t["credit"] = t["amount"] > 0
        return txns
