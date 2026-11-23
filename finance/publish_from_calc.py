# VERSION: 2026-11-23T15:55:00+03:00
"""Standalone publisher for encrypted financial dashboards from saved local Calc.

Only ONE Python file is needed. No Windows CMD launcher or second Python module.

    py publish_from_calc.py              # check local budget, no upload
    py publish_from_calc.py --export-only # local encrypted snapshot only
    py publish_from_calc.py --publish     # upload encrypted reports to GitHub

Default workbook: ~/OneDrive/Documents/Бюджет_2.ods
Override with: --book "C:\\path\\budget.ods"

Requires Python 3.11+, cryptography and tzdata on Windows.
Reads the saved values of LibreOffice formulas; NEVER recalculates them.
The first daily goal is fixed in encrypted owner.enc, not in the workbook.
"""
from __future__ import annotations

import argparse
import base64
import getpass
from datetime import date, datetime
import json
import os
import subprocess
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import xml.etree.ElementTree as ET
import zipfile
import re

# Inlined local Calc model: this script is completely standalone.
SHEET = 'Семейные Траты'
FIRST_BLOCK = 640
BLOCK_SIZE = 14
# Named ODS sources requested by the user. Values stay on the local machine.
SOURCE_CELLS = {
    'Мои': ('C50','C57','C68'),
    'Сводка': ('I23','I14','I17','I9'),
    'ГМАХ мой': ('C5',),
}
RUB_PER_USD = Decimal('60')
T = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
O = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
TX = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
ZERO = Decimal('0')
CENT = Decimal('0.01')

class CalcError(ValueError):
    pass

def money(value, ref):
    if value is None or value == '' or isinstance(value, bool):
        raise CalcError(f'{ref}: missing cached numeric value; save the workbook in LibreOffice Calc.')
    try:
        result = Decimal(str(value).replace('\u00a0','').replace(' ', '').replace(',', '.'))
    except (ValueError, InvalidOperation) as exc:
        raise CalcError(f'{ref}: invalid numeric value {value!r}') from exc
    if not result.is_finite():
        raise CalcError(f'{ref}: number is not finite')
    return result.quantize(CENT, rounding=ROUND_HALF_UP)

def number(value, ref):
    if value is None or value == '' or isinstance(value, bool):
        raise CalcError(f'{ref}: missing numeric value')
    try:
        d=Decimal(str(value).replace(' ', '').replace(',', '.'))
    except (ValueError,InvalidOperation) as exc:
        raise CalcError(f'{ref}: invalid number {value!r}') from exc
    if not d.is_finite(): raise CalcError(f'{ref}: non-finite number')
    return d

def parse_month(value, ref):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:return datetime.strptime(str(value).strip(),fmt).date()
        except (ValueError,TypeError):pass
    raise CalcError(f'{ref}: expected the first day of a month, got {value!r}')

def colindex(col):
    n=0
    for l in col.upper(): n=n*26+ord(l)-64
    return n-1

class Workbook:
    def __init__(self, path:Path):
        self.path=Path(path)
        if not self.path.is_file(): raise CalcError(f'Workbook not found: {self.path}')
        self.cells={}
        self.source_values={}
        if self.path.suffix.lower()=='.ods': self._read_ods()
        elif self.path.suffix.lower() in ('.xlsx','.xls','.xlsb'):
            try:from python_calamine import CalamineWorkbook
            except ImportError as exc:raise CalcError('Install python-calamine to read Excel files; ODS needs no extra parser') from exc
            excel=CalamineWorkbook.from_path(str(path))
            sheet=excel.get_sheet_by_name(SHEET)
            for ri,row in enumerate(sheet.to_python(skip_empty_area=False),1):
                if ri<FIRST_BLOCK:continue
                for ci,value in enumerate(row):
                    if value is not None and value!='':self.cells[(ri,ci)]=value
            for source_sheet, refs in SOURCE_CELLS.items():
                data=excel.get_sheet_by_name(source_sheet).to_python(skip_empty_area=False)
                for ref in refs:
                    match=re.fullmatch(r'([A-Z]+)([0-9]+)',ref)
                    row_idx=int(match.group(2))-1; col_idx=colindex(match.group(1))
                    if row_idx<len(data) and col_idx<len(data[row_idx]):
                        self.source_values[(source_sheet,ref)]=data[row_idx][col_idx]
        else:raise CalcError('Supported formats: saved .ods, .xlsx, .xls and .xlsb')

    def _read_ods(self):
        try:
            with zipfile.ZipFile(self.path) as z:root=ET.fromstring(z.read('content.xml'))
        except (OSError,zipfile.BadZipFile,ET.ParseError) as exc:raise CalcError(f'Invalid or corrupted ODS: {exc}') from exc
        sheet=next((e for e in root.iter(T+'table') if e.get(T+'name')==SHEET),None)
        if sheet is None:raise CalcError(f'Sheet not found: {SHEET!r}')
        ri=0
        for row in sheet:
            if row.tag!=T+'table-row':continue
            repeat=int(row.get(T+'number-rows-repeated','1'))
            first=ri+1
            last=ri+repeat
            ri=last
            if last<FIRST_BLOCK:continue
            ci=0
            for cell in row:
                if cell.tag not in (T+'table-cell',T+'covered-table-cell'):continue
                count=int(cell.get(T+'number-columns-repeated','1'))
                kind=cell.get(O+'value-type')
                if kind=='error':
                    val='#FORMULA-ERROR '+''.join(cell.itertext())[:100]
                elif kind in ('float','percentage','currency'):
                    val=cell.get(O+'value')
                elif kind=='date':val=cell.get(O+'date-value')
                elif kind=='boolean':val=cell.get(O+'boolean-value')=='true'
                else:
                    val=cell.get(O+'string-value')
                    if val is None:
                        val=' '.join(''.join(p.itertext()) for p in cell.findall(TX+'p'))
                if val not in (None,''):
                    for d in range(count):
                        if ci+d<=colindex('R'):
                            for rn in range(max(FIRST_BLOCK,first),last+1):
                                self.cells[(rn,ci+d)]=val
                ci+=count
            if ri>10000:break
        # Read only the precise extra cells needed for debts and savings.
        # Never expose individual household values in the GitHub source.
        for source_sheet, refs in SOURCE_CELLS.items():
            extra=next((e for e in root.iter(T+'table') if e.get(T+'name')==source_sheet),None)
            if extra is None:
                raise CalcError(f"Required sheet not found: {source_sheet}")
            wanted={(int(re.search(r'[0-9]+',ref).group()),colindex(re.match(r'[A-Z]+',ref).group())):ref
                    for ref in refs}
            max_row=max(row for row,col in wanted)
            ri=0
            for row in extra:
                if row.tag!=T+'table-row':continue
                repeat=int(row.get(T+'number-rows-repeated','1'))
                first,last=ri+1,ri+repeat
                ri=last
                if first>max_row:break
                requested=[(r,c,ref) for (r,c),ref in wanted.items() if first<=r<=last]
                if not requested:continue
                ci=0
                for cell in row:
                    if cell.tag not in (T+'table-cell',T+'covered-table-cell'):continue
                    count=int(cell.get(T+'number-columns-repeated','1'))
                    matched=[(r,ref) for r,c,ref in requested if ci<=c<ci+count]
                    if matched:
                        kind=cell.get(O+'value-type')
                        if kind=='error':
                            val='#FORMULA-ERROR '+''.join(cell.itertext())[:80]
                        elif kind in ('float','percentage','currency'):
                            val=cell.get(O+'value')
                        elif kind=='date':
                            val=cell.get(O+'date-value')
                        elif kind=='boolean':
                            val=cell.get(O+'boolean-value')=='true'
                        else:
                            val=cell.get(O+'string-value')
                            if val is None:
                                val=' '.join(''.join(p.itertext()) for p in cell.findall(TX+'p'))
                        for _,ref in matched:
                            self.source_values[(source_sheet,ref)]=val
                    ci+=count

    def source_num(self,source_sheet,ref):
        if (source_sheet,ref) not in self.source_values:
            raise CalcError(f"Missing cached source cell {source_sheet}!{ref}; save the workbook.")
        return money(self.source_values[(source_sheet,ref)],f"{source_sheet}!{ref}")

    def cell(self,col,row,required=True):
        x=self.cells.get((row,colindex(col)))
        if required and (x is None or x==''):raise CalcError(f'{SHEET}!{col}{row}: no cached value')
        return x
    def num(self,col,row):return number(self.cell(col,row),f'{SHEET}!{col}{row}')
    def text(self,col,row):return str(self.cell(col,row,False) or '').strip()

def norm(label):
    n=' '.join(label.casefold().split())
    mapping={
      'продукты':'Продукты','седжаро':'Седжаро','лечение проч':'Прочее лечение',
      'психолог жена':'Психолог','цдока':'Цдока','быт. химия':'Бытовая химия',
      'дети прочее':'Прочие дети','развозка':'Развозка','учёба дети':'Обучение детей',
      'одежда':'Одежда','шабат':'Шаббат','уход за собой':'Уход за собой',
      'квартира':'Аренда','хор сына':'Хор','алиса с экраном':'Рассрочка — Алиса с экраном',
      'алиса в гостинной':'Рассрочка — Алиса в гостиной',
      'непредвиденные траты':'Непредвиденные траты','страхование 629':'Страхование квартиры',
      'сотовая связь':'Сотовая связь','чатгпт':'Подписки (USD-резерв)',
      'интернет 720':'Интернет',
    }
    return mapping.get(n,label)

def budget_cycle(book, row):
    month=parse_month(book.cell('A',row),f'{SHEET}!A{row}')
    if month.day!=1:raise CalcError(f'Expected first day of month in A{row}')
    start=(month.replace(day=1)-timedelta(days=1)).replace(day=21)
    end=month.replace(day=20)
    categories=[];names=set();remaining=ZERO
    for side, labelcol,spentcol,remaincol,limitcol in (
      ('left','D','C','F','G'),('right','O','N','Q','R')):
        for i in range(BLOCK_SIZE):
            rn=row+i;label=book.text(labelcol,rn)
            if not label:continue
            low=label.casefold().strip()
            if low in ('второй столбец','rem'):continue
            limit=book.num(limitcol,rn)
            spent=book.num(spentcol,rn)
            rest=book.num(remaincol,rn)
            if not limit and not spent and not rest:continue
            if abs((limit-spent)-rest)>Decimal('0.02'):
                raise CalcError(f'{label} (row {rn}): remaining is {rest}, but budget - spent = {limit-spent}')
            name=norm(label)
            if name in names:raise CalcError(f'Duplicate category {name!r} in cycle A{row}')
            names.add(name)
            categories.append({'name':name,'limit':float(money(limit,f'{limitcol}{rn}')),
                               'spent':float(money(spent,f'{spentcol}{rn}')),
                               'remaining':float(money(rest,f'{remaincol}{rn}')),
                               'source':f'{SHEET}!{labelcol}{rn}'})
            remaining+=rest
    expenses=book.num('A',row+8)
    if abs(expenses-remaining)>Decimal('0.03'):
        raise CalcError(f'Cycle {start} to {end}: A{row+8} = {expenses:.2f}, '+
           f'sum of unique category remainders = {remaining:.2f}; '+
           f'difference {expenses-remaining:+.2f}. Check F{row+13} '+
           f'(subtotal), Q{row+3} (REM) and formula A{row+8}.')
    income=book.num('A',row+10)
    rub=sum((max(ZERO,book.num('I',row+i)) for i in range(BLOCK_SIZE) if book.cell('I',row+i,False) not in ('',None)),ZERO)
    usd=sum((max(ZERO,book.num('J',row+i)) for i in range(BLOCK_SIZE) if book.cell('J',row+i,False) not in ('',None)),ZERO)
    expected_income=rub+usd*RUB_PER_USD
    if abs(expected_income-income)>Decimal('0.03'):
        raise CalcError(f'Cycle A{row}: income A{row+10}={income:.2f}, '+
              f'positive I + 60*J = {expected_income:.2f} (difference {income-expected_income:+.2f})')
    signed_deficit=book.num('A',row+12)
    return {'label':f'{start:%d.%m.%Y}–{end:%d.%m.%Y}',
            'start':start.isoformat(),'end':end.isoformat(),'sourceRow':row,
            'income':float(money(income,f'A{row+10}')),
            'expenses':float(money(expenses,f'A{row+8}')),
            'signedResult':float(money(signed_deficit,f'A{row+12}')),
            'rubIncome':float(money(rub,'I')),'usdIncome':float(money(usd,'J')),
            'budgets':categories,'possibleReturn':None,'unmappedExpenses':[]}

def cycles_from_book(book,day=None):
    day=day or datetime.now().date()
    first=None
    for row in range(FIRST_BLOCK,FIRST_BLOCK+BLOCK_SIZE*180,BLOCK_SIZE):
        val=book.cell('A',row,False)
        if not val:break
        try:month=parse_month(val,f'A{row}')
        except CalcError:continue
        if month.day!=1:continue
        start=(month-timedelta(days=1)).replace(day=21)
        end=month.replace(day=20)
        if start<=day<=end:
            first=row;break
    if first is None:raise CalcError(f'No 14-row block found for current cycle {day:%d.%m.%Y}, starting at A{FIRST_BLOCK}')
    out=[budget_cycle(book,first+BLOCK_SIZE*i) for i in range(3)]
    for a,b in zip(out,out[1:]):
        if date.fromisoformat(b['start'])!=date.fromisoformat(a['end'])+timedelta(days=1):
            raise CalcError('Budget cycles are not consecutive in the workbook')
    return out

def fixed_goal(deficit, end_date, today, previous=None):
    """Freeze the first calculated daily goal; never recalculate today's existing value."""
    today=today if isinstance(today,date) else date.fromisoformat(today)
    if previous:
        prev=(previous.get('goalHistory') or {}).get(today.isoformat()) or previous.get('dailyGoal') or {}
        if prev.get('date')==today.isoformat() and isinstance(prev.get('target'),(int,float)):
            return prev
        old_date=str(previous.get('asOf',''))[:10]
        old_day=previous.get('day') or {}
        if old_date==today.strftime('%d.%m.%Y') and isinstance(old_day.get('target'),(int,float)):
            return {'date':today.isoformat(),'target':old_day['target'],
                    'basis':'Inherited fixed goal from previous encrypted dashboard'}
    end_date=end_date if isinstance(end_date,date) else date.fromisoformat(end_date)
    days=(end_date-today).days+1
    if days<=0:raise CalcError('Cannot fix a daily goal outside its budget cycle')
    due=max(ZERO,-number(deficit,'Прогноз дефицита'))
    target=(due/Decimal(days)).quantize(CENT, rounding=ROUND_HALF_UP)
    return {'date':today.isoformat(),'target':float(target),
            'basisDeficit':float(money(due,'deficit')),'remainingDays':days,
            'basis':'Снимок первого запуска дня: дефицит Calc / оставшиеся дни включая сегодня'}

REPOSITORY = 'Ishayahu/jewish-chrono'
BRANCH = 'main'
TZ = 'Europe/Moscow'
SITE_OWNER_URL = 'https://ishayahu.github.io/jewish-chrono/finance/data/owner.enc'
PUBLISH_ENABLED = True  # Both workflows use locally committed ciphertexts after first upload.

class PublisherError(ValueError):
    pass

def build_report(book: Workbook, *, today: date, previous: dict | None=None):
    """Read budget, savings and liabilities from cached local Calc values.

    Children goals, instalments and valuation FX rate are the only inherited
    fields left until their own Calc sources are mapped.
    """
    cycles = cycles_from_book(book, today)
    prev = previous or {}
    report = dict(prev)
    report['cycles'] = cycles
    report['deficit'] = max(0., -cycles[0]['signedResult'])
    report['budgetRate'] = 60
    # The household deficit is a separate accounting zero-point. Do not
    # derive it by subtracting cycle income and expenses.
    report['familyDeficit'] = float(max(ZERO,book.source_num('Мои','C68')))
    tinkoff = book.source_num('Мои','C50')
    sberbank = book.source_num('Мои','C57')
    if tinkoff<0 or sberbank<0:
        raise CalcError('Savings balances must not be negative (Мои!C50/C57).')
    report['savingsAccounts'] = [
        {'name':'Т-Банк','amount':float(tinkoff),'source':'Мои!C50'},
        {'name':'Сбербанк','amount':float(sberbank),'source':'Мои!C57'},
    ]
    report['savedRub'] = float(money(tinkoff+sberbank,'savings total'))
    # On the supplied 23-Nov ODS, Сводка!I23 is -36,580, close to the
    # previously recorded USD loan; the adjacent label is "Я арев".
    # Respect the explicitly supplied cell, but record its source.
    def liability(source_sheet,ref):
        signed=book.source_num(source_sheet,ref)
        if signed>0:
            raise CalcError(f'Expected non-positive debt balance at {source_sheet}!{ref}, got {signed}.')
        return float(-signed)
    report['usdDebt'] = liability('Сводка','I23')
    report['rubDebts'] = [
        {'name':'Цдока МЕОЦ','amount':liability('Сводка','I14')},
        {'name':'Мама','amount':liability('Сводка','I17')},
        {'name':'Бюджет МЕОЦ','amount':liability('Сводка','I9')},
        {'name':'Свой ГМАХ','amount':float(max(ZERO,book.source_num('ГМАХ мой','C5')))},
    ]
    report.pop('reserveTargetRub',None)
    report['calcSources'] = {
        'familyDeficit':'Мои!C68',
        'usdDebt':'Сводка!I23',
        'rubDebts':{'Цдока МЕОЦ':'Сводка!I14','Мама':'Сводка!I17',
                    'Бюджет МЕОЦ':'Сводка!I9','Свой ГМАХ':'ГМАХ мой!C5'},
        'savings':['Мои!C50','Мои!C57'],
    }
    report['budgetSource'] = {'workbookSheet': 'Семейные Траты',
            'rows': [c['sourceRow'] for c in cycles],
            'note': 'Budget, debts, family deficit and bank savings sourced from the saved Calc workbook.'}
    goal = fixed_goal(cycles[0]['signedResult'], cycles[0]['end'], today, previous)
    report['dailyGoal'] = goal
    history=dict(prev.get('goalHistory') or {})
    history[today.isoformat()]=goal
    report['goalHistory']=history
    same_day = (prev.get('dailyGoal') or {}).get('date')==today.isoformat()
    day_received = (prev.get('day') or {}).get('received') if same_day else None
    report['day'] = {'target':goal['target'], 'received':day_received}
    modified = datetime.fromtimestamp(book.path.stat().st_mtime,ZoneInfo(TZ))
    report['asOf'] = modified.strftime('%d.%m.%Y %H:%M МСК')
    report['sourceSavedAt'] = modified.isoformat()
    report['exportedAt'] = datetime.now(ZoneInfo(TZ)).isoformat()
    if previous:
        report['legacyFieldsAsOf'] = prev.get('legacyFieldsAsOf',prev.get('asOf'))
    return report

def encrypt_report(data: dict, password: str) -> str:
    if not password:
        raise PublisherError('Encryption password must not be empty.')
    from secrets import token_bytes
    salt, iv = token_bytes(16), token_bytes(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                    iterations=600_000).derive(password.encode('utf-8'))
    enc = lambda b: base64.b64encode(b).decode('ascii')
    ciphertext = AESGCM(key).encrypt(iv,json.dumps(data,ensure_ascii=False,
                        separators=(',',':')).encode('utf-8'),None)
    return json.dumps({'v':1,'kdf':'PBKDF2-SHA256','cipher':'AES-256-GCM',
           'iterations':600_000,'salt':enc(salt),'iv':enc(iv),
           'ciphertext':enc(ciphertext)},separators=(',',':'))

def decrypt_report(envelope: str | dict, password: str) -> dict:
    if not password: raise PublisherError('FINANCE_OWNER_PASSWORD is required to recover the previous daily goal')
    obj=json.loads(envelope) if isinstance(envelope,str) else envelope
    if (obj.get('v')!=1 or obj.get('kdf')!='PBKDF2-SHA256' or
        obj.get('cipher')!='AES-256-GCM' or obj.get('iterations',0)<600_000):
        raise PublisherError('Unsupported previous encrypted report format')
    dec=lambda x:base64.b64decode(x,validate=True)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=dec(obj['salt']),
         iterations=obj['iterations']).derive(password.encode('utf-8'))
    try:
        data=json.loads(AESGCM(key).decrypt(dec(obj['iv']),dec(obj['ciphertext']),None))
    except Exception as exc:
        raise PublisherError('Cannot decrypt previous report: password mismatch or corrupted file') from exc
    if not isinstance(data,dict): raise PublisherError('Invalid previous report format')
    return data

def site_previous(password: str) -> dict:
    """Read the encrypted snapshot ACTUALLY served to the dashboard.

    GitHub Actions creates it at deploy time but does not commit it back to
    the repository. The committed finance/data/owner.enc may be outdated.
    """
    request=urllib.request.Request(SITE_OWNER_URL,
                headers={'User-Agent':'finance-local-calc-publisher',
                         'Cache-Control':'no-cache'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            payload=response.read(2_000_001)
    except (OSError, urllib.error.URLError) as exc:
        raise PublisherError('Cannot download the live owner.enc from GitHub Pages. '
            'Check access to '+SITE_OWNER_URL) from exc
    if len(payload)>2_000_000:
        raise PublisherError('Live owner.enc is unexpectedly large; export aborted')
    try:
        return decrypt_report(payload.decode('utf-8'),password)
    except (UnicodeError,ValueError) as exc:
        raise PublisherError('Live owner.enc could not be decrypted using the supplied password. '
            'Make sure this is the owner dashboard password.') from exc


def github_json(method: str, endpoint: str, token: str, data: dict | None=None) -> dict:
    url='https://api.github.com/repos/'+REPOSITORY+'/'+endpoint.lstrip('/')
    headers={'Authorization':f'Bearer {token}', 'Accept':'application/vnd.github+json',
      'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'finance-local-calc-publisher'}
    raw=None
    if data is not None:
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
        headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=raw,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=35) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        raise PublisherError(f'GitHub {method} {endpoint}: HTTP {exc.code}') from exc

def require_switched_workflow(token:str):
    """Both Pages workflows must switch to committed data after first upload.

    Until then they deliberately retain the legacy Google generator to keep
    the existing website live during migration.
    """
    for path in ('.github/workflows/finance.yml','.github/workflows/pages.yml'):
        info=github_json('GET',f'contents/{urllib.parse.quote(path,safe="/")}?ref={BRANCH}',token)
        code=base64.b64decode(info['content']).decode('utf-8')
        if not all(marker in code for marker in (
                'LOCAL_CALC_SNAPSHOT_READY',
                'test -s finance/data/owner.enc && test -s finance/data/family.enc')):
            raise PublisherError(
                f'Safe workflow cutover is missing in {path}; publication aborted.'
            )

def remote_previous(token: str, password: str):
    head=github_json('GET',f'git/ref/heads/{BRANCH}',token)['object']['sha']
    path=urllib.parse.quote('finance/data/owner.enc',safe='/')
    try:
        current=github_json('GET',f'contents/{path}?ref={head}',token)
    except PublisherError as exc:
        if 'HTTP 404' in str(exc):
            print('GitHub owner.enc not found; downloading live report from Pages.')
            return head,site_previous(password)
        raise
    raw=base64.b64decode(current['content']).decode('utf-8')
    try:
        obj=decrypt_report(raw,password)
    except PublisherError:
        print('Stale owner.enc in GitHub; using live encrypted report from Pages.')
        return head,site_previous(password)
    if (obj.get('budgetSource') or {}).get('workbookSheet')!='Семейные Траты':
        print('Legacy pre-Calc snapshot in GitHub; loading current fields from Pages.')
        return head,site_previous(password)
    return head,obj

def publish_encrypted(files:dict[str,str],token:str,expected_head:str):
    """Commit both encrypted files against same branch HEAD; never force-overwrite."""
    current=github_json('GET',f'git/ref/heads/{BRANCH}',token)['object']['sha']
    if current!=expected_head:
        raise PublisherError('GitHub HEAD changed concurrently; retry to protect the fixed daily goal')
    parent=github_json('GET',f'git/commits/{current}',token)
    tree=github_json('POST','git/trees',token,{
       'base_tree':parent['tree']['sha'],
       'tree':[{'path':p,'mode':'100644','type':'blob','content':c} for p,c in files.items()]})['sha']
    commit=github_json('POST','git/commits',token,{
       'message':'chore(finance): publish fixed-day encrypted snapshot from local Calc',
       'tree':tree,'parents':[current]})['sha']
    github_json('PATCH',f'git/refs/heads/{BRANCH}',token,{'sha':commit,'force':False})
    return commit

def require_legacy_fields(previous:dict|None):
    required=('rate','children','installments')
    missing=[k for k in required if not isinstance(previous,dict) or k not in previous]
    if missing:
        raise PublisherError('Previous owner.enc is missing fields not yet mapped from Calc: '+', '.join(missing)+
                   '. Refusing to invent values; provide a previous report or verified Calc references.')

def existing_password(variable: str, prompt: str) -> str:
    """Reuse the already configured secret or ask securely for the EXISTING password.

    No new length requirement: the old GitHub dashboard may use an established
    password shorter than 16 characters. getpass never echoes typed secrets.
    """
    current = os.environ.get(variable)
    if current:
        return current
    try:
        value = getpass.getpass(prompt + ' (hidden input): ')
    except (EOFError, KeyboardInterrupt) as exc:
        raise PublisherError('Could not read password from terminal') from exc
    if not value:
        raise PublisherError('Empty password: enter the current dashboard password.')
    return value


def github_token() -> str:
    """Use an already configured token or the standard GitHub CLI login.

    Fall back to a concealed one-time prompt without storing credentials on
    disk. Never echo credentials into logs, shell history or the dashboard.
    """
    token=os.environ.get('GITHUB_TOKEN','').strip()
    if token:
        return token
    try:
        result=subprocess.run(['gh','auth','token'],capture_output=True,
                              text=True,timeout=15,check=False)
        if result.returncode==0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):
        pass
    try:
        token=getpass.getpass('GitHub token (fine-grained, Contents: read/write): ').strip()
    except (EOFError,KeyboardInterrupt) as exc:
        raise PublisherError('Could not read GitHub token') from exc
    if not token:
        raise PublisherError(
           'Нужен GITHUB_TOKEN или вход в GitHub CLI (gh auth login). '
           'Без токена публикация не выполняется.'
        )
    return token


def merge_first_local_goal(remote: dict, local: dict | None, today: date) -> dict:
    """On FIRST upload, preserve the goal fixed by prior --export-only.

    Once a Calc snapshot exists on GitHub, the committed remote history is
    authoritative; never silently replace it with older local state.
    """
    if (remote.get('budgetSource') or {}).get('workbookSheet')=='Семейные Траты':
        return remote
    if not local:
        return remote
    goal=(local.get('goalHistory') or {}).get(today.isoformat()) or local.get('dailyGoal') or {}
    if goal.get('date')!=today.isoformat() or not isinstance(goal.get('target'),(int,float)):
        return remote
    merged=dict(remote)
    merged['dailyGoal']=goal
    history=dict(remote.get('goalHistory') or {})
    history.update(local.get('goalHistory') or {})
    history[today.isoformat()]=goal
    merged['goalHistory']=history
    return merged


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book',type=Path,
        default=Path.home()/'OneDrive'/'Documents'/'Бюджет_2.ods',
        help='Path to saved .ods/.xlsx; default ~/OneDrive/Documents/Budget_2.ods')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--publish',action='store_true',help='Publish encrypted report after guarded workflow cutover')
    mode.add_argument('--export-only',action='store_true',help='Create local encrypted .enc files only')
    parser.add_argument('--output-dir',type=Path,default=Path.home()/'finance-export')
    parser.add_argument('--previous-owner',type=Path,help='Optional previous owner.enc file')
    args=parser.parse_args(argv)
    tz=ZoneInfo(TZ)
    today=datetime.now(tz).date()
    book=Workbook(args.book)
    cycles=cycles_from_book(book,today)
    print('Workbook:',book.path,'| saved:',datetime.fromtimestamp(book.path.stat().st_mtime,tz))
    for c in cycles:
        print(f"{c['label']} | income {c['income']:,.2f} | remaining expenses {c['expenses']:,.2f} | "+
              f"deficit {max(0,-c['signedResult']):,.2f} | categories {len(c['budgets'])}")
    if not(args.publish or args.export_only):
        print('CHECK OK: structure and totals match; GitHub unchanged. Daily goal not fixed.')
        return 0
    owner_password=existing_password('FINANCE_OWNER_PASSWORD','Current owner dashboard password')
    family_password=existing_password('WIFE_PASSWORD','Current family dashboard password')
    previous=None;head=None
    if args.publish:
        if not PUBLISH_ENABLED:raise PublisherError('PUBLISH_ENABLED=False: publication cutover is not enabled')
        token=github_token()
        require_switched_workflow(token)
        head,previous=remote_previous(token,owner_password)
        local_latest=args.output_dir/'owner.enc'
        if local_latest.is_file():
            try:
                local_report=decrypt_report(local_latest.read_text(encoding='utf-8'),
                                             owner_password)
            except PublisherError as exc:
                raise PublisherError(
                    f'Encrypted report at {local_latest} uses a different password '
                    'or is damaged. Aborting to preserve an already fixed '
                    'daily goal. Keep this file for inspection.'
                ) from exc
            previous=merge_first_local_goal(previous,local_report,today)
    else:
        # Prefer the most recent LOCAL encrypted snapshot on subsequent runs;
        # --previous-owner is only a bootstrap fallback. Otherwise the frozen
        # same-day goal would silently reset to the original legacy copy.
        local_latest=args.output_dir/'owner.enc'
        previous_path=local_latest if local_latest.is_file() else args.previous_owner
        if previous_path and previous_path.is_file():
            try:
                previous=decrypt_report(previous_path.read_text(encoding='utf-8'),owner_password)
            except PublisherError:
                if previous_path == local_latest:
                    # Do not silently replace a newer local goal history.
                    raise PublisherError('Cannot decrypt local '+str(local_latest)+
                        '. Its password may differ. Preserve this file and investigate; '
                        'do not replace fixed goals using an older snapshot.')
                print('Repository owner.enc cannot be decrypted; using live Pages report.')
                previous=site_previous(owner_password)
        else:
            print('No local previous owner.enc; using live Pages report.')
            previous=site_previous(owner_password)
    require_legacy_fields(previous)
    report=build_report(book,today=today,previous=previous)
    files={'finance/data/owner.enc':encrypt_report(report,owner_password),
           'finance/data/family.enc':encrypt_report({'asOf':report['asOf'],'cycle':report['cycles'][0]},family_password)}
    # Check both freshly produced encrypted payloads BEFORE saving/publishing.
    owner_check=decrypt_report(files['finance/data/owner.enc'],owner_password)
    family_check=decrypt_report(files['finance/data/family.enc'],family_password)
    if (owner_check.get('dailyGoal')!=report.get('dailyGoal') or
        family_check.get('cycle')!=report['cycles'][0] or
        len(owner_check.get('cycles') or [])!=3):
        raise PublisherError('Encrypted report round-trip validation failed; publication aborted.')
    if args.export_only:
        args.output_dir.mkdir(parents=True,exist_ok=True)
        for target,content in files.items():
            p=args.output_dir/Path(target).name
            p.write_text(content,encoding='utf-8')
            print('Local encrypted file:',p)
        print('Daily goal:',report['dailyGoal']['date'],report['dailyGoal']['target'],'RUB (fixed in owner.enc)')
        return 0
    commit=publish_encrypted(files,token,head)
    print('GitHub updated: encrypted owner.enc and family.enc only; commit',commit)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (PublisherError,CalcError,OSError,ValueError) as exc:
        print('ERROR:',str(exc).encode('ascii','backslashreplace').decode('ascii'),file=sys.stderr)
        sys.exit(1)
