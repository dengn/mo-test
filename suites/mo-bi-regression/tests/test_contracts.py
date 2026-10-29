import copy,decimal,io,json,os,sys,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import fixtures,native,run,run_sql,spill_recovery

class Comparison(unittest.TestCase):
    def case(self,rows,**opts):return {'id':'test','expected':rows,'policy':'exact','order_check':True,**opts}
    def test_large_money_not_float_tolerated(self):
        case=self.case([['9007199254740993.123456']])
        self.assertIsNotNone(c.compare([[float(decimal.Decimal(case['expected'][0][0]))]],case))
    def test_one_micro_currency_difference_fails(self):
        self.assertIsNotNone(c.compare([['1.000001']],self.case([['1.000000']])))
    def test_null_is_not_zero_or_empty(self):
        for value in ['0','']:
            self.assertIsNotNone(c.compare([[value]],self.case([[None]])))
    def test_exact_decimal_numeric_transport(self):
        self.assertIsNone(c.compare([[decimal.Decimal('1.230000')]],self.case([['1.23']])))
    def test_zero_padded_and_declared_numeric_text_are_exact(self):
        self.assertIsNotNone(c.compare([['1']],self.case([['001']])))
        self.assertIsNotNone(c.compare([['1.2300']],self.case([['1.23']],text_columns=[0])))
    def test_duplicate_rows_are_not_discarded(self):
        self.assertIsNotNone(c.compare([[1]],self.case([['1'],['1']],order_check=False)))
    def test_order_is_checked(self):
        self.assertIsNotNone(c.compare([[2],[1]],self.case([['1'],['2']])))
        self.assertIsNone(c.compare([[2],[1]],self.case([['1'],['2']],order_check=False)))
    def test_approximate_columns_are_explicit(self):
        case=self.case([['1','2']],policy='analytics',approximate_columns=[1])
        self.assertIsNone(c.compare([['1','2.0000005']],case))
        self.assertIsNotNone(c.compare([['1.0000005','2']],case))
    def test_temporal_transport(self):
        self.assertIsNone(c.compare([['2025-01-01 00:00:00']],self.case([['2025-01-01']])))
    def test_normalization_uses_sufficient_precision(self):
        with decimal.localcontext() as ctx:
            ctx.prec=10
            value=decimal.Decimal('123456789012345678901234567890.123456')
            self.assertEqual(c.scalar(value),'123456789012345678901234567890.123456')

class OwnershipAndRemapping(unittest.TestCase):
    state={'schemas':{'core':'new_core','baseline':'new_base','semantic':'new_views','extra':'new_extra'}}
    def test_sql_literals_and_comments_are_not_rewritten(self):
        sql="SELECT 'bi_cases20k_20261012', x FROM `bi_cases20k_20261012`.orders -- bi_cases20k_20261012\n"
        result=c.remap(sql,self.state)
        self.assertIn("'bi_cases20k_20261012'",result);self.assertIn('`new_core`.orders',result);self.assertIn('-- bi_cases20k_20261012',result)
    def test_sql_quoted_escape(self):
        sql="SELECT 'quote\\\'bi_cases20k_20261012' FROM bi_cases20k_20261012.orders"
        result=c.remap(sql,self.state);self.assertTrue(result.endswith('FROM new_core.orders'))
    def test_recursive_model_ids(self):
        request={'database':2,'query':{'source-query':{'source-table':'card__41'},'filter':['=',['field','label'], 'card__41']}}
        rewritten=native.mb_remap(request,{41:123},999)
        self.assertEqual(rewritten['database'],999);self.assertEqual(rewritten['query']['source-query']['source-table'],'card__123')
        self.assertEqual(rewritten['query']['filter'][-1],'card__41');self.assertEqual(request['database'],2)
    def test_identifier_rejection(self):
        for value in ['name;DROP DATABASE prod','db.name','`existing`']:
            with self.assertRaises(ValueError):c.identifier(value)
    def test_declared_decimal_scale_not_unbounded_csv(self):
        rows=[(decimal.Decimal('0.334333333333333333333'),)]
        self.assertEqual(fixtures.stored_rows('rate DECIMAL(12,6)',rows),[(decimal.Decimal('0.334333'),)])
    def test_cleanup_refuses_unknown_ownership(self):
        class Cursor:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,*args):raise AssertionError('No DROP should occur')
        class Connection(Cursor):
            def cursor(self):return Cursor()
        with patch('common.connection',return_value=Connection()):
            with self.assertRaises(RuntimeError):fixtures.cleanup({'run_id':'abc','owned_schemas':['production']})

class Reporting(unittest.TestCase):
    def test_resource_rejection_requires_the_expected_quota(self):
        error=c.pymysql.OperationalError(1105,'allocation account capacity exceeded: used=132055040 requested=7454720 limit=134217728')
        self.assertTrue(spill_recovery.resource_rejection(error,'memory',134217728))
        self.assertFalse(spill_recovery.resource_rejection(error,'memory',536870912))
        self.assertFalse(spill_recovery.resource_rejection(RuntimeError('memory limit exceeded'),'memory',134217728))
        self.assertFalse(spill_recovery.resource_rejection(c.pymysql.OperationalError(1105,'memory limit exceeded'),'memory',134217728))
    def test_source_config_not_mutated_and_caps_are_frontend_only(self):
        text='[cn]\nport-base=18000\n[cn.frontend]\nprocessLimitationSpillSize=999\n[other]\nvalue=3\n'
        updated=spill_recovery.make_phase(text,128,1024)
        parsed=__import__('tomllib').loads(updated)
        self.assertEqual(parsed['cn']['frontend']['processLimitationSize'],128)
        self.assertEqual(parsed['cn']['frontend']['processLimitationSpillSize'],1024)
        self.assertEqual(parsed['other']['value'],3)
        self.assertIn('SpillSize=999',text)
    def test_strict_known_failure_is_red(self):
        self.assertEqual(run.outcome([{'status':'known_failure'}],'strict'),1)
    def test_observe_never_turns_failure_into_pass(self):
        with tempfile.TemporaryDirectory() as d:
            records=[{'id':'known','status':'known_failure'}]
            self.assertEqual(run.report(Path(d),records,{},'observe'),0)
            body=json.loads((Path(d)/'results.json').read_text());self.assertFalse(body['passed'])
            self.assertEqual(ET.parse(Path(d)/'junit.xml').getroot().get('skipped'),'1')
            self.assertEqual(body['cases'][0]['status'],'known_failure')
    def test_unknown_error_stays_red_in_observe(self):
        self.assertEqual(run.outcome([{'status':'error'}],'observe'),1)
        self.assertEqual(run.outcome([{'status':'mismatch'}],'observe'),1)
    def test_empty_coverage_fails(self):self.assertEqual(run.outcome([],'observe'),2)
    def test_missing_native_runtime_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            records=native.run('evidence',{},None,Path(d))
            self.assertEqual(records[0]['status'],'error');self.assertEqual(run.outcome(records,'observe'),1)
    def test_private_password_is_redacted(self):
        with patch.dict(os.environ,{'MO_PASSWORD':'private-test-password'}):
            self.assertNotIn('private-test-password',json.dumps(c.safe_error(RuntimeError('private-test-password failed'))))
    def test_graph_health_keeps_specific_verbose_error(self):
        class Response:
            ok=False;status_code=400
            text=json.dumps({'message':'Generic network error','details':{'verboseMessage':'invalid connection'}})
        api=native.HTTP({'url':'http://127.0.0.1:9999'})
        with patch.object(api.s,'request',return_value=Response()):
            with self.assertRaisesRegex(native.NativeError,'invalid connection'):api.get('/health')

if __name__=='__main__':unittest.main()
