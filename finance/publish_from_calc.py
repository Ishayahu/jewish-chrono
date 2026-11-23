# VERSION: 2026-11-23T12:00:00+03:00
#!/usr/bin/env python3
"""Publish encrypted finance dashboards from saved local LibreOffice Calc.

Basic validation (never uploads): python finance/publish_from_calc.py --book budget.ods
Test encrypted snapshots:       python finance/publish_from_calc.py --book budget.ods --export-only
Live upload:                    python finance/publish_from_calc.py --book budget.ods --publish

Only local cached formula results are read; they are not recalculated.
The first goal fixed for a Moscow date lives in encrypted owner.enc, NOT Calc.
"""
from __future__ import annotations

import argparse
import base64
import getpass
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    from finance.local_calc_model import Workbook, CalcError, cycles_from_book, fixed_goal
except ModuleNotFoundError:
    from local_calc_model import Workbook, CalcError, cycles_from_book, fixed_goal

REPOSITORY = 'Ishayahu/jewish-chrono'
BRANCH = 'main'
TZ = 'Europe/Moscow'
PUBLISH_ENABLED = False   # Enable only after replacing cloud Google Sheets workflow.

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
    path='.github/workflows/finance.yml'
    info=github_json('GET',f'contents/{urllib.parse.quote(path,safe="/")}?ref={BRANCH}',token)
    code=base64.b64decode(info['content']).decode('utf-8')
    if 'build_encrypted.py' in code or 'FINANCE_GOOGLE_SERVICE_ACCOUNT_JSON' in code:
        raise PublisherError('Публикация заблокирована: прежний GitHub workflow ещё строит отчёт из Google Sheets.')

def remote_previous(token: str, password: str):
    head=github_json('GET',f'git/ref/heads/{BRANCH}',token)['object']['sha']
    path=urllib.parse.quote('finance/data/owner.enc',safe='/')
    try:
        current=github_json('GET',f'contents/{path}?ref={head}',token)
    except PublisherError as exc:
        if 'HTTP 404' in str(exc):
            return head,None
        raise
    raw=base64.b64decode(current['content']).decode('utf-8')
    return head,decrypt_report(raw,password)

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


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--book',type=Path,required=True,help='Путь к сохранённой .ods/.xlsx')
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
        token=os.environ.get('GITHUB_TOKEN','').strip()
        if not token:raise PublisherError('Не задан GITHUB_TOKEN (Contents: write)')
        require_switched_workflow(token)
        head,previous=remote_previous(token,owner_password)
    else:
        previous_path=args.previous_owner or (args.output_dir/'owner.enc')
        if previous_path.is_file():
            previous=decrypt_report(previous_path.read_text(encoding='utf-8'),owner_password)
    require_legacy_fields(previous)
    report=build_report(book,today=today,previous=previous)
    files={'finance/data/owner.enc':encrypt_report(report,owner_password),
           'finance/data/family.enc':encrypt_report({'asOf':report['asOf'],'cycle':report['cycles'][0]},family_password)}
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
