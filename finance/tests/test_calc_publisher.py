# VERSION: 2026-11-23T12:10:00+03:00
"""Synthetic regression tests. Never commit actual household budget fixtures."""
import base64
import io
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from finance.local_calc_model import CalcError,cycles_from_book,fixed_goal,number
from finance import publish_from_calc as pub

class FakeBook:
    def __init__(self,path):
        self.path=path
        self.data={}
        for i,month in enumerate(('2026-12-01','2027-01-01','2027-02-01')):
            r=640+14*i
            self.data[('A',r)]=month
            self.data[('D',r)]='Продукты'
            self.data[('G',r)]=100
            self.data[('C',r)]=20
            self.data[('F',r)]=80
            self.data[('O',r)]='Интернет 720'
            self.data[('R',r)]=20
            self.data[('N',r)]=0
            self.data[('Q',r)]=20
            self.data[('D',r+13)]='ВТОРОЙ СТОЛБЕЦ'
            self.data[('F',r+13)]=20
            self.data[('O',r+3)]='REM'
            self.data[('Q',r+3)]=0
            self.data[('I',r)]=70
            self.data[('J',r)]=1
            self.data[('A',r+8)]=100
            self.data[('A',r+10)]=130
            self.data[('A',r+12)]=-50
    def cell(self,c,r,required=True):
        v=self.data.get((c,r))
        if required and v is None:raise CalcError(f'{c}{r} missing')
        return v
    def num(self,c,r):return number(self.cell(c,r),f'{c}{r}')
    def text(self,c,r):return str(self.cell(c,r,False) or '').strip()

class CalcPublisherTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)/'saved.ods';p.write_bytes(b'test-book')
        self.book=FakeBook(p)
        self.today=date(2026,11,23)
    def test_extracts_three_cycles_without_subtotal(self):
        cycles=cycles_from_book(self.book,self.today)
        self.assertEqual(len(cycles),3)
        self.assertEqual(cycles[0]['income'],130)
        self.assertEqual(cycles[0]['expenses'],100)
        self.assertEqual([b['name'] for b in cycles[0]['budgets']],['Продукты','Интернет'])
    def test_rejects_duplicate_aggregate(self):
        self.book.data[('A',648)]=120
        with self.assertRaisesRegex(CalcError,'разница'):
            cycles_from_book(self.book,self.today)
    def test_frozen_target_and_new_day(self):
        original=fixed_goal(-50,'2026-12-20',self.today)
        self.assertEqual(original['target'],1.79)
        prev={'goalHistory':{self.today.isoformat():original}}
        self.assertEqual(fixed_goal(-9000,'2026-12-20',self.today,prev),original)
        self.assertNotEqual(fixed_goal(-9000,'2026-12-20',date(2026,11,24),prev),original)
    def test_migrate_previous_dashboard_target(self):
        x=fixed_goal(-100,'2026-12-20',self.today,{
          'asOf':'23.11.2026 09:00 МСК','day':{'target':4321,'received':0}})
        self.assertEqual(x['target'],4321)
    def test_owner_report_preserves_legacy_fields(self):
        prev={'familyDeficit':100000,'usdDebt':37000,'rate':82,'savedRub':50,
          'reserveTargetRub':300,'rubDebts':[],'children':[],'installments':[],
          'asOf':'22.11.2026 10:00 МСК'}
        pub.require_legacy_fields(prev)
        report=pub.build_report(self.book,today=self.today,previous=prev)
        self.assertEqual(report['budgetRate'],60)
        self.assertEqual(report['familyDeficit'],100000)
        self.assertEqual(report['cycles'][0]['income'],130)
        self.assertEqual(report['deficit'],50)
        self.assertEqual(pub.build_report(self.book,today=self.today,previous=report)['dailyGoal'],report['dailyGoal'])
    def test_encryption_compatible_with_dashboard(self):
        # Preserve already established (possibly shorter) dashboard passwords.
        key='old-pass'
        data={'day':{'target':5},'dailyGoal':{'date':'2026-11-23','target':5}}
        self.assertEqual(pub.decrypt_report(pub.encrypt_report(data,key),key),data)

    def test_existing_password_prompt_when_environment_is_unset(self):
        with mock.patch.dict('os.environ',{},clear=True), mock.patch.object(pub.getpass,'getpass',return_value='my-current-password') as prompt:
            self.assertEqual(pub.existing_password('FINANCE_OWNER_PASSWORD','Owner'), 'my-current-password')
            prompt.assert_called_once()
        with mock.patch.dict('os.environ',{'FINANCE_OWNER_PASSWORD':'old-pass'}), mock.patch.object(pub.getpass,'getpass') as prompt:
            self.assertEqual(pub.existing_password('FINANCE_OWNER_PASSWORD','Owner'), 'old-pass')
            prompt.assert_not_called()
    def test_live_pages_owner_decrypts_with_existing_browser_password(self):
        password='old-pass'
        previous={'familyDeficit':123456,'day':{'target':120}}
        envelope=pub.encrypt_report(previous,password).encode('utf-8')
        with mock.patch.object(pub.urllib.request,'urlopen',
                               return_value=io.BytesIO(envelope)):
            self.assertEqual(pub.site_previous(password),previous)

    def test_repository_snapshot_with_wrong_password_uses_live_site(self):
        old=pub.encrypt_report({'state':'old'},'obsolete-password')
        def fake_github(method,endpoint,token):
            if endpoint.startswith('git/ref/'):
                return {'object':{'sha':'abc'}}
            return {'content':base64.b64encode(old.encode('utf-8')).decode('ascii')}
        with mock.patch.object(pub,'github_json',side_effect=fake_github), \
             mock.patch.object(pub,'site_previous',return_value={'state':'current'}) as live:
            head,previous=pub.remote_previous('token','old-pass')
        self.assertEqual(head,'abc')
        self.assertEqual(previous,{'state':'current'})
        live.assert_called_once_with('old-pass')

    def test_refuses_old_remote_workflow(self):
        with mock.patch.object(pub,'github_json',return_value={
          'content':base64.b64encode(b'python finance/build_encrypted.py').decode()}):
            with self.assertRaises(pub.PublisherError):pub.require_switched_workflow('test-token')

if __name__=='__main__':unittest.main()
