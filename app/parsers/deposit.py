import re
from typing import List, Dict, Any
from . import register

MONTH = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def _date(d, m, year): return f"{year:04d}-{MONTH[m.upper()]:02d}-{int(d):02d}"

DATE_RE   = re.compile(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.I)
AMT_LINE  = re.compile(r"^([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})(?:\s+[0-9]{1,3}(?:,[0-9]{3})*\.\d{2})?$")  # amount [balance]
MONEY     = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})")

DEPOSIT_HINT  = re.compile(r"\b(SALARY|INCOMING PAYNOW|INTEREST EARNED|DEPOSIT|FROM:)\b", re.I)
WITHDRAW_HINT = re.compile(r"\b(CASH WITHDRAWAL|FUNDS TRANSFER|TOP-UP TO PAYLAH|TO:|GIRO DEBIT|PAYNOW TRANSFER\s+TO)\b", re.I)

@register("deposit")
class _:
    @staticmethod
    def detect(text: str) -> bool:
        return bool(re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", text, re.I))

    @staticmethod
    def parse(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines() if ln.strip()]

        # bound section
        start = next((i+1 for i,l in enumerate(lines)
                      if re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", l, re.I)), None)
        if start is None: return []
        stop = next((j for j in range(start, len(lines))
                     if re.search(r"^(TOTALS?|BALANCE CARRIED FORWARD|MESSAGE FOR YOU|CLOSING BALANCE)", lines[j], re.I)),
                    len(lines))

        txns: List[Dict[str, Any]] = []
        cur: Dict[str, Any] | None = None
        have_amt = False

        def flush():
            nonlocal cur, have_amt
            if cur and have_amt and "amount" in cur and "credit" in cur:
                cur["payee"] = re.sub(r"\s{2,}", " ", cur.get("payee","")).strip()
                cur["memo"]  = re.sub(r"\s{2,}", " ", cur.get("memo","")).strip()
                cur["amount"] = abs(float(cur["amount"]))
                txns.append(cur)
            cur, have_amt = None, False

        for ln in lines[start:stop]:
            dm = DATE_RE.match(ln)
            if dm:
                flush()
                d, m = dm.group(1), dm.group(2)
                desc = ln[dm.end():].strip()
                cur = {"date": _date(d, m, year), "payee": desc, "memo": ""}
                continue

            if not cur:
                continue

            # amount may appear alone or followed by balance
            if AMT_LINE.match(ln) and not have_amt:
                amt = float(MONEY.findall(ln)[0].replace(",", ""))  # first number is the txn amount
                cur["amount"] = amt
                probe = (cur.get("payee","") + " " + cur.get("memo","")).upper()
                if DEPOSIT_HINT.search(probe):      cur["credit"] = True
                elif WITHDRAW_HINT.search(probe):   cur["credit"] = False
                else:
                    # default: treat FAST/Incoming/Interest/Salary as deposit; TOP-UP/To: as withdrawal
                    cur["credit"] = bool(re.search(r"\b(INCOMING|SALARY|INTEREST|FROM:)\b", probe, re.I))
                have_amt = True
                continue

            # keep building memo/desc lines
            cur["memo"] = (cur.get("memo","") + " " + ln).strip()

        flush()
        return txns
