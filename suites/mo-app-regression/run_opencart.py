"""Pinned OpenCart native installer, date-aware prices/cart, auth and restart."""
import argparse
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from native_common import Processes, connection_config, digest, finish, port, private_file, runtime_root
from run_baikal import Session

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'fixtures/opencart'
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'


def release(provided, private):
    identity = json.loads((FIXTURE / 'release.json').read_text())
    archive = provided
    if not archive:
        archive = private / 'official.zip'
        with urllib.request.urlopen(identity['archive_url'], timeout=90) as response:
            private_file(archive, response.read(40 * 1024**2 + 1))
    if digest(archive) != identity['archive_sha256']:
        raise RuntimeError('Pinned official OpenCart archive mismatch')
    app = private / 'app'; app.mkdir(mode=0o700); count = 0; expanded = 0
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if member.is_dir() or not member.filename.startswith('upload/'):
                continue
            relative = Path(member.filename[7:])
            if relative.is_absolute() or '..' in relative.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError('Unsafe OpenCart release entry')
            expanded += member.file_size
            if expanded > 150 * 1024**2:
                raise RuntimeError('Expanded OpenCart release exceeds bound')
            target = app / relative; target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            count += 1
    if count != identity['release_selected_file_count']:
        raise RuntimeError('Pinned release file count mismatch')
    for entry in json.loads((FIXTURE / 'adaptation-manifest.json').read_text())['files']:
        target = app / entry['path']; adapted = FIXTURE / 'adapted' / entry['path']
        if digest(target) != entry['original_sha256'] or digest(adapted) != entry['adapted_sha256']:
            raise RuntimeError('Pinned original/adapter mismatch')
        target.write_bytes(adapted.read_bytes())
    return app, count


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-archive', type=Path, default=os.getenv('MO_OPENCART_RELEASE_ARCHIVE') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts'/('opencart-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128: parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_opencart_'+uuid.uuid4().hex[:16]
    private = runtime_root()/schema; private.mkdir(mode=0o700)
    report = {'app':'opencart/opencart','version':'4.1.0.4','schema':schema,'passed':False,'checks':[],
              'native_runtime_attempted':False,'existing_databases_modified':False,
              'official_archive_sha256':json.loads((FIXTURE/'release.json').read_text())['archive_sha256'],
              'adaptation_manifest_sha256':digest(FIXTURE/'adaptation-manifest.json'),
              'manual_users_or_migration_stamps':False,'min_free_mib':args.min_free_mib,
              'source_edits':['date-filtered derived price joins','PHP boolean SQL literals as integers','skip only OPTIMIZE, keep expired-session DELETE','PHP8.5 PDO constant compatibility'],
              'limitations':['fresh schema initializer; populated upgrades/payment/shipping/checkout/orders/extensions/load unverified',
                             'original file sessions/cache retained; SQL business data uses MatrixOne',
                             'upstream fresh installer leaves foreign keys commented out; no additional constraints removed']}
    owned = Processes(private, report); stage = 'admission'
    def check(name, value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value: raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2+190*1024**2:
            raise RuntimeError('Pinned PHP SDK and release expansion headroom required')
        php = args.binary.resolve(); check('pinned_FrankenPHP', digest(php)==PHP_SHA)
        app, count = release(args.release_archive, private); report['verified_release_files'] = count
        check('fresh_official_release_without_old_config', not(app/'config.php').exists() and not(app/'admin/config.php').exists())
        for target in [app/'config.php',app/'admin/config.php']:
            target.write_bytes(target.with_name('config-dist.php').read_bytes()); target.chmod(0o600)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()'); report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q: q.execute(query,params); return q.fetchall()
        credentials={'admin_password':'Mo1-'+secrets.token_hex(12)}
        private_file(private/'credentials.json',json.dumps(credentials))
        base='http://127.0.0.1:'+str(port()); admin=Session(base); customer=Session(base); anonymous=Session(base)
        ini=private/'php-ini'; ini.mkdir(mode=0o700)
        private_file(ini/'local.ini','date.timezone=UTC\ndisplay_errors=Off\nlog_errors=On\n')
        # Follow the upstream supported deployment setting; preserve private error logging.
        settings=app/'system/config/default.php'; text=settings.read_text()
        if text.count("$_['error_display']        = true;")!=1: raise RuntimeError('Supported deployment setting changed')
        settings.write_text(text.replace("$_['error_display']        = true;","$_['error_display']        = false;"))
        caddy=private/'Caddyfile'
        private_file(caddy,'{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n'+base+' {\n root * '+str(app)+'\n @blocked path /config.php /admin/config.php /system/*\n respond @blocked 403\n php_server\n}\n')
        env={**os.environ,'MATRIXONE_ADAPTER':'1','PHP_INI_SCAN_DIR':str(ini),'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB',
             'XDG_CONFIG_HOME':str(private/'config'),'XDG_DATA_HOME':str(private/'data')}
        def route(prefix, name, **params): return prefix+'index.php?'+urllib.parse.urlencode({'route':name,'language':'en-gb',**params})
        def start():
            proc=owned.start([str(php),'run','--config',str(caddy)],app,env,'opencart'); report['native_runtime_attempted']=True
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if proc.poll() is not None: raise RuntimeError('Native OpenCart startup failed; private log retained')
                try:
                    if anonymous.request('GET','/',timeout=5).status_code==200: return proc
                except(OSError,urllib.error.URLError): pass
                time.sleep(.2)
            raise TimeoutError('Native OpenCart readiness')
        def native_json(response, label):
            if response.status_code!=200: raise AssertionError(label+'_HTTP')
            try: return response.json()
            except ValueError:
                private_file(private/(label+'-response.private'),response.content)
                raise RuntimeError('Native JSON response invalid; private evidence retained')
        stage='native_installer'; proc=start()
        response=admin.request('GET',route('/install/','install/step_3'))
        check('native_database_and_admin_install_form',response.status_code==200 and 'name="db_hostname"' in response.text)
        form={'db_driver':'pdo','db_hostname':cfg['host'],'db_port':cfg['port'],'db_username':cfg['user'],
              'db_password':cfg['password'],'db_database':schema,'db_prefix':'oc_',
              'db_ssl_key':'','db_ssl_cert':'','db_ssl_ca':'','username':'mo-admin',
              'password':credentials['admin_password'],'email':'admin@example.test'}
        result=native_json(admin.request('POST',route('/install/','install/step_3.save'),data=form,timeout=180),'install')
        check('native_schema_data_and_admin_installer',not result.get('error') and 'install/step_4' in result.get('redirect',''))
        report['native_table_count']=len(sql('SHOW TABLES'))
        check('native_core_tables',all(sql("SHOW TABLES LIKE %s",('oc_'+n,)) for n in ['user','product','product_description','product_discount','cart','setting']))
        check('native_admin_password_hash',sql('SELECT username,LENGTH(password),user_group_id,status FROM oc_user')==(('mo-admin',60,1,1),))
        check('native_install_config_written',all('DB_DATABASE' in p.read_text() and schema in p.read_text() for p in [app/'config.php',app/'admin/config.php']))
        (app/'install').rename(private/'install-disabled')
        for p in [app/'config.php',app/'admin/config.php']:p.chmod(0o600)
        stage='native_authentication'
        def login(client, password):
            response=client.request('GET',route('/admin/','common/login'))
            form=BeautifulSoup(response.text,'html.parser').select_one('#form-login')
            if form is None: raise AssertionError('native_login_form')
            action=urllib.parse.urlsplit(form['action']); query=urllib.parse.parse_qs(action.query)
            check('native_login_token_'+str(len(report['checks'])),bool(query.get('login_token')))
            result=native_json(client.request('POST',action.path+'?'+action.query,data={'username':'mo-admin','password':password},headers={'User-Agent':'MO native regression'}),'login')
            return result
        bad=login(Session(base),'incorrect-'+uuid.uuid4().hex)
        check('wrong_password_native_rejection',bool(bad.get('error')) and not bad.get('redirect'))
        result=login(admin,credentials['admin_password']); token=urllib.parse.parse_qs(urllib.parse.urlsplit(result.get('redirect','')).query).get('user_token',[''])[0]
        check('native_password_cookie_login',bool(token))
        credentials['user_token']=token; (private/'credentials.json').write_text(json.dumps(credentials))
        def management(name, **params): return route('/admin/',name,user_token=token,**params)
        stage='native_product'
        name='原生商店商品 中文 😀𠮷'; description='商品描述 中文 😀𠮷'; model='mo-'+uuid.uuid4().hex[:12]
        today=date.today(); old=(today-timedelta(days=30)).isoformat(); active=(today+timedelta(days=30)).isoformat(); future=(today+timedelta(days=60)).isoformat()
        body={'model':model,'price':'25.00','quantity':'100','minimum':'1','subtract':'1','shipping':'1','stock_status_id':'7',
              'date_available':old,'status':'1','tax_class_id':'0','weight_class_id':'1','length_class_id':'1','width':'0','height':'0',
              'length':'0','image':'','product_store[0]':'0','product_seo_url[0][1]':model}
        for field,value in {'name':name,'description':description,'meta_title':name,'meta_description':'','meta_keyword':'','tag':''}.items():body['product_description[1]['+field+']']=value
        discounts=[('P','10','0','1',old,active),('S','5','1','1',old,active),('S','24','1','0',future,future),('S','23','1','0',old,old)]
        for i,(kind,price,special,priority,start_date,end_date) in enumerate(discounts):
            for field,value in {'customer_group_id':'1','quantity':'1','priority':priority,'type':kind,'price':price,'special':special,'date_start':start_date,'date_end':end_date}.items():body[f'product_discount[{i}][{field}]']=value
        result=native_json(admin.request('POST',management('catalog/product.save'),data=body,timeout=120),'product-create')
        check('native_admin_product_create',bool(result.get('success')) and not result.get('error'))
        rows=sql('SELECT product_id FROM oc_product WHERE model=%s',(model,)); check('native_product_single_ID',len(rows)==1); identity=rows[0][0]
        report['native_product_id']=identity; body['product_id']=identity
        def audit():
            check('SQL_product_description_store_relationships',sql('SELECT d.name,d.description,p.model,p.price,p.quantity,s.store_id FROM oc_product p JOIN oc_product_description d ON d.product_id=p.product_id JOIN oc_product_to_store s ON s.product_id=p.product_id WHERE p.product_id=%s',(identity,))==((name,description,model,Decimal('25.0000'),100,0),))
            rows=sql('SELECT type,price,special,priority,date_start,date_end FROM oc_product_discount WHERE product_id=%s ORDER BY product_discount_id',(identity,))
            check('SQL_all_four_price_rules_exact',len(rows)==4 and [(r[0],format(r[1], 'f').rstrip('0').rstrip('.'),str(r[2]),str(r[3]),str(r[4]),str(r[5])) for r in rows]==discounts)
        audit()
        def readback(label):
            response=admin.request('GET',management('catalog/product.form',product_id=identity)); field=BeautifulSoup(response.text,'html.parser').find('input',attrs={'name':'product_description[1][name]'})
            check(label+'_native_admin_unicode_readback',response.status_code==200 and field is not None and field.get('value')==name)
            response=customer.request('GET',route('/','product/product',product_id=identity)); soup=BeautifulSoup(response.text,'html.parser')
            prices=[n.get_text(' ',strip=True) for n in soup.select('.price-old,.price-new')]; report['native_display_prices']=prices
            check(label+'_date_filtered_discount_special',response.status_code==200 and name in soup.get_text() and prices==['$22.50','$20.00'])
        readback('before_restart')
        stage='native_cart'
        result=native_json(customer.request('POST',route('/','checkout/cart.add'),data={'product_id':identity,'quantity':'2'}),'cart-add')
        check('native_cart_add',bool(result.get('success')) and not result.get('error'))
        check('SQL_cart_product_quantity_relation',sql('SELECT product_id,quantity FROM oc_cart WHERE product_id=%s',(identity,))==((identity,2),))
        def cart(label):
            response=customer.request('GET',route('/','checkout/cart')); soup=BeautifulSoup(response.text,'html.parser')
            matches=[n.get_text(' ',strip=True) for n in soup.select('table tbody tr') if name in n.get_text()]
            check(label+'_native_cart_unit20_line40',response.status_code==200 and len(matches)==1 and '$20.00 $40.00' in matches[0])
        cart('before_restart')
        def denied(response):
            if response.status_code in {401,403}: return True
            if response.status_code!=200: return False
            if response.headers.get('Content-Type','').startswith('application/json'):
                return 'common/login' in response.json().get('redirect','')
            return BeautifulSoup(response.text,'html.parser').select_one('#form-login') is not None
        rejected={**body,'product_description[1][name]':'invalid cross-session write'}
        response=anonymous.request('POST',route('/admin/','catalog/product.save'),data=rejected)
        check('anonymous_management_denied_zero_write',denied(response) and sql('SELECT name FROM oc_product_description WHERE product_id=%s',(identity,))==((name,),))
        response=admin.request('POST',route('/admin/','catalog/product.save',user_token='deliberately-invalid-token'),data=rejected)
        check('invalid_native_user_token_denied_zero_write',denied(response) and sql('SELECT name FROM oc_product_description WHERE product_id=%s',(identity,))==((name,),))
        stage='native_restart'; previous=proc.pid; owned.stop(proc); proc=start()
        check('real_PHP_process_restart',proc.pid!=previous); readback('after_restart'); cart('after_restart'); audit()
        stage='native_update'; name='更新商店商品 中文 😀𠮷'; body['product_description[1][name]']=name; body['product_description[1][meta_title]']=name
        result=native_json(admin.request('POST',management('catalog/product.save'),data=body),'product-update')
        check('native_admin_product_update',bool(result.get('success')) and not result.get('error')); readback('after_update'); audit()
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),)); report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError): report['failed_check']=str(exc)
    finally: owned.close()
    finish(out,report,'opencart-native'); return 0 if report['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
