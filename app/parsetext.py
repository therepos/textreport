import re
from typing import List, Dict, Any

MONTH = {
    'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
    'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12
}

def _date(day, mon, year=2025):
    return f"{year:04d}-{MONTH[mon.upper()]:02d}-{int(day):02d}"

# -----------------------------------------------------------------------------
# Credit card statement parser
# -----------------------------------------------------------------------------
def extract_credit_card_transactions(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
    """Parse POSB/DBS credit card statements (NEW TRANSACTIONS section)."""
    lines = [re.sub(r"\s+"," ",ln).strip() for ln in raw_text.splitlines() if ln.strip()]

    s = next((i for i,l in enumerate(lines) if re.search(r"\bNEW TRANSACTIONS\b", l)), None)
    if s is None:
        s = next((i for i,l in enumerate(lines) if re.search(r"\bPREVIOUS BALANCE\b", l)), None)
    if s is None:
        raise RuntimeError("Couldn't locate 'NEW TRANSACTIONS' section.")

    e = next((j for j in range(s+1, len(lines))
              if re.match(r"^(SUB-TOTAL:|TOTAL:|INSTALMENT PLANS SUMMARY)", lines[j])),
             len(lines))
    txn_lines = lines[s+1:e]

    date_re = re.compile(r'^(?P<d>\d{2}) (?P<m>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b', re.I)
    amt_line = re.compile(r'^(?P<a>[0-9]{1,3}(?:,[0-9]{3})*\.\d{2})(?:\s*(?P<cr>CR))?$', re.I)
    amt_inline = re.compile(r'(?P<a>[0-9]{1,3}(?:,[0-9]{3})*\.\d{2})(?:\s*(?P<cr>CR))?$')
    fx_info = re.compile(r'(U\. S\. DOLLAR|MALAYSIAN RINGGIT)\s+([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})', re.I)

    txns, cur = [], None
    for ln in txn_lines:
        m = date_re.match(ln)
        if m:
            if cur and ('amount' in cur) and cur.get('payee'):
                txns.append(cur)
            d, mon = m.group('d'), m.group('m')
            rest = ln[m.end():].strip()
            mi = amt_inline.search(rest)
            cr = False; amt = None
            if mi:
                amt = mi.group('a')
                cr = bool(mi.group('cr'))
                rest = rest[:mi.start()].strip()
            cur = {'date': _date(d, mon, year), 'payee': rest, 'memo': ''}
            if amt:
                cur['amount'] = float(amt.replace(',', ''))
                cur['credit'] = cr
            continue

        if cur is None:
            continue
        if fx_info.search(ln):
            cur['memo'] = (cur.get('memo','') + ('; ' if cur.get('memo') else '') + ln).strip()
            continue
        ma = amt_line.match(ln)
        if ma and 'amount' not in cur:
            cur['amount'] = float(ma.group('a').replace(',', ''))
            cur['credit'] = bool(ma.group('cr'))
            continue
        if not re.match(r'^(Credit Cards|DBS Cards|Hotline:|Statement of Account|PDS_)', ln, re.I):
            cur['payee'] = (cur['payee'] + ' ' + ln).strip()

    if cur and ('amount' in cur) and cur.get('payee'):
        txns.append(cur)

    for t in txns:
        t['payee'] = re.sub(r'\s{2,}', ' ', t['payee']).strip()
    return txns


# -----------------------------------------------------------------------------
# Deposit account statement parser
# -----------------------------------------------------------------------------
def extract_deposit_transactions(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
    """Parse DBS/POSB deposit account statements (WITHDRAWAL / DEPOSIT columns)."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines() if ln.strip()]

    txns, cur = [], None
    date_re = re.compile(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.I)
    amt_re = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*\.\d{2})")

    for ln in lines:
        m = date_re.match(ln)
        if m:
            if cur and ('amount' in cur):
                txns.append(cur)
            day, mon = m.group(1), m.group(2)
            rest = ln[m.end():].strip()
            cur = {"date": _date(day, mon, year), "payee": rest, "memo": ""}
            continue

        if not cur:
            continue

        amts = amt_re.findall(ln)
        if len(amts) == 2:  # withdrawal + deposit columns
            withdraw, deposit = [float(a.replace(',', '')) for a in amts]
            cur["amount"] = deposit - withdraw
        elif len(amts) == 1:
            cur["amount"] = float(amts[0].replace(',', ''))
        else:
            cur["memo"] = (cur["memo"] + " " + ln).strip()

    if cur and ('amount' in cur):
        txns.append(cur)
    return txns


# -----------------------------------------------------------------------------
# Auto-detect and dispatch
# -----------------------------------------------------------------------------
def extract_transactions_from_text(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
    """Dispatch parser based on document content."""
    if re.search(r"DETAILS OF TRANSACTIONS\s+WITHDRAWAL\(\$\)\s+DEPOSIT\(\$\)", raw_text, re.I):
        return extract_deposit_transactions(raw_text, year)
    if re.search(r"\bNEW TRANSACTIONS\b", raw_text, re.I):
        return extract_credit_card_transactions(raw_text, year)
    raise RuntimeError("Unknown statement format.")
