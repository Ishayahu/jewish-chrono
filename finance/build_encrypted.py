import os,json,base64,secrets,datetime as dt
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
SID='1nQNEresKTI0b5LzVhmZQhT0AFLmqWhKNlz369CIoCPU'
ranges=["'Финансовая позиция'!A1:B53","'Дневное распределение'!A4:K130","'Бюджет — с 21.11.2026'!A1:D40","'Операции'!A1:N1000"]
def encrypt_report(report,password,filename):
 if len(password)<12:raise ValueError('Password too short')
 salt,iv=secrets.token_bytes(16),secrets.token_bytes(12)
 key=PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=salt,iterations=600000).derive(password.encode())
 enc=lambda x:base64.b64encode(x).decode()
 out={'v':1,'kdf':'PBKDF2-SHA256','cipher':'AES-256-GCM','iterations':600000,'salt':enc(salt),'iv':enc(iv),'ciphertext':enc(AESGCM(key).encrypt(iv,json.dumps(report,ensure_ascii=False).encode(),None))}
 from pathlib import Path
 Path(filename).write_text(json.dumps(out))

def main():
 c=service_account.Credentials.from_service_account_info(json.loads(os.environ['FINANCE_GOOGLE_SERVICE_ACCOUNT_JSON']),scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
 r=AuthorizedSession(c).get(f'https://sheets.googleapis.com/v4/spreadsheets/{SID}/values:batchGet',params=[('ranges',x) for x in ranges]+[('valueRenderOption','UNFORMATTED_VALUE')],timeout=45)
 r.raise_for_status()
 p,d,b,operations=[x.get('values',[]) for x in r.json()['valueRanges']]
 def n(x):
  if isinstance(x,bool) or not isinstance(x,(int,float)):raise ValueError('Invalid numeric cell')
  return round(float(x),2)
 def v(rows,row,col=1):return n(rows[row-1][col])
 now=dt.datetime.now(ZoneInfo('Europe/Moscow'));today=now.date()
 dayrow=next((x for x in d[1:] if x and x[0]==today.strftime('%d.%m.%Y')),None)
 cats=[('Шаббат',5,2,4),('Продукты',6,2,1),('Прочие дети',7,2,1),('Бытовая химия',8,2,1),('Аренда',35,1,1),('Психолог',36,1,1),('Седжаро',37,1,1),('Прочее лечение',38,1,1),('Уход за собой',39,1,1),('Развозка',29,1,1),('Хор',30,1,1)]

 def parse_date(x):
  try:return dt.datetime.strptime(str(x).strip(),'%d.%m.%Y').date()
  except (ValueError,TypeError):return None
 def classify(x):
  category=str(x[6] if len(x)>6 else '').strip().casefold()
  sub=str(x[7] if len(x)>7 else '').strip().casefold()
  title=str(x[2] if len(x)>2 else '').strip().casefold()
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
  spent={name:0.0 for name,_,_,_ in cats}
  unmapped=[]
  for ix,x in enumerate(operations[1:],2):
   date=parse_date(x[0] if x else None)
   if date is None or not start<=date<=end:continue
   if len(x)<10 or str(x[1]).strip()!='Расход' or str(x[4]).strip()!='RUB' or str(x[5]).strip()!='Совершено' or str(x[9]).strip()!='Факт':continue
   try:amount=n(x[3])
   except (ValueError,TypeError):continue
   if amount<0:continue
   name=classify(x)
   if name:spent[name]=round(spent[name]+amount,2)
   else:unmapped.append({'row':ix,'amount':amount,'category':str(x[6]),'subcategory':str(x[7])})
  return spent,unmapped

 cycles=[]
 for i,(start,end) in enumerate([(dt.date(2026,11,21),dt.date(2026,12,20)),(dt.date(2026,12,21),dt.date(2027,1,20))]):
  spent,unmapped=actuals(start,min(end,today)) if today>=start else ({},[])
  budgets=[{'name':name,'limit':(500*(5 if i==0 else 4) if name=='Хор' else v(b,row,col+i if row in (35,36,37,38,39) else col)*factor),'spent':spent.get(name,0.0)} for name,row,col,factor in cats]
  cycles.append({'label':f'{start:%d.%m.%Y}–{end:%d.%m.%Y}','income':v(b,17,i+1),'expenses':v(b,16,i+1),'possibleReturn':v(b,19,i+1),'budgets':budgets,'unmappedExpenses':unmapped})
 report={'asOf':now.strftime('%d.%m.%Y %H:%M МСК'),'balance':v(p,28),'deficit':v(p,8),'rubDebts':[{'name':name,'amount':v(p,row)} for name,row in [('Цдока МЕОЦ',9),('Маме',10),('Бюджет МЕОЦ',11),('Собственный ГМАХ',12)]],'usdDebt':v(p,13),'rate':v(b,13),'savedRub':v(p,52),'reserveTargetRub':v(p,26),'day':{'target':n(dayrow[5]),'received':n(dayrow[6])} if dayrow else None,'cycles':cycles,'children':[{'name':name,'amount':v(p,row)} for name,row in [('Дочь',47),('Леви',48),('Давид',49)]],'installments':[{'name':'Алиса с экраном','count':2,'payment':v(p,45)/2},{'name':'Алиса в гостиной','count':4,'payment':v(p,46)/4}]}

 encrypt_report(report,os.environ['FINANCE_OWNER_PASSWORD'],'finance/data/owner.enc')
 # Only family-appropriate fields go into the separate ciphertext.
 start_at=[dt.datetime(2026,11,21,18,tzinfo=ZoneInfo('Europe/Moscow')),dt.datetime(2026,12,21,0,tzinfo=ZoneInfo('Europe/Moscow'))]
 active=next((i for i,st in enumerate(start_at) if now>=st and now<(start_at[i+1] if i+1<len(start_at) else dt.datetime(2027,1,21,0,tzinfo=ZoneInfo('Europe/Moscow')))),None)
 family={'asOf':report['asOf'],'cycle':None}
 if active is not None:
  c=cycles[active]
  adjustment=500 if active==0 else 0
  family['cycle']={'label':c['label'],'income':c['income'],'expenses':c['expenses']+adjustment,
                   'possibleReturn':c['possibleReturn'],'budgets':c['budgets'],'unmappedExpenses':c['unmappedExpenses']}
 encrypt_report(family,os.environ['WIFE_PASSWORD'],'finance/data/family.enc')
 print('Owner and family encrypted reports created')

if __name__=='__main__':main()
