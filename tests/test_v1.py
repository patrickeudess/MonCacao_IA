from contextlib import closing
import csv
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash
from v1 import create_app


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'Test-password-12345'
        cls.hashed = generate_password_hash(cls.password)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name)/'test.sqlite')
        self.app = create_app({'TESTING':True,'DATABASE':self.path})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO professionals(name,email,password_hash) VALUES (?,?,?)',
                           [('Alice','alice@example.test',self.hashed),('Bob','bob@example.test',self.hashed)])
        self.client = self.app.test_client()
        self.login()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, email='alice@example.test', client=None):
        client = client or self.client
        result = client.post('/api/login',json={'email':email,'password':self.password},headers={'X-Requested-With':'MonCacao'})
        self.assertEqual(result.status_code,200)
        self.headers={'X-Requested-With':'MonCacao','X-CSRF-Token':result.json['csrf']}
        return result

    def producer(self,name='Awa'):
        result=self.client.post('/api/producers',json={'name':name,'region':'San Pedro','phone':'+2250102030405','notes':'Visite terrain'},headers=self.headers)
        self.assertEqual(result.status_code,201)
        return result.json['id']

    def harvest(self, **changes):
        return dict(observed_on='2026-01-15',area_ha=2,age_years=10,harvest_kg=500,price_fcfa_kg=1800,cost_fcfa=100000,agroforestry='Oui',disease='Non',notes='Récolte distincte',**changes)

    def test_producer_self_registration_and_private_workflow(self):
        other_pid=self.producer()
        guest=self.app.test_client()
        payload=dict(name='Kouassi',region='San-Pedro',email='kouassi@example.test',password=self.password,password_confirm=self.password,role='professional')
        basic={'X-Requested-With':'MonCacao'}
        self.assertEqual(guest.post('/api/register',json=payload).status_code,403)
        self.assertEqual(guest.post('/api/register',json=payload,headers={**basic,'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(guest.post('/api/register',json={**payload,'password_confirm':'different'},headers=basic).status_code,400)
        self.assertEqual(guest.post('/api/register',json=payload,headers=basic).status_code,201)
        self.assertEqual(guest.post('/api/register',json=payload,headers=basic).status_code,409)
        login=guest.post('/api/login',json={'email':payload['email'],'password':self.password},headers=basic)
        self.assertEqual(login.json['user']['role'],'producer')
        self.assertEqual(guest.get('/api/me').json['user']['role'],'producer')
        headers={**basic,'X-CSRF-Token':login.json['csrf']}
        profiles=guest.get('/api/producers').json['producers']
        self.assertEqual(len(profiles),1)
        pid=profiles[0]['id']
        self.assertEqual(profiles[0]['name'],'Kouassi')
        self.assertEqual(guest.post('/api/producers',json={'name':'Other','region':'X'},headers=headers).status_code,403)
        self.assertEqual(guest.get(f'/api/producers/{other_pid}').status_code,404)
        self.assertEqual(guest.post(f'/api/producers/{other_pid}/harvests',json=self.harvest(),headers=headers).status_code,404)
        self.assertEqual(guest.post(f'/api/producers/{pid}/harvests',json=self.harvest(),headers=headers).status_code,201)
        prediction=self.prediction_payload()
        self.assertEqual(guest.post(f'/api/producers/{pid}/predictions',json=prediction,headers=headers).status_code,201)
        self.assertEqual(guest.get('/api/dashboard').json['kg'],500)
        self.assertNotIn('Awa',guest.get('/api/export/harvests').text)
        self.assertEqual(self.client.get(f'/api/producers/{pid}').status_code,404)
        restarted=create_app({'TESTING':True,'DATABASE':self.path}).test_client()
        again=restarted.post('/api/login',json={'email':payload['email'],'password':self.password},headers=basic)
        self.assertEqual(again.json['user']['role'],'producer')
        self.assertEqual(len(restarted.get(f'/api/producers/{pid}').json['predictions']),1)

    def test_registration_rate_limit_and_migration(self):
        guest=self.app.test_client()
        for i in range(5):
            self.assertEqual(guest.post('/api/register',json={},headers={'X-Requested-With':'MonCacao'}).status_code,400)
        self.assertEqual(guest.post('/api/register',json={},headers={'X-Requested-With':'MonCacao'}).status_code,429)
        self.assertEqual(self.client.get('/api/me').json['user']['role'],'professional')
        legacy=str(Path(self.tmp.name)/'legacy.sqlite')
        with closing(sqlite3.connect(legacy)) as db,db:
            db.execute('CREATE TABLE professionals(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL)')
            db.execute('INSERT INTO professionals VALUES (1,?,?,?)',('Alice','alice@example.test',self.hashed))
        migrated=create_app({'TESTING':True,'DATABASE':legacy}).test_client()
        self.assertEqual(self.login(client=migrated).json['user']['role'],'professional')

    def test_complete_workflow_and_persistence(self):
        pid=self.producer()
        r=self.client.post(f'/api/producers/{pid}/harvests',json=self.harvest(),headers=self.headers)
        self.assertEqual(r.status_code,201)
        self.assertEqual(self.client.post(f'/api/producers/{pid}/advice',json={'content':'Observation à revoir avec le conseiller.'},headers=self.headers).status_code,201)
        detail=self.client.get(f'/api/producers/{pid}').json
        self.assertEqual(detail['advice'][0]['author'],'Alice')
        hid=detail['harvests'][0]['id']
        h=self.harvest();h['harvest_kg']=600
        self.assertEqual(self.client.put(f'/api/producers/{pid}/harvests/{hid}',json=h,headers=self.headers).status_code,200)
        self.assertEqual(self.client.put(f'/api/producers/{pid}',json={'name':'Awa modifié','region':'Daloa'},headers=self.headers).status_code,200)
        result=self.client.get('/api/dashboard').json
        self.assertEqual(result,{'producers':1,'pending':0,'harvests':1,'kg':600,'revenue':1080000})
        restarted=create_app({'TESTING':True,'DATABASE':self.path}).test_client()
        self.login(client=restarted)
        self.assertEqual(restarted.get(f'/api/producers/{pid}').json['producer']['name'],'Awa modifié')

    def test_other_account_cannot_access_or_modify_data(self):
        pid=self.producer()
        self.client.post(f'/api/producers/{pid}/harvests',json=self.harvest(),headers=self.headers)
        hid=self.client.get(f'/api/producers/{pid}').json['harvests'][0]['id']
        self.login('bob@example.test')
        self.assertEqual(self.client.get('/api/producers').json['producers'],[])
        for method,path,data in [('GET',f'/api/producers/{pid}',None),('PUT',f'/api/producers/{pid}',{'name':'X','region':'Y'}),('POST',f'/api/producers/{pid}/harvests',self.harvest()),('PUT',f'/api/producers/{pid}/harvests/{hid}',self.harvest()),('POST',f'/api/producers/{pid}/advice',{'content':'X'})]:
            self.assertEqual(self.client.open(path,method=method,json=data,headers=self.headers).status_code,404)
        self.assertEqual(self.client.get('/api/dashboard').json['kg'],0)
        self.assertNotIn('Awa',self.client.get('/api/export/harvests').text)

    def test_session_csrf_cookie_logout(self):
        guest=self.app.test_client()
        for path in ['/api/producers','/api/dashboard','/api/export/producers']:
            self.assertEqual(guest.get(path).status_code,401)
        self.assertEqual(self.client.post('/api/producers',json={'name':'X','region':'Y'}).status_code,403)
        self.assertEqual(self.client.post('/api/producers',json={'name':'X','region':'Y'},headers={'X-Requested-With':'MonCacao'}).status_code,403)
        response=self.login()
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        self.assertIn('SameSite=Lax',response.headers['Set-Cookie'])
        self.assertEqual(self.client.post('/api/logout',json={},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/me').status_code,401)

    def test_invalid_and_duplicate_harvest(self):
        pid=self.producer()
        for key,value in [('area_ha',0),('harvest_kg',-1),('harvest_kg',True),('price_fcfa_kg','1800'),('disease','invalid'),('observed_on','2099-01-01'),('area_ha',float('nan'))]:
            h=self.harvest();h[key]=value
            self.assertEqual(self.client.post(f'/api/producers/{pid}/harvests',json=h,headers=self.headers).status_code,400)
        self.client.post(f'/api/producers/{pid}/harvests',json=self.harvest(),headers=self.headers)
        self.assertEqual(self.client.post(f'/api/producers/{pid}/harvests',json=self.harvest(),headers=self.headers).status_code,409)
        self.assertEqual(self.client.get('/api/dashboard').json['harvests'],1)

    def test_csv_and_formula_protection(self):
        self.producer('=HYPERLINK("bad")')
        r=self.client.get('/api/export/producers')
        rows=list(csv.reader(io.StringIO(r.text.lstrip('\ufeff')),delimiter=';'))
        self.assertEqual(len(rows),2)
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertTrue(rows[1][2].startswith("'+225"))
        self.assertIn('attachment',r.headers['Content-Disposition'])

    def test_throttle_expiry_and_removed_routes(self):
        client=self.app.test_client()
        for _ in range(10):
            self.assertEqual(client.post('/api/login',json={'email':'unknown@example.test','password':'bad'},headers={'X-Requested-With':'MonCacao'}).status_code,401)
        self.assertEqual(client.post('/api/login',json={'email':'unknown@example.test','password':'bad'},headers={'X-Requested-With':'MonCacao'}).status_code,429)
        for path in ['/api/messages/1','/api/auth/forgot-password','/predict','/prediction.html','/data.sqlite']:
            self.assertEqual(self.client.get(path).status_code,404)
        with closing(sqlite3.connect(self.path)) as db, db:db.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.client.get('/api/me').status_code,401)

    def test_account_provisioning_and_reset_revokes_session(self):
        runner=self.app.test_cli_runner()
        result=runner.invoke(args=['create-professional','--name','Claire','--email','claire@example.test','--password',self.password])
        self.assertEqual(result.exit_code,0,result.output)
        result=runner.invoke(args=['reset-password','--email','alice@example.test','--password','Replacement-password-123'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertEqual(self.client.get('/api/me').status_code,401)
        response=self.client.post('/api/login',json={'email':'alice@example.test','password':self.password},headers={'X-Requested-With':'MonCacao'})
        self.assertEqual(response.status_code,401)

    def test_assets_and_backup(self):
        for path in ['/','/static/app.js','/static/app.css','/health']:
            r=self.client.get(path)
            self.assertEqual(r.status_code,200)
            self.assertIn("default-src 'self'",r.headers['Content-Security-Policy'])
            r.close()
        pid=self.producer()
        target=str(Path(self.tmp.name)/'backup.sqlite')
        result=self.app.test_cli_runner().invoke(args=['backup',target])
        self.assertEqual(result.exit_code,0,result.output)
        with closing(sqlite3.connect(target)) as db:self.assertEqual(db.execute('SELECT name FROM producers WHERE id=?',(pid,)).fetchone()[0],'Awa')

    def prediction_payload(self):
        schema=self.client.get('/api/prediction-schema')
        self.assertEqual(schema.status_code,200,schema.json)
        inputs={f['name']: (10 if f['name']=='Age_verger' else 400000) if f['type']=='number' else f['options'][0] for f in schema.json['fields']}
        return {'inputs':inputs,'area_ha':2}

    def test_real_model_prediction_saved_and_isolated_from_harvests(self):
        import joblib
        import pandas as pd
        from v1 import ROOT
        pid=self.producer()
        data=self.prediction_payload()
        original=joblib.load(ROOT/'model_productivite_xgb.pkl')
        expected=float(original.predict(pd.DataFrame([data['inputs']]))[0])
        result=self.client.post(f'/api/producers/{pid}/predictions',json=data,headers=self.headers)
        self.assertEqual(result.status_code,201,result.json)
        self.assertAlmostEqual(result.json['productivity_t_ha'],expected,places=6)
        self.assertAlmostEqual(result.json['estimated_total_kg'],expected*2000,places=6)
        self.assertNotIn('confidence',result.json)
        detail=self.client.get(f'/api/producers/{pid}').json
        self.assertEqual(detail['predictions'][0]['inputs'],data['inputs'])
        self.assertEqual(detail['predictions'][0]['author'],'Alice')
        self.assertEqual(detail['harvests'],[])
        self.assertEqual(self.client.get('/api/dashboard').json['kg'],0)
        self.login('bob@example.test')
        self.assertEqual(self.client.post(f'/api/producers/{pid}/predictions',json=data,headers=self.headers).status_code,404)
        self.assertEqual(self.client.get(f'/api/producers/{pid}').status_code,404)

    def test_prediction_validation_and_unavailable_model(self):
        from prediction_service import Predictor
        pid=self.producer()
        data=self.prediction_payload()
        for area in [0,-1,True,'2',float('nan')]:
            bad={'inputs':data['inputs'],'area_ha':area}
            self.assertEqual(self.client.post(f'/api/producers/{pid}/predictions',json=bad,headers=self.headers).status_code,400)
        for key,value in [('Age_verger',-1),('Coût_production/ha','400000'),('Région','Unknown')]:
            bad={'inputs':{**data['inputs'],key:value},'area_ha':2}
            self.assertEqual(self.client.post(f'/api/producers/{pid}/predictions',json=bad,headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(f'/api/producers/{pid}/predictions',json=data,headers={'X-Requested-With':'MonCacao'}).status_code,403)
        self.app.extensions['predictor']=Predictor(Path(self.tmp.name)/'missing.pkl')
        with self.assertLogs(self.app.logger,level='ERROR'):
            self.assertEqual(self.client.post(f'/api/producers/{pid}/predictions',json=data,headers=self.headers).status_code,503)
        self.assertEqual(self.client.get(f'/api/producers/{pid}').json['predictions'],[])

if __name__=='__main__':unittest.main()
