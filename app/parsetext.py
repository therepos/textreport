import re
from typing import List, Dict, Any

MONTH = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,
         'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}

def _date(day, mon, year=2025): return f"{year:04d}-{MONTH[mon.upper()]:02d}-{int(day):02d}"

def extract_transactions_from_text(raw_text: str, year: int = 2025) -> List[Dict[str, Any]]:
    lines = [re.sub(r"\s+"," ",ln).strip() for ln in raw_text.splitlines() if ln.strip()]

    # Find NEW TRANSACTIONS block (fallback to PREVIOUS BALANCE if needed)
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
            if cur and ('amount' in cur) and cur.get('payee'): txns.append(cur)
            d, mon = m.group('d'), m.group('m'); rest = ln[m.end():].strip()
            mi = amt_inline.search(rest); cr=False; amt=None
            if mi:
                amt = mi.group('a'); cr = bool(mi.group('cr')); rest = rest[:mi.start()].strip()
            cur = {'date': _date(d, mon, year), 'payee': rest, 'memo': ''}
            if amt: cur['amount'] = float(amt.replace(',','')); cur['credit'] = cr
            continue

        if cur is None: continue
        if fx_info.search(ln):
            cur['memo'] = (cur.get('memo','') + ('; ' if cur.get('memo') else '') + ln).strip(); continue
        ma = amt_line.match(ln)
        if ma and 'amount' not in cur:
            cur['amount'] = float(ma.group('a').replace(',','')); cur['credit'] = bool(ma.group('cr')); continue
        if not re.match(r'^(Credit Cards|DBS Cards|Hotline:|Statement of Account|PDS_)', ln, re.I):
            cur['payee'] = (cur['payee'] + ' ' + ln).strip()

    if cur and ('amount' in cur) and cur.get('payee'): txns.append(cur)
    for t in txns: t['payee'] = re.sub(r'\s{2,}',' ',t['payee']).strip()
    return txns
