#!/usr/bin/env python3
# VERSION: 2026-11-23T14:45:00+03:00
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

# Inlined local Calc model: this script is completely standalone.
SHEET = 'Семейные Траты'
FIRST_BLOCK = 640
BLOCK_SIZE = 14
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
        raise CalcError(f'{ref}: отсутствует сохранённое числовое значение. Сохраните книгу Calc.')
    try:
        result = Decimal(str(value).replace('\u00a0','').replace(' ', '').replace(',', '.'))
    except (ValueError, InvalidOperation) as exc:
        raise CalcError(f'{ref}: некорректное число {value!r}') from exc
    if not result.is_finite():
        raise CalcError(f'{ref}: число не конечное')
    return result.quantize(CENT, rounding=ROUND_HALF_UP)

def number(value, ref):
    if value is None or value == '' or isinstance(value, bool):
        raise CalcError(f'{ref}: пустое числовое значение')
    try:
        d=Decimal(str(value).replace(' ', '').replace(',', '.'))
    except (ValueError,InvalidOperation) as exc:
        raise CalcError(f'{ref}: неверное число {value!r}') from exc
    if not d.is_finite(): raise CalcError(f'{ref}: неконечное значение')
    return d

def parse_month(value, ref):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:return datetime.strptime(str(value).strip(),fmt).date()
        except (ValueError,TypeError):pass
    raise CalcError(f'{ref}: ожидалась дата первого числа месяца, получено {value!r}')

def colindex(col):
    n=0
    for l in col.upper(): n=n*26+ord(l)-64
    return n-1

class Workbook:
    def __init__(self, path:Path):
        self.path=Path(path)
        if not self.path.is_file(): raise CalcError(f'Нет книги {self.path}')
        self.cells={}
        if self.path.suffix.lower()=='.ods': self._read_ods()
        elif self.path.suffix.lower() in ('.xlsx','.xls','.xlsb'):
            try:from python_calamine import CalamineWorkbook
            except ImportError as exc:raise CalcError('Для чтения Excel установите python-calamine; ODS читается без зависимостей') from exc
            sheet=CalamineWorkbook.from_path(str(path)).get_sheet_by_name(SHEET)
            for ri,row in enumerate(sheet.to_python(skip_empty_area=False),1):
                if ri<FIRST_BLOCK:continue
                for ci,value in enumerate(row):
                    if value is not None and value!='':self.cells[(ri,ci)]=value
        else:raise CalcError('Поддерживаются сохранённые .ods и .xlsx/.xls/.xlsb')

    def _read_ods(self):
        try:
            with zipfile.ZipFile(self.path) as z:root=ET.fromstring(z.read('content.xml'))
        except (OSError,zipfile.BadZipFile,ET.ParseError) as exc:raise CalcError(f'Повреждённый ODS: {exc}') from exc
        sheet=next((e for e in root.iter(T+'table') if e.get(T+'name')==SHEET),None)
        if sheet is None:raise CalcError(f'Нет вкладки {SHEET!r}')
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

    def cell(self,col,row,required=True):
        x=self.cells.get((row,colindex(col)))
        if required and (x is None or x==''):raise CalcError(f'{SHEET}!{col}{row}: нет сохранённого значения')
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
    if month.day!=1:raise CalcError(f'В A{row} ожидалось первое число месяца')
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
                raise CalcError(f'{label} (строка {rn}): остаток {rest}, но лимит − факт = {limit-spent}')
            name=norm(label)
            if name in names:raise CalcError(f'Дублирующаяся категория {name!r} в цикле A{row}')
            names.add(name)
            categories.append({'name':name,'limit':float(money(limit,f'{limitcol}{rn}')),
                               'spent':float(money(spent,f'{spentcol}{rn}')),
                               'remaining':float(money(rest,f'{remaincol}{rn}')),
                               'source':f'{SHEET}!{labelcol}{rn}'})
            remaining+=rest
    expenses=book.num('A',row+8)
    if abs(expenses-remaining)>Decimal('0.03'):
        raise CalcError(f'Цикл {start}–{end}: A{row+8} = {expenses:.2f}, '+
           f'сумма остатков уникальных категорий = {remaining:.2f}; '+
           f'разница {expenses-remaining:+.2f}. Проверьте F{row+13} '+
           f'(сводная строка), Q{row+3} (REM) и формулу A{row+8}.')
    income=book.num('A',row+10)
    rub=sum((max(ZERO,book.num('I',row+i)) for i in range(BLOCK_SIZE) if book.cell('I',row+i,False) not in ('',None)),ZERO)
    usd=sum((max(ZERO,book.num('J',row+i)) for i in range(BLOCK_SIZE) if book.cell('J',row+i,False) not in ('',None)),ZERO)
    expected_income=rub+usd*RUB_PER_USD
    if abs(expected_income-income)>Decimal('0.03'):
        raise CalcError(f'Цикл A{row}: доход A{row+10}={income:.2f}, '+
              f'но положительные I + 60×J = {expected_income:.2f} (разница {income-expected_income:+.2f})')
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
    if first is None:raise CalcError(f'Нет 14-строчного блока текущего цикла для {day:%d.%m.%Y}; начиная с A{FIRST_BLOCK}')
    out=[budget_cycle(book,first+BLOCK_SIZE*i) for i in range(3)]
    for a,b in zip(out,out[1:]):
        if date.fromisoformat(b['start'])!=date.fromisoformat(a['end'])+timedelta(days=1):
            raise CalcError('Бюджетные циклы в файле не следуют друг за другом')
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
    if days<=0:raise CalcError('Нельзя назначить дневную цель за пределами цикла')
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
    """Use Calc for three cycles; retain unrelated dashboard fields from prior snapshot.

    Current source workbook has NO verified cells for personal debts, savings,
    previous whole-family deficit or payments received *today*. Do not invent them.
    """
    cycles = cycles_from_book(book, today)
    prev = previous or {}
    report = dict(prev)
    report['cycles'] = cycles
    report['deficit'] = max(0., -cycles[0]['signedResult'])
    report['budgetRate'] = 60
    report['budgetSource'] = {'workbookSheet': 'Семейные Траты',
            'rows': [c['sourceRow'] for c in cycles],
            'note': 'Only income, expenses and category values are refreshed from Calc.'}
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
        raise PublisherError('Пароль шифрования не может быть пустым.')
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
    if not password: raise PublisherError('Нужен FINANCE_OWNER_PASSWORD для восстановления прежней цели')
    obj=json.loads(envelope) if isinstance(envelope,str) else envelope
    if (obj.get('v')!=1 or obj.get('kdf')!='PBKDF2-SHA256' or
        obj.get('cipher')!='AES-256-GCM' or obj.get('iterations',0)<600_000):
        raise PublisherError('Неизвестный формат прежнего шифрованного отчёта')
    dec=lambda x:base64.b64decode(x,validate=True)
    key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=dec(obj['salt']),
         iterations=obj['iterations']).derive(password.encode('utf-8'))
    try:
        data=json.loads(AESGCM(key).decrypt(dec(obj['iv']),dec(obj['ciphertext']),None))
    except Exception as exc:
        raise PublisherError('Не удалось прочитать прежний отчёт: пароль не совпадает или файл повреждён') from exc
    if not isinstance(data,dict): raise PublisherError('Неверный формат предыдущего отчёта')
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
        raise PublisherError('Не удалось получить актуальный owner.enc с опубликованного сайта. '
            'Проверьте доступность '+SITE_OWNER_URL) from exc
    if len(payload)>2_000_000:
        raise PublisherError('Неожиданно большой owner.enc с сайта; экспорт остановлен')
    try:
        return decrypt_report(payload.decode('utf-8'),password)
    except (UnicodeError,ValueError) as exc:
        raise PublisherError('Сайт доступен, но действующим паролем его owner.enc расшифровать не удалось. '
            'Проверьте, что пароль относится к личному дашборду.') from exc


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
                f'Безопасное переключение ещё не установлено в {path}; ничего не публикуем.'
            )

def remote_previous(token: str, password: str):
    head=github_json('GET',f'git/ref/heads/{BRANCH}',token)['object']['sha']
    path=urllib.parse.quote('finance/data/owner.enc',safe='/')
    try:
        current=github_json('GET',f'contents/{path}?ref={head}',token)
    except PublisherError as exc:
        if 'HTTP 404' in str(exc):
            print('В GitHub отсутствует owner.enc; читаю опубликованный сайт.')
            return head,site_previous(password)
        raise
    raw=base64.b64decode(current['content']).decode('utf-8')
    try:
        obj=decrypt_report(raw,password)
    except PublisherError:
        print('GitHub содержит старый owner.enc; читаю актуальный зашифрованный отчёт с сайта.')
        return head,site_previous(password)
    if (obj.get('budgetSource') or {}).get('workbookSheet')!='Семейные Траты':
        print('В GitHub архивный снимок до перехода на Calc; наследую актуальные поля сайта.')
        return head,site_previous(password)
    return head,obj

def publish_encrypted(files:dict[str,str],token:str,expected_head:str):
    """Commit both encrypted files against same branch HEAD; never force-overwrite."""
    current=github_json('GET',f'git/ref/heads/{BRANCH}',token)['object']['sha']
    if current!=expected_head:
        raise PublisherError('Снимок Github обновился параллельно: повторите запуск, чтобы не стереть дневную цель')
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
    required=('familyDeficit','usdDebt','rate','savedRub','reserveTargetRub','rubDebts','children','installments')
    missing=[k for k in required if not isinstance(previous,dict) or k not in previous]
    if missing:
        raise PublisherError('В прежнем owner.enc недостаёт ещё не сопоставленных с Calc полей: '+', '.join(missing)+
                   '. Не публикуем выдуманные значения; нужен прежний отчёт или утверждённые адреса.')

def existing_password(variable: str, prompt: str) -> str:
    """Reuse the already configured secret or ask securely for the EXISTING password.

    No new length requirement: the old GitHub dashboard may use an established
    password shorter than 16 characters. getpass never echoes typed secrets.
    """
    current = os.environ.get(variable)
    if current:
        return current
    try:
        value = getpass.getpass(prompt + ' (ввод скрыт): ')
    except (EOFError, KeyboardInterrupt) as exc:
        raise PublisherError('Не удалось прочитать пароль из терминала') from exc
    if not value:
        raise PublisherError('Пустой пароль. Введи действующий пароль дашборда.')
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
        token=getpass.getpass('GitHub token (fine-grained, только Contents: write): ').strip()
    except (EOFError,KeyboardInterrupt) as exc:
        raise PublisherError('Не удалось получить токен GitHub') from exc
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
        help='Путь к сохранённой .ods/.xlsx; по умолчанию ~/OneDrive/Documents/Бюджет_2.ods')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--publish',action='store_true',help='Опубликовать зашифрованный отчёт (после переключения workflow)')
    mode.add_argument('--export-only',action='store_true',help='Записать только локальные .enc')
    parser.add_argument('--output-dir',type=Path,default=Path.home()/'finance-export')
    parser.add_argument('--previous-owner',type=Path,help='Необязательная копия прежнего owner.enc')
    args=parser.parse_args(argv)
    tz=ZoneInfo(TZ)
    today=datetime.now(tz).date()
    book=Workbook(args.book)
    cycles=cycles_from_book(book,today)
    print('Таблица:',book.path,'| сохранена',datetime.fromtimestamp(book.path.stat().st_mtime,tz))
    for c in cycles:
        print(f"{c['label']} | доход {c['income']:,.2f} | осталось расходов {c['expenses']:,.2f} | "+
              f"дефицит {max(0,-c['signedResult']):,.2f} | категорий {len(c['budgets'])}")
    if not(args.publish or args.export_only):
        print('ПРОВЕРКА: структура и суммы сошлись, GitHub не изменён. Цель не фиксировалась.')
        return 0
    owner_password=existing_password('FINANCE_OWNER_PASSWORD','Действующий пароль личного дашборда')
    family_password=existing_password('WIFE_PASSWORD','Действующий пароль семейного дашборда')
    previous=None;head=None
    if args.publish:
        if not PUBLISH_ENABLED:raise PublisherError('PUBLISH_ENABLED=False: переключение публикации ещё не согласовано')
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
                    f'В {local_latest} находится зашифрованный отчёт с другим паролем '
                    'или ошибкой. Не публикуем: важно не потерять фиксированную '
                    'дневную цель. Сохраните файл для проверки.'
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
                    raise PublisherError('Не удалось прочитать локальный '+str(local_latest)+
                        '. Возможно, его пароль отличается. Сохраните файл и разберитесь с причиной; '
                        'не заменяем зафиксированные цели более старой копией.')
                print('Репозиторный owner.enc не открывается: читаю актуальный отчёт с сайта.')
                previous=site_previous(owner_password)
        else:
            print('Исходного owner.enc локально нет: читаю актуальный отчёт с сайта.')
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
        raise PublisherError('Проверка зашифрованного отчёта не пройдена; публикация запрещена.')
    if args.export_only:
        args.output_dir.mkdir(parents=True,exist_ok=True)
        for target,content in files.items():
            p=args.output_dir/Path(target).name
            p.write_text(content,encoding='utf-8')
            print('Локальный шифрованный файл:',p)
        print('Дневная цель',report['dailyGoal']['date'],report['dailyGoal']['target'],'₽ (фиксирована в owner.enc)')
        return 0
    commit=publish_encrypted(files,token,head)
    print('GitHub обновлён: только owner.enc и family.enc; коммит',commit)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (PublisherError,CalcError,OSError,ValueError) as exc:
        print('ОШИБКА:',str(exc),file=sys.stderr)
        sys.exit(1)
