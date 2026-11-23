# VERSION: 2026-11-23T11:55:00+03:00
"""Read cached budget figures from the user's saved LibreOffice Calc book.

The book, not this module, owns income/expense arithmetic. This module only
extracts and validates three 14-row financial cycles, with no data upload.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

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
