"""Regression tests for fixed daily goals and nonduplicating planned cash flows."""
import datetime as dt
import unittest
from decimal import Decimal
from finance.daily_target import forecast,daily_target,cycle_start,next_cycle,extra_daily_income,cumulative_family_deficit

PLAN={"start":"21.11.2026","end":"20.12.2026","opening":37862.85,
      "budgets":{"Аренда":185000.0,"Прочие дети":5000.0,"Уход за собой":20000.0},
      "misc":5920.0,"regular":279980.0,"lessons":57600.0}

def tx(date,direction,amount,subcategory="",reason="",category="",assigned=""):
 row=[""]*18
 row[0]=date;row[1]=direction;row[2]="test";row[3]=amount
 row[4]="RUB";row[5]="Совершено";row[6]=category;row[7]=subcategory
 row[9]="Факт";row[11]=reason;row[15]=assigned
 return row

class DailyForecastTest(unittest.TestCase):
 def baseline(self):
  return forecast(PLAN,[],dt.date(2026,11,23))
 def test_budget_gap_and_remaining_days(self):
  expected=Decimal("37862.85")+185000+5000+20000+5920-279980-57600
  self.assertEqual(self.baseline(),expected)
  self.assertEqual(daily_target(PLAN,[],dt.date(2026,11,23))[1],28)
 def test_planned_salary_not_double_counted(self):
  r=tx("21.11.2026","Приход",25252.5,reason="Получено чистыми. Плановая зарплата")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline())
 def test_planned_lessons_not_double_counted(self):
  r=tx("22.11.2026","Приход",2400,subcategory="Уроки")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline())
 def test_extra_income_reduces_gap(self):
  r=tx("22.11.2026","Приход",1000,reason="Получено чистыми")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline()-1000)
 def test_budget_spend_consumes_plan(self):
  r=tx("22.11.2026","Расход",3000,category="Дети")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline())
 def test_overspend_increases_gap(self):
  r=tx("22.11.2026","Расход",7000,category="Дети")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline()+2000)
 def test_today_cash_does_not_change_fixed_goal(self):
  r=tx("23.11.2026","Приход",8000,reason="Получено чистыми")
  self.assertEqual(daily_target(PLAN,[[],r],dt.date(2026,11,23)),
                   daily_target(PLAN,[],dt.date(2026,11,23)))
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,24)),self.baseline()-8000)
 def test_extra_income_excludes_budgeted_salary_and_lessons(self):
  earned=[[],tx("23.11.2026","Приход",36075,reason="Плановая зарплата"),
          tx("23.11.2026","Приход",2400,subcategory="Уроки"),
          tx("23.11.2026","Приход",1000,reason="Получено чистыми")]
  self.assertEqual(extra_daily_income(PLAN,earned,dt.date(2026,11,23)),Decimal("1000.00"))
 def test_compensation_not_profit(self):
  r=tx("23.11.2026","Приход","1293,70",subcategory="Компенсация за еду",reason="Получено чистыми")
  self.assertEqual(extra_daily_income(PLAN,[[],r],dt.date(2026,11,23)),Decimal("0.00"))
 def test_lessons_above_plan_are_extra(self):
  short_plan=dict(PLAN,lessons=1680.0)
  records=[[],tx("23.11.2026","Приход",2400,subcategory="Уроки"),
           tx("23.11.2026","Приход",2400,subcategory="Уроки")]
  self.assertEqual(extra_daily_income(short_plan,records,dt.date(2026,11,23)),Decimal("1680.00"))
 def test_prepayment_not_counted_twice(self):
  r=tx("19.11.2026","Расход",6000,subcategory="Уход за собой",category="Личные расходы",assigned="21.11.2026")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline()-6000)
 def test_cumulative_family_deficit_from_historical_snapshot(self):
  records=[[],tx("14.10.2026","Приход",10000,reason="Получено чистыми"),
           tx("15.10.2026","Расход","1677,40"),
           tx("16.10.2026","Приход","13076,52",reason="Получено чистыми"),
           tx("18.10.2026","Приход",2400,subcategory="Уроки")]
  actual=cumulative_family_deficit(records,1128419.73,dt.date(2026,10,14),dt.date(2026,11,23))
  self.assertEqual(actual,Decimal("1113340.61"))
 def test_internal_transfers_and_non_rub_do_not_change_family_deficit(self):
  internal=tx("20.10.2026","Перевод",20000)
  dollar=tx("21.10.2026","Приход",1000);dollar[4]="USD"
  unconfirmed=tx("22.10.2026","Расход",4000);unconfirmed[5]="Ожидается"
  self.assertEqual(cumulative_family_deficit([[],internal,dollar,unconfirmed],100000,dt.date(2026,10,14),dt.date(2026,11,23)),Decimal("100000.00"))
 def test_cycle_ends(self):
  self.assertEqual(cycle_start(dt.date(2026,12,20)),dt.date(2026,11,21))
  self.assertEqual(next_cycle(dt.date(2026,12,21)),dt.date(2027,1,21))
  self.assertEqual(daily_target(PLAN,[],dt.date(2026,12,20))[1],1)

if __name__=="__main__":unittest.main()
