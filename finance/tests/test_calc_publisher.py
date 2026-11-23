# VERSION: 2026-11-23T17:25:00+03:00
"""Synthetic regression tests. Never commit actual household budget fixtures."""
import base64
import io
import runpy
import zipfile
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from finance import publish_from_calc as pub
from finance.publish_from_calc import CalcError,cycles_from_book,fixed_goal,number

class FakeBook:
    def __init__(self,path):
        self.path=path
        self.data={}
        self.source_values={
            ('Мои','C50'):100,('Мои','C57'):150,('Мои','C68'):4321,
            ('Сводка','I23'):-36000,('Сводка','I14'):-200,
            ('Сводка','I17'):-300,('Сводка','I9'):-400,
            ('ГМАХ мой','C5'):500,
        }
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
    def source_num(self,sh,ref):
        if (sh,ref) not in self.source_values:
            raise CalcError(f'Missing cached source cell {sh}!{ref}')
        return pub.money(self.source_values[(sh,ref)],f'{sh}!{ref}')
    def text(self,c,r):return str(self.cell(c,r,False) or '').strip()

class CalcPublisherTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)/'saved.ods';p.write_bytes(b'test-book')
        self.book=FakeBook(p)
        self.today=date(2026,11,23)
    def test_single_python_file_runs_without_sibling_module(self):
        namespace=runpy.run_path(str(Path(pub.__file__)),run_name='__standalone_test__')
        self.assertIn('Workbook',namespace)
        self.assertIn('fixed_goal',namespace)
        self.assertIn('main',namespace)
        self.assertEqual(
            namespace['cycles_from_book'](self.book,self.today)[0]['income'],
            130,
        )

    def test_extracts_three_cycles_without_subtotal(self):
        cycles=cycles_from_book(self.book,self.today)
        self.assertEqual(len(cycles),3)
        self.assertEqual(cycles[0]['income'],130)
        self.assertEqual(cycles[0]['expenses'],100)
        self.assertEqual([b['name'] for b in cycles[0]['budgets']],['Продукты','Интернет'])
    def test_rejects_duplicate_aggregate(self):
        self.book.data[('A',648)]=120
        with self.assertRaisesRegex(CalcError,'difference'):
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
        self.assertEqual(report['familyDeficit'],4321)
        self.assertEqual(report['savedRub'],250)
        self.assertEqual(report['usdDebt'],36000)
        self.assertEqual(report['savingsAccounts'],[
            {'name':'Т-Банк','amount':100.0,'source':'Мои!C50'},
            {'name':'Сбербанк','amount':150.0,'source':'Мои!C57'},
        ])
        self.assertEqual(report['rubDebts'],[
            {'name':'Цдока МЕОЦ','amount':200},
            {'name':'Мама','amount':300},
            {'name':'Бюджет МЕОЦ','amount':400},
            {'name':'Свой ГМАХ','amount':500},
        ])
        self.assertNotIn('reserveTargetRub',report)
        self.assertEqual(report['children'],[])
        self.assertEqual(report['installments'],[])
        self.assertEqual(report['cycles'][0]['income'],130)
        self.assertEqual(report['deficit'],50)
        self.assertEqual(pub.build_report(self.book,today=self.today,previous=report)['dailyGoal'],report['dailyGoal'])
    def test_missing_source_cell_blocks_publication(self):
        self.book.source_values.pop(('Сводка','I23'))
        prev={'rate':82,'children':[],'installments':[]}
        with self.assertRaisesRegex(CalcError,'Сводка!I23'):
            pub.build_report(self.book,today=self.today,previous=prev)

    def test_debt_positive_balance_is_not_silently_recast_as_a_debt(self):
        self.book.source_values[('Сводка','I14')]=100
        prev={'rate':82,'children':[],'installments':[]}
        with self.assertRaisesRegex(CalcError,'Сводка!I14'):
            pub.build_report(self.book,today=self.today,previous=prev)

    def test_ods_reader_extracts_extra_sheets_and_repeated_cells(self):
        def make_sheet(name, refs):
            rows=[]
            previous=0
            for row_num,column,val in sorted(refs,key=lambda x:x[0]):
                if row_num>previous+1:
                    rows.append(f'<table:table-row table:number-rows-repeated="{row_num-previous-1}"/>')
                col_no=pub.colindex(column)
                cell=(f'<table:table-cell office:value-type="float" office:value="{val}"/>')
                rows.append('<table:table-row>'+(
                    f'<table:table-cell table:number-columns-repeated="{col_no}"/>'
                    if col_no else '')+cell+'</table:table-row>')
                previous=row_num
            return f'<table:table table:name="{name}">'+''.join(rows)+'</table:table>'
        xml=(
            '<office:document-content '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            '<office:body><office:spreadsheet>'+
            make_sheet('Семейные Траты',[(640,'A',1)])+
            make_sheet('Мои',[(50,'C',123.45),(57,'C',678.90),(68,'C',9123.456)])+
            make_sheet('Сводка',[(9,'I',-9876),(14,'I',-543210.987),
                                 (17,'I',-71000),(23,'I',-24680)])+
            make_sheet('ГМАХ мой',[(5,'C',12000)])+
            '</office:spreadsheet></office:body></office:document-content>'
        )
        path=Path(self.tmp.name)/'synthetic.ods'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('content.xml',xml.encode('utf-8'))
        book=pub.Workbook(path)
        self.assertEqual(book.source_num('Мои','C50'),pub.Decimal('123.45'))
        self.assertEqual(book.source_num('Мои','C57'),pub.Decimal('678.90'))
        self.assertEqual(book.source_num('Мои','C68'),pub.Decimal('9123.46'))
        self.assertEqual(book.source_num('Сводка','I23'),pub.Decimal('-24680.00'))
        self.assertEqual(book.source_num('Сводка','I14'),pub.Decimal('-543210.99'))
        self.assertEqual(book.source_num('Сводка','I17'),pub.Decimal('-71000.00'))
        self.assertEqual(book.source_num('Сводка','I9'),pub.Decimal('-9876.00'))
        self.assertEqual(book.source_num('ГМАХ мой','C5'),pub.Decimal('12000.00'))

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
    def test_scheduled_run_fails_without_password_without_prompting(self):
        with mock.patch.dict('os.environ',{},clear=True), \
             mock.patch.object(pub.getpass,'getpass') as prompt:
            with self.assertRaisesRegex(pub.PublisherError,'FINANCE_OWNER_PASSWORD'):
                pub.existing_password('FINANCE_OWNER_PASSWORD','Owner',non_interactive=True)
            prompt.assert_not_called()

    def test_scheduled_run_reuses_persistent_environment(self):
        with mock.patch.dict('os.environ',{'FINANCE_OWNER_PASSWORD':'password-from-user-env'}), \
             mock.patch.object(pub.getpass,'getpass') as prompt:
            self.assertEqual(pub.existing_password('FINANCE_OWNER_PASSWORD','Owner',
                             non_interactive=True),'password-from-user-env')
            prompt.assert_not_called()

    def test_scheduled_run_can_use_github_cli_and_never_prompts(self):
        proc=mock.Mock(returncode=0,stdout='token-from-gh\\n')
        with mock.patch.dict('os.environ',{},clear=True), \
             mock.patch.object(pub.subprocess,'run',return_value=proc), \
             mock.patch.object(pub.getpass,'getpass') as prompt:
            self.assertEqual(pub.github_token(non_interactive=True),'token-from-gh')
            prompt.assert_not_called()

    def test_scheduled_run_fails_without_github_credentials(self):
        proc=mock.Mock(returncode=1,stdout='')
        with mock.patch.dict('os.environ',{},clear=True), \
             mock.patch.object(pub.subprocess,'run',return_value=proc), \
             mock.patch.object(pub.getpass,'getpass') as prompt:
            with self.assertRaisesRegex(pub.PublisherError,'No GitHub credentials'):
                pub.github_token(non_interactive=True)
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

    def test_guarded_workflows_are_required_both_places(self):
        ready=b'# LOCAL_CALC_SNAPSHOT_READY\n# test -s finance/data/owner.enc && test -s finance/data/family.enc'
        def fetch(method,endpoint,token):
            self.assertIn('workflows/',endpoint)
            return {'content':base64.b64encode(ready).decode('ascii')}
        with mock.patch.object(pub,'github_json',side_effect=fetch) as calls:
            pub.require_switched_workflow('test-token')
        self.assertEqual(calls.call_count,2)

    def test_first_publish_retains_local_fixed_goal(self):
        goal={'date':'2026-11-23','target':500.25}
        remote={'asOf':'23.11.2026 10:00 МСК','familyDeficit':123}
        local={'asOf':'23.11.2026 13:00 МСК','dailyGoal':goal,
               'goalHistory':{'2026-11-23':goal}}
        merged=pub.merge_first_local_goal(remote,local,self.today)
        self.assertEqual(merged['dailyGoal'],goal)
        self.assertEqual(merged['familyDeficit'],123)
        self.assertEqual(merged['goalHistory']['2026-11-23'],goal)

    def test_after_first_git_upload_remote_fixed_goal_wins(self):
        goal={'date':'2026-11-23','target':450.0}
        remote={'budgetSource':{'workbookSheet':'Семейные Траты'},
                'dailyGoal':goal,'goalHistory':{'2026-11-23':goal}}
        local={'dailyGoal':{'date':'2026-11-23','target':999}}
        self.assertIs(pub.merge_first_local_goal(remote,local,self.today),remote)

    def test_refuses_old_remote_workflow(self):
        with mock.patch.object(pub,'github_json',return_value={
          'content':base64.b64encode(b'python finance/build_encrypted.py').decode()}):
            with self.assertRaises(pub.PublisherError):pub.require_switched_workflow('test-token')

if __name__=='__main__':unittest.main()
