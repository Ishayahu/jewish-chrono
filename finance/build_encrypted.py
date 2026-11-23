import os,json,base64,secrets,datetime as dt
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from daily_target import ensure_daily_target
SID='1nQNEresKTI0b5LzVhmZQhT0AFLmqWhKNlz369CIoCPU'
ranges=["'Финансовая позиция'!A1:B55","'Дневное распределение'!A4:K130","'Бюджет — с 21.11.2026'!A1:D40","'Операции'!A1:R1000","'Утренняя цель — новая схема'!A4:L400","'Бюджет — скользящие циклы'!A1:J200"]
def encrypt_report(report,password,filename):
 if len(password)<12:raise ValueError('Password too short')
 salt,iv=secrets.token_bytes(16),secrets.token_bytes(12)
 key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=600000).derive(password.encode())
 enc=lambda x:base64.b64encode(x).decode()
 out={'v':1,'kdf':'PBKDF2-SHA256','cipher':'AES-256-GCM','iterations':600000,'salt':enc(salt),'iv':enc(iv),'ciphertext':enc(AESGCM(key).encrypt(iv,json.dumps(report,ensure_ascii=False).encode(),None))}
 from pathlib import Path
 Path(filename).write_text(json.dumps(out))

def main():
 c=service_account.Credentials.from_service_account_info(json.loads(os.environ['FINANCE_GOOGLE_SERVICE_ACCOUNT_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets'])
 r=AuthorizedSession(c).get(f'https://sheets.googleapis.com/v4/spreadsheets/{SID}/values:batchGet',params=[('ranges',x) for x in ranges]+[('valueRenderOption','UNFORMATTED_VALUE')],timeout=45)
 r.raise_for_status()
 p,d,b,operations,daily,rolling=[x.get('values',[]) for x in r.json()['valueRanges']]
 def n(x):
  if isinstance(x,bool):raise ValueError('Invalid numeric cell')
  if isinstance(x,str):
   x=x.replace('\u00a0','').replace(' ','').replace(',','.')
   try:x=float(x)
   except ValueError:raise ValueError('Invalid numeric cell')
  if not isinstance(x,(int,float)):raise ValueError('Invalid numeric cell')
  return round(float(x),2)
 def v(rows,row,col=1):return n(rows[row-1][col])
 now=dt.datetime.now(ZoneInfo('Europe/Moscow'));today=now.date()
 daily,current_deficit=ensure_daily_target(AuthorizedSession(c),SID,operations,daily,rolling,now)
 # The family-wide accumulated deficit is temporarily shown as the dated
 # 14 October snapshot. Do not extrapolate it from the incomplete cash ledger.
 family_deficit=v(p,8)
 dayrow=next((x for x in daily[1:] if x and x[0]==today.strftime('%d.%m.%Y')),None)
 if dayrow is None and today<dt.date(2026,11,21):
  dayrow=next((x for x in d[1:] if x and x[0]==today.strftime('%d.%m.%Y')),None)
  legacy_day=True
 else:
  legacy_day=False
 cats=[('Шаббат',5,2,4),('Продукты',6,2,1),('Прочие дети',7,2,1),('Бытовая химия',8,2,1),('Аренда',35,1,1),('Психолог',36,1,1),('Седжаро',37,1,1),('Прочее лечение',38,1,1),('Уход за собой',39,1,1),('Развозка',29,1,1),('Хор',30,1,1),('Сотовая связь',17,1,1),('Интернет',18,1,1),('Страхование квартиры',19,1,1),('Рассрочка — Алиса с экраном',20,1,1),('Рассрочка — Алиса в гостиной',21,1,1)]

 def parse_date(x):
  try:return dt.datetime.strptime(str(x).strip(),'%d.%m.%Y').date()
  except (ValueError,TypeError):return None
 def classify(x):
  category=str(x[6] if len(x)>6 else '').strip().casefold()
  sub=str(x[7] if len(x)>7 else '').strip().casefold()
  title=str(x[2] if len(x)>2 else '').strip().casefold()
  if "интернет" in sub and ("связь" in category or "интернет" in category or "интернет" in title):return "Интернет"
  if "мобильная связь" in sub or (category=="связь" and ("телефон" in title or "пополн" in title)):return "Сотовая связь"
  if "страхован" in (sub+" "+title) and "квартир" in (category+" "+sub+" "+title):return "Страхование квартиры"
  if "алиса" in title or "станция" in title or "алиса" in sub:
   if "экран" in (sub+" "+title):return "Рассрочка — Алиса с экраном"
   if "гостин" in (sub+" "+title):return "Рассрочка — Алиса в гостиной"
  if 'шаббат' in sub or (category=='семейное питание' and 'шаббат' in title):return 'Шаббат'
  if category=='питание' and sub in ('продукты','фастфуд','рыба','овощи','фрукты'):return 'Продукты'
  if category=='продукты' and sub not in ('резерв: покупки к шаббату',):return 'Продукты'
  if category=='дети':
   if 'хор' in sub:return 'Хор'
   if 'развоз' in sub:return 'Развозка'
   return 'Прочие дети'
  if category=='быт и хозяйство' and sub=='бытовая химия':return 'Бытовая химия'
  if category=='жильё' and ('квартир' in sub or 'аренд' in sub):return 'Аренда'
  if 'психолог' in sub:return 'Психолог'
  if 'седжаро' in sub:return 'Седжаро'
  if category=='здоровье и уход' and ('лекарств' in sub or 'лечение' in sub):return 'Прочее лечение'
  if category=='личные расходы' and 'уход за собой' in sub:return 'Уход за собой'
  return None
 def actuals(start,end):
  # Q is the budget cycle assigned to the transaction; A is the payment date.
  # R is the explicit budget category. Never add a second prepaid amount.
  spent={name:0.0 for name,_,_,_ in cats}
  unmapped=[]
  for ix,x in enumerate(operations[1:],2):
   # Q may hold a formula error; fall back to assigned-cycle date P, then cash date A.
   date=next((d0 for d0 in (parse_date(x[16] if len(x)>16 else None),parse_date(x[15] if len(x)>15 else None),parse_date(x[0] if x else None)) if d0 is not None),None)
   if date is None or not start<=date<=end:continue
   if len(x)<10 or str(x[1]).strip()!='Расход' or str(x[4]).strip()!='RUB' or str(x[5]).strip()!='Совершено' or str(x[9]).strip()!='Факт':continue
   try:amount=n(x[3])
   except (ValueError,TypeError):continue
   if amount<0:continue
   allowed={item[0] for item in cats}|{'Покупки к Шаббату'}
   explicit=next((v for i in (18,17) if (v:=str(x[i]).strip() if len(x)>i else '') in allowed),'')
   name=({'Покупки к Шаббату':'Шаббат','Шаббат':'Шаббат'}.get(explicit,explicit) if explicit else classify(x))
   if name:spent[name]=round(spent[name]+amount,2)
   else:unmapped.append({'row':ix,'amount':amount,'category':str(x[6]),'subcategory':str(x[7])})
  return spent,unmapped

 def cycle_start(day):
  return dt.date(day.year,day.month,21) if day.day>=21 else (dt.date(day.year-1,12,21) if day.month==1 else dt.date(day.year,day.month-1,21))
 def shift_month(date,months):
  y=date.year+(date.month-1+months)//12
  m=(date.month-1+months)%12+1
  return dt.date(y,m,21)
 def sheet_date(value):
  if isinstance(value,(int,float)):
   return dt.date(1899,12,30)+dt.timedelta(days=int(value))
  if isinstance(value,str):
   return dt.datetime.strptime(value,'%d.%m.%Y').date()
  raise ValueError('Invalid rolling cycle date')
 categories=[str(rolling[row-1][0]) for row in range(6,23)]
 cycles=[]
 for i in range(3):
  start=sheet_date(rolling[2][i+1])
  end=sheet_date(rolling[3][i+1])
  if end<start or (i>0 and start!=sheet_date(rolling[3][i])+dt.timedelta(days=1)):
   raise ValueError('Rolling budget dates are inconsistent')
  spent,unmapped=actuals(start,min(end,today)) if today>=start else ({},[])
  budgets=[]
  for row,name in enumerate(categories,6):
   limit=v(rolling,row,i+1)
   if name=='Подписки (USD-резерв)':
    # USD 75 is already removed from the available currency before conversion.
    # Display this budget line, but never add its RUB equivalent to expenses.
    budgets.append({'name':name,'limit':limit,'spent':None,'prepaid':0,
     'informational':True,'accountingNote':'75 USD на подписки уже вычтены из доступной валюты. Сумма показана справочно по сценарному курсу, не прибавляется к рублёвым расходам.'})
   else:
    budgets.append({'name':name,'limit':limit,'spent':round(spent.get(name,0),2),'prepaid':0})
  income=v(rolling,33,i+1)
  expenses=v(rolling,35,i+1)
  cycles.append({'label':f'{start:%d.%m.%Y}–{end:%d.%m.%Y}',
   'income':income,'expenses':expenses,'possibleReturn':None,
   'budgets':budgets,'unmappedExpenses':unmapped})
 report={'asOf':now.strftime('%d.%m.%Y %H:%M МСК'),'familyDeficit':family_deficit,'balance':v(p,28),'deficit':max(0,float(current_deficit)) if current_deficit is not None else v(p,8),'rubDebts':[{'name':name,'amount':v(p,row)} for name,row in [('Цдока МЕОЦ',9),('Маме',10),('Бюджет МЕОЦ',11),('Собственный ГМАХ',12)]],'usdDebt':v(p,13),'rate':v(b,13),'savedRub':v(p,55),'reserveTargetRub':v(p,26),'day':{'target':n(dayrow[5] if legacy_day else dayrow[3]),'received':n(dayrow[6] if legacy_day else dayrow[4])} if dayrow else None,'cycles':cycles,'children':[{'name':name,'amount':v(p,row)} for name,row in [('Дочь',47),('Леви',48),('Давид',49)]],'installments':[{'name':'Алиса с экраном','count':2,'payment':v(p,45)/2},{'name':'Алиса в гостиной','count':4,'payment':v(p,46)/4}]}

 encrypt_report(report,os.environ['FINANCE_OWNER_PASSWORD'],'finance/data/owner.enc')
 # Only family-appropriate fields go into the separate ciphertext.
 active=0 if today>=dt.date(2026,11,21) else None
 family={'asOf':report['asOf'],'cycle':None}
 if active is not None:
  current=next((x for x in cycles if x['label'].startswith(f'{cycle_start(today):%d.%m.%Y}')),None)
  if current:
   family['cycle']={'label':current['label'],'income':current['income'],'expenses':current['expenses'],
    'possibleReturn':current['possibleReturn'],'budgets':current['budgets'],'unmappedExpenses':current['unmappedExpenses']}
 encrypt_report(family,os.environ['WIFE_PASSWORD'],'finance/data/family.enc')
 print('Owner and family encrypted reports created')

if __name__=='__main__':main()
