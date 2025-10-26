import re
from typing import List, Dict, Any
from . import register

MONTH = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,
         'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}

def _date(d, m, year): return f"{year:04d}-{MONTH[m.upper()]:02d}-{int(d):02d}"

@register("deposit")
class _:
    @staticmethod
    def detect(text: str) -> bool:
        return bool(re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", text, re.I))

    @staticmethod
    def parse(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
        # Normalize lines and trim to the section after the header
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines()]
        lines = [ln for ln in lines if ln]  # drop empties

        # Bound the table section (start after header; stop at next section/footer)
        start = None
        for i, ln in enumerate(lines):
            if re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", ln, re.I):
                start = i + 1
                break
        if start is None:
            return []

        stop = len(lines)
        for j in range(start, len(lines)):
            if re.search(r"^(TOTALS?|CLOSING BALANCE|SUMMARY OF CHARGES|INTEREST EARNED)", lines[j], re.I):
                stop = j
                break

        date_re = re.compile(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.I)
        money_re = re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})\b")

        txns: List[Dict[str, Any]] = []
        cur: Dict[str, Any] | None = None

        def flush():
            nonlocal cur
            if not cur:
                return
            # Only finalize if we got an amount decision
            if "amount" in cur and "credit" in cur:
                cur["memo"] = cur.get("memo", "").strip()
                cur["payee"] = cur.get("payee", "").strip()
                txns.append(cur)
            cur = None

        for ln in lines[start:stop]:
            m = date_re.match(ln)
            if m:
                # New row starts
                flush()
                d, mon = m.group(1), m.group(2)
                desc = ln[m.end():].strip()
                cur = {"date": _date(d, mon, year), "payee": desc, "memo": ""}
                continue

            if not cur:
                continue

            # Try to read amounts on this line
            amts = [float(a.replace(",", "")) for a in money_re.findall(ln)]

            # Heuristic: when 3 numbers appear, they are [withdrawal, deposit, balance]
            if len(amts) >= 3 and "amount" not in cur:
                w, d = amts[0], amts[1]
                if d > 0 and w == 0:
                    cur["amount"] = d
                    cur["credit"] = True   # deposit
                elif w > 0 and d == 0:
                    cur["amount"] = w
                    cur["credit"] = False  # withdrawal
                else:
                    # fallback: prefer whichever is non-zero and larger as the actual txn
                    if d >= w:
                        cur["amount"] = d; cur["credit"] = True
                    else:
                        cur["amount"] = w; cur["credit"] = False
                continue

            # If exactly 2 numbers show up on a single line (rare), assume [withdrawal, deposit]
            if len(amts) == 2 and "amount" not in cur:
                w, d = amts
                if d > 0 and w == 0:
                    cur["amount"] = d; cur["credit"] = True
                elif w > 0 and d == 0:
                    cur["amount"] = w; cur["credit"] = False
                else:
                    # pick the non-zero one
                    if d > 0:
                        cur["amount"] = d; cur["credit"] = True
                    else:
                        cur["amount"] = w; cur["credit"] = False
                continue

            # If amounts aren’t on same line as description, keep accumulating memo
            # and decide sign later via keywords with a single amount line.
            if len(amts) == 1 and "amount" not in cur:
                cur["amount"] = amts[0]
                # Keyword hints to decide deposit vs withdrawal
                memo_probe = (cur.get("payee", "") + " " + cur.get("memo", "") + " " + ln).upper()
                if re.search(r"\b(SALARY|INCOMING PAYNOW|INTEREST EARNED|DEPOSIT)\b", memo_probe):
                    cur["credit"] = True
                elif re.search(r"\b(WITHDRAWAL|FUNDS TRANSFER|TOP-UP TO PAYLAH|PAYNOW TRANSFER TO|GIRO DEBIT)\b", memo_probe):
                    cur["credit"] = False
                # If still undecided, leave for later lines; don’t continue
            else:
                # just accumulate description
                cur["memo"] = (cur.get("memo", "") + " " + ln).strip()

            # If we have both absolute amount and credit flag, it’s safe to flush on next date
            # (flush happens when next date line comes or after loop)

        flush()

        # IMPORTANT: return ABS amount + credit flag (no signed amounts here)
        for t in txns:
            t["amount"] = abs(float(t["amount"]))
        return txns
