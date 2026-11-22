"""Budget forecast and idempotent daily goal fixation for the family finance sheet."""
import datetime as dt
import json
from decimal import Decimal, ROUND_HALF_UP

ZERO=Decimal("0.00")
FIRST=dt.date(2026,11,21)
SHEET_ID=782341095

def money(x):
 if isinstance(x,bool): raise ValueError("Invalid money value")
 if isinstance(x,str): x=x.replace("\u00a0","").replace(" ","").replace(",","." ).replace("₽","").strip()
 return Decimal(str(x)).quantize(Decimal(".01"),rounding=ROUND_HALF_UP)

def day(x):
 if isinstance(x,(int,float)) and not isinstance(x,bool):
  return dt.date(1899,12,30)+dt.timedelta(days=int(x))
 try: return dt.datetime.strptime(str(x).strip(),"%d.%m.%Y").date()
 except (TypeError,ValueError):return None

def cycle_start(x):
 if x.day>=21:return dt.date(x.year,x.month,21)
 if x.month==1:return dt.date(x.year-1,12,21)
 return dt.date(x.year,x.month-1,21)

def next_cycle(x):
 return dt.date(x.year+(x.month==12),x.month%12+1,21)

def classify(r,budgets):
 explicit=str(r[17]).strip() if len(r)>17 else ""
 if explicit in budgets:return explicit
 if explicit=="Покупки к Шаббату":return "Шаббат"
 cat=str(r[6] if len(r)>6 else "").strip().casefold()
 sub=str(r[7] if len(r)>7 else "").strip().casefold()
 title=str(r[2] if len(r)>2 else "").strip().casefold()
 if "шаббат" in sub or (cat=="семейное питание" and "шаббат" in title):return "Шаббат"
 if (cat=="питание" and sub in ("продукты","фастфуд","рыба","овощи","фрукты")) or cat=="продукты":return "Продукты"
 if cat=="дети":
  if "хор" in sub:return "Хор"
  if "развоз" in sub:return "Развозка"
  return "Прочие дети"
 if cat=="быт и хозяйство" and sub=="бытовая химия":return "Бытовая химия"
 if cat=="жильё" and ("квартир" in sub or "аренд" in sub):return "Аренда"
 if "психолог" in sub:return "Психолог"
 if "седжаро" in sub:return "Седжаро"
 if cat=="здоровье и уход" and ("лекарств" in sub or "лечение" in sub):return "Прочее лечение"
 if cat=="личные расходы" and "уход за собой" in sub:return "Уход за собой"
 return None

def plan_from_rolling(rows,col,opening):
 start=day(rows[2][col]);end=day(rows[3][col])
 if not start or end!=next_cycle(start)-dt.timedelta(days=1):raise ValueError("Invalid rolling cycle")
 limits={str(rows[i-1][0]):float(money(rows[i-1][col])) for i in range(6,17)}
 regular=money(rows[26][col])*money(rows[27][col])+money(rows[28][col])
 lessons=money(rows[32][col])-regular
 if lessons<0:raise ValueError("Negative planned lesson income")
 return {"start":start.strftime("%d.%m.%Y"),"end":end.strftime("%d.%m.%Y"),
         "opening":float(money(opening)),"budgets":limits,
         "misc":float(money(rows[33][col])),"regular":float(regular),"lessons":float(lessons)}

def forecast(plan,ops,before):
 """Opening deficit + actual expenses + remaining plan - actual income - remaining plan.
 Money earned/received today is excluded when called with before=today for fixation."""
 start=day(plan["start"])
 budgets={k:money(v) for k,v in plan["budgets"].items()}
 spent={k:ZERO for k in budgets}
 prepaid={k:ZERO for k in budgets}
 spent_misc=prepaid_misc=actual_inc=actual_exp=salary=lessons=ZERO
 for r in ops[1:]:
  if len(r)<12 or str(r[4]).strip()!="RUB" or str(r[5]).strip()!="Совершено" or str(r[9]).strip()!="Факт":continue
  cash=day(r[0])
  if cash is None or cash>=before:continue
  direction=str(r[1]).strip()
  if direction not in ("Приход","Расход"):continue
  # A signed RUB amount can be a confirmed refund/reversal (e.g. -339.98 RUB).
  # Keep it signed so the underlying payment is not counted twice.
  amount=money(r[3])
  if direction=="Расход":
   name=classify(r,budgets)
   assigned=day(r[15]) if len(r)>15 and r[15] else None
   if cash<start and assigned==start:
    if name:prepaid[name]+=amount
    else:prepaid_misc+=amount
   elif start<=cash<before:
    actual_exp+=amount
    if name:spent[name]+=amount
    else:spent_misc+=amount
  elif start<=cash<before:
   reason=str(r[11]).casefold()
   if "получено чистыми" in reason:available=amount
   elif "доступно 80%" in reason:available=money(amount*Decimal(".8"))
   else:available=money(amount*Decimal(".7"))
   actual_inc+=available
   if "плановая зарплата" in reason:salary+=available
   elif str(r[7]).strip().casefold()=="уроки":lessons+=available
 pending_exp=sum((max(ZERO,v-prepaid[k]-spent[k]) for k,v in budgets.items()),ZERO)
 pending_exp+=max(ZERO,money(plan["misc"])-prepaid_misc-spent_misc)
 pending_inc=max(ZERO,money(plan["regular"])-salary)+max(ZERO,money(plan["lessons"])-lessons)
 return money(money(plan["opening"])+actual_exp+pending_exp-actual_inc-pending_inc)

def extra_daily_income(plan,ops,today):
 """Only available RUB earnings not already included in planned salaries/lessons.
 Reimbursements change the overall deficit but must not create a debt-saving bonus."""
 start=day(plan["start"])
 planned_lessons=money(plan["lessons"])
 allocated_lessons=ZERO
 eligible=ZERO
 items=[]
 for r in ops[1:]:
  if len(r)<12 or str(r[1]).strip()!="Приход" or str(r[4]).strip()!="RUB":continue
  if str(r[5]).strip()!="Совершено" or str(r[9]).strip()!="Факт":continue
  cash=day(r[0])
  if cash is None or not start<=cash<=today:continue
  items.append((cash,r))
 items.sort(key=lambda pair:pair[0])
 for cash,r in items:
  amount=money(r[3])
  note=str(r[11]).casefold()
  if "получено чистыми" in note:available=amount
  elif "доступно 80%" in note:available=money(amount*Decimal(".8"))
  else:available=money(amount*Decimal(".7"))
  sub=str(r[7] if len(r)>7 else "").strip().casefold()
  category=str(r[6] if len(r)>6 else "").strip().casefold()
  title=str(r[2] if len(r)>2 else "").strip().casefold()
  if "плановая зарплата" in note:extra=ZERO
  elif sub=="уроки":
   still_planned=max(ZERO,planned_lessons-allocated_lessons)
   planned_part=min(still_planned,available)
   allocated_lessons+=planned_part
   extra=available-planned_part
  elif "компенсац" in title or "возмещен" in title or "компенсац" in sub or category=="целевые поступления":
   extra=ZERO
  else:extra=available
  if cash==today:eligible+=extra
 return money(eligible)

def rows_by_date(daily):
 return {day(r[0]):(i+4,r) for i,r in enumerate(daily) if r and day(r[0])}

def cycle_opening(start,daily,ops):
 existing=rows_by_date(daily)
 if start==FIRST:
  first=existing.get(FIRST)
  if not first or len(first[1])<2:raise ValueError("Missing 21 November deficit anchor")
  return money(first[1][1])
 prev=cycle_start(start-dt.timedelta(days=1))
 row=existing.get(prev)
 if not row or len(row[1])<11 or not row[1][10]:raise ValueError("Previous cycle plan snapshot missing")
 plan=json.loads(row[1][10])
 if day(plan["start"])!=prev:raise ValueError("Previous plan date mismatch")
 return forecast(plan,ops,start)

def daily_target(plan,ops,date):
 end=day(plan["end"]);start=day(plan["start"])
 if not start<=date<=end:raise ValueError("Goal outside cycle")
 left=(end-date).days+1
 deficit=forecast(plan,ops,date)
 return deficit,left,money(max(ZERO,deficit)/Decimal(left))

def cellval(v):
 if isinstance(v,str):return {"userEnteredValue":{"stringValue":v}}
 return {"userEnteredValue":{"numberValue":float(v)}}

def range_for(row,c1,c2):
 return {"sheetId":SHEET_ID,"startRowIndex":row-1,"endRowIndex":row,"startColumnIndex":c1,"endColumnIndex":c2}

def update_row(row,c1,values):
 return {"updateCells":{"range":range_for(row,c1,c1+len(values)),"rows":[{"values":[cellval(v) for v in values]}],"fields":"userEnteredValue"}}

def ensure_daily_target(session,sid,ops,daily,rolling,now):
 """Use the same GitHub script from both workflows; 05:00 is a boundary, not a trigger."""
 today=now.date();start=cycle_start(today)
 if start<FIRST:return daily,None
 plan=plan_from_rolling(rolling,1,cycle_opening(start,daily,ops))
 if day(plan["start"])!=start:raise ValueError("Rolling budget date differs from Moscow cycle")
 live=forecast(plan,ops,today+dt.timedelta(days=1))
 # Verify this GitHub Actions service account has spreadsheet EDIT permission even
 # before the first 05:00 fixation. A no-match replace does not modify cells.
 probe=session.post(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}:batchUpdate",
  json={"requests":[{"findReplace":{"find":"__finance_write_probe_20261123_no_match__",
   "replacement":"__finance_write_probe_20261123_no_match__",
   "sheetId":SHEET_ID,"matchCase":True}}]},timeout=45)
 probe.raise_for_status()
 if now.hour<5:return daily,live
 rows=rows_by_date(daily)
 existing=rows.get(today)
 actions=[]
 added={}
 if not existing or len(existing[1])<4 or existing[1][3] in ("",None):
  if existing:
   rownum=existing[0]
   opening,remaining,target=daily_target(plan,ops,today)
   actions.append(update_row(rownum,0,[today.strftime("%d.%m.%Y"),opening,remaining,target]))
  else:
   last=max((r for r,_ in rows.values()),default=4)
   latest=max((date for date in rows if date and date<=today),default=start-dt.timedelta(days=1))
   for step in range(1,(today-latest).days+1):
    date=latest+dt.timedelta(days=step)
    if date<start:continue
    last+=1
    added[date]=last
    if last>400:raise ValueError("Daily goal grid is full")
    opening,remaining,target=daily_target(plan,ops,date)
    actions.append({"copyPaste":{"source":range_for(last-1,0,9),
     "destination":range_for(last,0,9),"pasteType":"PASTE_NORMAL","pasteOrientation":"NORMAL"}})
    actions.append(update_row(last,0,[date.strftime("%d.%m.%Y"),opening,remaining,target]))
   rownum=last
 else:
  rownum=existing[0]
 # E is the extra earned money, not the already-budgeted salary / lesson forecast.
 # Write a number to cover text-valued numerics such as "1293,70".
 actions.append(update_row(rownum,4,[extra_daily_income(plan,ops,today)]))
 # Only live forecast / timestamp may change after the target has been fixed.
 actions.append(update_row(rownum,8,[live,now.strftime("%d.%m.%Y %H:%M:%S МСК")]))
 # Preserve the current cycle's plan snapshot to reconstruct a rollover.
 first=rows.get(start)
 first_row=first[0] if first else added.get(start)
 if first_row:
  actions.append(update_row(first_row,10,[json.dumps(plan,ensure_ascii=False,separators=(",",":"))]))
 if actions:
  response=session.post(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}:batchUpdate",
                        json={"requests":actions},timeout=45)
  response.raise_for_status()
  from urllib.parse import quote
  a1=quote("'Утренняя цель — новая схема'!A4:L400",safe="")
  confirm=session.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{a1}",
                      params={"valueRenderOption":"UNFORMATTED_VALUE"},timeout=45)
  confirm.raise_for_status()
  daily=confirm.json().get("values",[])
  verified=rows_by_date(daily).get(today)
  if not verified or len(verified[1])<4 or not isinstance(verified[1][3],(int,float)):
   raise ValueError("Failed to verify stored daily target")
 return daily,live
