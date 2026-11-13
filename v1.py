from contextlib import closing
"""Same-origin professional pilot. Legacy databases are never modified."""
import csv
import hashlib
import io
import math
import os
import secrets
import sqlite3
import time
from datetime import date
from pathlib import Path
import click
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
SCHEMA = '''
CREATE TABLE IF NOT EXISTS professionals(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES professionals(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS producers(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES professionals(id),name TEXT NOT NULL,region TEXT NOT NULL,phone TEXT NOT NULL,notes TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS producer_owner ON producers(owner_id);
CREATE TABLE IF NOT EXISTS harvests(id INTEGER PRIMARY KEY,producer_id INTEGER NOT NULL REFERENCES producers(id),observed_on TEXT NOT NULL,area_ha REAL NOT NULL,age_years REAL NOT NULL,harvest_kg REAL NOT NULL,price_fcfa_kg REAL NOT NULL,cost_fcfa REAL NOT NULL,agroforestry TEXT NOT NULL,disease TEXT NOT NULL,notes TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(producer_id,observed_on));
CREATE TABLE IF NOT EXISTS advice(id INTEGER PRIMARY KEY,producer_id INTEGER NOT NULL REFERENCES producers(id),content TEXT NOT NULL,author TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,started REAL NOT NULL);
'''

def create_app(config=None):
    app = Flask(__name__, static_folder='static')
    app.config.update(DATABASE=os.environ.get('MONCACAO_DATABASE', str(ROOT/'instance'/'v1.sqlite')), COOKIE_SECURE=os.environ.get('MONCACAO_HTTPS')=='1', MAX_CONTENT_LENGTH=32768)
    if config:
        app.config.update(config)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(app.config['DATABASE'])) as db, db:
        db.executescript(SCHEMA)

    def database():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close_database(exc):
        if 'db' in g:
            g.db.close()

    def error(message, status=400):
        return jsonify(error=message), status

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Un objet JSON est requis.')
        return data

    def text(data, key, maximum, required=True):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value.strip())>maximum or (required and not value.strip()):
            raise ValueError(f'Champ {key} invalide (maximum {maximum} caractères).')
        return value.strip()

    def number(data, key, low, high):
        value = data.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{key} doit être un nombre entre {low} et {high}.')
        return value

    @app.errorhandler(ValueError)
    def invalid(exc):
        return error(str(exc))

    @app.errorhandler(413)
    def too_large(exc):
        return error('Saisie trop volumineuse.',413)

    @app.before_request
    def protect():
        if not request.path.startswith('/api/'):
            return
        writing = request.method in ('POST','PUT','DELETE','PATCH')
        if writing and (request.headers.get('X-Requested-With')!='MonCacao' or request.headers.get('Sec-Fetch-Site')=='cross-site'):
            return error('Requête non autorisée.',403)
        if request.path=='/api/login':
            return
        token_hash = hashlib.sha256(request.cookies.get('mc_session','').encode()).hexdigest()
        row = database().execute('SELECT p.id,p.name,p.email,s.csrf,s.token_hash FROM sessions s JOIN professionals p ON p.id=s.user_id WHERE s.token_hash=? AND s.expires>?',(token_hash,time.time())).fetchone()
        if not row:
            return error('Connectez-vous pour continuer.',401)
        g.user = dict(row)
        if writing and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),row['csrf']):
            return error('Session expirée. Rechargez la page.',403)

    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin','X-Frame-Options':'DENY','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        return response

    @app.get('/')
    def index():
        return send_from_directory(ROOT/'templates','index.html')

    @app.get('/health')
    def health():
        database().execute('SELECT 1')
        return jsonify(status='ok',version='1.0')

    @app.post('/api/login')
    def login():
        data = body()
        email,password = text(data,'email',254).lower(),text(data,'password',256)
        db,now = database(),time.time()
        key = hashlib.sha256(email.encode()).hexdigest()
        with db:
            db.execute('DELETE FROM attempts WHERE started<?',(now-900,))
            db.execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now))
            count = db.execute('SELECT count FROM attempts WHERE key=?',(key,)).fetchone()[0]
        if count>10:
            return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
        user = db.execute('SELECT * FROM professionals WHERE email=?',(email,)).fetchone()
        if not user or not check_password_hash(user['password_hash'],password):
            return error('Email ou mot de passe incorrect.',401)
        raw,csrf = secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with db:
            db.execute('DELETE FROM attempts WHERE key=?',(key,))
            db.execute('DELETE FROM sessions WHERE expires<? OR token_hash=?',(now,hashlib.sha256(request.cookies.get('mc_session','').encode()).hexdigest()))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(raw.encode()).hexdigest(),user['id'],csrf,now+28800))
        response = jsonify(user={'name':user['name'],'email':user['email']},csrf=csrf)
        response.set_cookie('mc_session',raw,httponly=True,secure=app.config['COOKIE_SECURE'],samesite='Lax',max_age=28800)
        return response

    @app.get('/api/me')
    def me():
        return jsonify(user={'name':g.user['name'],'email':g.user['email']},csrf=g.user['csrf'])

    @app.post('/api/logout')
    def logout():
        with database() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?',(g.user['token_hash'],))
        response = jsonify(success=True)
        response.delete_cookie('mc_session')
        return response

    def owned(pid):
        return database().execute('SELECT * FROM producers WHERE id=? AND owner_id=?',(pid,g.user['id'])).fetchone()

    def producer_data(data):
        return (text(data,'name',120),text(data,'region',120),text(data,'phone',40,False),text(data,'notes',2000,False))

    @app.get('/api/producers')
    def producers():
        rows = database().execute('SELECT p.*,COUNT(h.id) harvest_count,MAX(h.observed_on) last_harvest FROM producers p LEFT JOIN harvests h ON h.producer_id=p.id WHERE p.owner_id=? GROUP BY p.id ORDER BY p.name',(g.user['id'],))
        return jsonify(producers=[dict(r) for r in rows])

    @app.post('/api/producers')
    def add_producer():
        values = producer_data(body())
        with database() as db:
            cursor = db.execute('INSERT INTO producers(owner_id,name,region,phone,notes) VALUES (?,?,?,?,?)',(g.user['id'],*values))
        return jsonify(id=cursor.lastrowid),201

    @app.put('/api/producers/<int:pid>')
    def edit_producer(pid):
        if not owned(pid):
            return error('Producteur introuvable.',404)
        values = producer_data(body())
        with database() as db:
            db.execute('UPDATE producers SET name=?,region=?,phone=?,notes=? WHERE id=? AND owner_id=?',(*values,pid,g.user['id']))
        return jsonify(success=True)

    @app.get('/api/producers/<int:pid>')
    def producer(pid):
        row = owned(pid)
        if not row:
            return error('Producteur introuvable.',404)
        harvests = database().execute('SELECT * FROM harvests WHERE producer_id=? ORDER BY observed_on DESC,id DESC',(pid,))
        advice = database().execute('SELECT * FROM advice WHERE producer_id=? ORDER BY id DESC',(pid,))
        return jsonify(producer=dict(row),harvests=[dict(h) for h in harvests],advice=[dict(a) for a in advice])

    def harvest_data(data):
        observed = date.fromisoformat(text(data,'observed_on',10))
        if observed>date.today() or observed.year<2000:
            raise ValueError('La date doit être comprise entre 2000 et aujourd’hui.')
        values = [number(data,k,lo,hi) for k,lo,hi in [('area_ha',0.01,100000),('age_years',0,150),('harvest_kg',0,1e8),('price_fcfa_kg',0,1e6),('cost_fcfa',0,1e11)]]
        agro,disease = text(data,'agroforestry',20),text(data,'disease',20)
        if agro not in ('Oui','Non','Non renseigné') or disease not in ('Oui','Non','Non renseigné'):
            raise ValueError('Choix agricole invalide.')
        return (observed.isoformat(),*values,agro,disease,text(data,'notes',2000,False))

    @app.post('/api/producers/<int:pid>/harvests')
    def add_harvest(pid):
        if not owned(pid):
            return error('Producteur introuvable.',404)
        values = harvest_data(body())
        try:
            with database() as db:
                db.execute('INSERT INTO harvests(producer_id,observed_on,area_ha,age_years,harvest_kg,price_fcfa_kg,cost_fcfa,agroforestry,disease,notes) VALUES (?,?,?,?,?,?,?,?,?,?)',(pid,*values))
        except sqlite3.IntegrityError:
            return error('Une récolte existe déjà à cette date pour ce producteur.',409)
        return jsonify(success=True),201

    @app.put('/api/producers/<int:pid>/harvests/<int:hid>')
    def edit_harvest(pid,hid):
        if not owned(pid) or not database().execute('SELECT id FROM harvests WHERE id=? AND producer_id=?',(hid,pid)).fetchone():
            return error('Récolte introuvable.',404)
        values = harvest_data(body())
        try:
            with database() as db:
                db.execute('UPDATE harvests SET observed_on=?,area_ha=?,age_years=?,harvest_kg=?,price_fcfa_kg=?,cost_fcfa=?,agroforestry=?,disease=?,notes=? WHERE id=? AND producer_id=?',(*values,hid,pid))
        except sqlite3.IntegrityError:
            return error('Une récolte existe déjà à cette date pour ce producteur.',409)
        return jsonify(success=True)

    @app.post('/api/producers/<int:pid>/advice')
    def add_advice(pid):
        if not owned(pid):
            return error('Producteur introuvable.',404)
        content = text(body(),'content',3000)
        with database() as db:
            db.execute('INSERT INTO advice(producer_id,content,author) VALUES (?,?,?)',(pid,content,g.user['name']))
        return jsonify(success=True),201

    @app.get('/api/dashboard')
    def dashboard():
        db = database()
        counts = db.execute('SELECT COUNT(*) total,SUM(CASE WHEN NOT EXISTS(SELECT 1 FROM harvests h WHERE h.producer_id=p.id) THEN 1 ELSE 0 END) pending FROM producers p WHERE owner_id=?',(g.user['id'],)).fetchone()
        totals = db.execute('SELECT COUNT(*) harvests,COALESCE(SUM(h.harvest_kg),0) kg,COALESCE(SUM(h.harvest_kg*h.price_fcfa_kg),0) revenue FROM harvests h JOIN producers p ON p.id=h.producer_id WHERE p.owner_id=?',(g.user['id'],)).fetchone()
        return jsonify(producers=counts['total'],pending=counts['pending'] or 0,**dict(totals))

    @app.get('/api/export/<kind>')
    def export(kind):
        queries = {
            'producers': ('SELECT name,region,phone,notes,created_at FROM producers WHERE owner_id=? ORDER BY name',['Nom','Région','Téléphone','Notes','Création']),
            'harvests': ('SELECT p.name,h.observed_on,h.area_ha,h.age_years,h.harvest_kg,h.price_fcfa_kg,h.cost_fcfa,h.harvest_kg*h.price_fcfa_kg,h.agroforestry,h.disease,h.notes FROM harvests h JOIN producers p ON p.id=h.producer_id WHERE p.owner_id=? ORDER BY h.observed_on DESC',['Producteur','Date récolte','Surface ha','Âge ans','Récolte kg','Prix FCFA/kg','Coûts récolte FCFA','Revenu calculé FCFA','Agroforesterie','Maladie','Notes']),
            'advice': ('SELECT p.name,a.content,a.author,a.created_at FROM advice a JOIN producers p ON p.id=a.producer_id WHERE p.owner_id=? ORDER BY a.id DESC',['Producteur','Conseil','Auteur','Date'])}
        if kind not in queries:
            return error('Export introuvable.',404)
        query,titles = queries[kind]
        output = io.StringIO(newline='')
        writer = csv.writer(output,delimiter=';')
        writer.writerow(titles)
        for row in database().execute(query,(g.user['id'],)):
            writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
        return app.response_class('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="moncacao-{kind}.csv"'})

    @app.cli.command('create-professional')
    @click.option('--name',prompt='Nom complet')
    @click.option('--email',prompt='Email')
    @click.password_option(confirmation_prompt=True)
    def create_professional(name,email,password):
        if not name.strip() or len(name)>120 or '@' not in email or len(email)>254 or not 12<=len(password)<=256 or password!=password.strip():
            raise click.ClickException('Nom/email valides et mot de passe de 12 à 256 caractères requis, sans espaces aux extrémités.')
        try:
            with database() as db:
                db.execute('INSERT INTO professionals(name,email,password_hash) VALUES (?,?,?)',(name.strip(),email.strip().lower(),generate_password_hash(password)))
        except sqlite3.IntegrityError:
            raise click.ClickException('Cet email possède déjà un compte.')
        click.echo('Compte professionnel créé.')

    @app.cli.command('reset-password')
    @click.option('--email',prompt='Email du compte')
    @click.password_option(confirmation_prompt=True)
    def reset_password(email,password):
        if not 12<=len(password)<=256 or password!=password.strip():
            raise click.ClickException('Mot de passe de 12 à 256 caractères requis, sans espaces aux extrémités.')
        db=database()
        user=db.execute('SELECT id FROM professionals WHERE email=?',(email.strip().lower(),)).fetchone()
        if not user:
            raise click.ClickException('Compte introuvable.')
        with db:
            db.execute('UPDATE professionals SET password_hash=? WHERE id=?',(generate_password_hash(password),user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
        click.echo('Mot de passe modifié et sessions révoquées.')

    @app.cli.command('backup')
    @click.argument('destination',type=click.Path())
    def backup(destination):
        target = Path(destination).resolve()
        if target.exists():
            raise click.ClickException('Le fichier de destination existe déjà.')
        target.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(target)) as dest:
            database().backup(dest)
        click.echo('Sauvegarde créée. Conservez-la dans un emplacement protégé.')
    return app
