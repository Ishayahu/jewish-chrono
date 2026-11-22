"""Regression tests for fixed daily goals and nonduplicating planned cash flows."""
import datetime as dt
import unittest
from decimal import Decimal
from finance.daily_target import forecast,daily_target,cycle_start,next_cycle

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
 def test_prepayment_not_counted_twice(self):
  r=tx("19.11.2026","Расход",6000,subcategory="Уход за собой",category="Личные расходы",assigned="21.11.2026")
  self.assertEqual(forecast(PLAN,[[],r],dt.date(2026,11,23)),self.baseline()-6000)
 def test_cycle_ends(self):
  self.assertEqual(cycle_start(dt.date(2026,12,20)),dt.date(2026,11,21))
  self.assertEqual(next_cycle(dt.date(2026,12,21)),dt.date(2027,1,21))
  self.assertEqual(daily_target(PLAN,[],dt.date(2026,12,20))[1],1)

if __name__=="__main__":unittest.main()
