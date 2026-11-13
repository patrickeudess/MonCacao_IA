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

if __name__=='__main__':unittest.main()
