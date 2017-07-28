#!flask/bin/python
from flask import Flask, jsonify, abort, request, make_response, render_template, g, send_from_directory
from flask_security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required, current_user
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import scoped_session, create_session
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from scpy import Sia
import threading
import secrets
import json
import os

app = Flask(__name__, static_url_path='')
sc = Sia()
app.config.from_pyfile('config.py')
db = SQLAlchemy(app)

db_session = scoped_session(lambda: create_session(bind=db.get_engine()))

app.config['DEBUG'] = True
app.config['SECRET_KEY'] = 'super-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

# Create database connection object
db = SQLAlchemy(app)

# Define models
roles_users = db.Table('roles_users',
        db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
        db.Column('role_id', db.Integer(), db.ForeignKey('role.id')))

class Role(db.Model, RoleMixin):
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    active = db.Column(db.Boolean())
    roles = db.relationship('Role', secondary=roles_users,
                            backref=db.backref('users', lazy='dynamic'))

# Setup Flask-Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)


class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.String(128), unique=True)
    name = db.Column(db.String(256))
    size = db.Column(db.Integer)
    user = db.Column(db.String(256))
    last_modified = db.Column(db.DateTime)
    status = db.Column(db.String(64))

    def __init__(self, name, size, user):
        self.file_id = secrets.token_hex(64)
        self.name = name
        self.size = size
        self.user = user
        self.last_modified = datetime.utcnow()
        self.status = "not available"

    def serialize(self):
        return {
            'file_id': self.file_id,
            'name'   : self.name,
            'size'   : self.size,
            'user'   : self.user,
            'last_modified' : self.last_modified,
            'status' : self.status,
            'available': get_available(self.file_id),
            'uploadprogress': get_uploadprogress(self.file_id),
    }

def get_available(file_id):
    for f in sc.renter.files:
        if f ['siapath'] == file_id:
            return f['available']
    return False

def get_uploadprogress(file_id):
    for f in sc.renter.files:
        if f ['siapath'] == file_id:
            return f['uploadprogress']
    return 0

def get_downloadprogress(file_id):
    for f in sc.renter.downloads:
        if f ['siapath'] == file_id:
            return f['received'] / f['filesize'] * 100
    return 0

class CachedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cached_file_id = db.Column(db.String(128), unique=True)
    file_id = db.Column(db.String(128))
    user = db.Column(db.String(256))
    download_code = db.Column(db.String(128))
    created = db.Column(db.DateTime)
    lifetime = db.Column(db.Integer())

    def __init__(self, file_id, user, lifetime):
        self.cached_file_id = secrets.token_hex(64)
        self.file_id = file_id
        self.user = user
        self.download_code = ""
        self.created = datetime.utcnow()
        self.lifetime = lifetime

    def serialize(self):
        return {
            'file'    : File.query.filter_by(file_id=self.file_id).first().serialize(),
            'id'      : self.cached_file_id,
            'user' : self.user,
            'download_code': self.download_code,
            'created' : self.created,
            'lifetime': self.lifetime,
    }


@app.route('/files', methods=['GET'])
@login_required
def list_files():
    return jsonify({'files': [f.serialize() for f in File.query.filter_by(user=current_user.id)]})

@app.route('/purge_cache', methods=['GET'])
@login_required
def purge_cache():
    for f in CachedFile.query.all():
        if f.created + datetime.timedelta(seconds=f.lifetime) < datetime.utcnow():
            os.remove(os.path.join(app.config['FINAL_CACHE_FOLDER'], f.download_code))
            db.session.delete(f)
            db.session.commit()
            


@app.route('/file/<string:file_id>', methods=['GET'])
@login_required
def get_file_detail(file_id):
    res = File.query.filter_by(file_id=file_id).filter_by(user=current_user.id).first()
    if res:
        return jsonify(res.serialize())
    else:
        abort(404)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    file = request.files['file']
    if file:
        filename = secure_filename(file.filename)
        new_file = File(filename, 1024, current_user.id)
        file_save_dir = os.path.join(app.config['UPLOAD_FOLDER'], new_file.file_id)
        file.save(file_save_dir)
        new_file.size = os.path.getsize(file_save_dir)
        new_file.status = "uploading"
        try:
            upload_to_sia(new_file, file_save_dir)
        except:
            abort(500)
        db.session.add(new_file)
        db.session.commit()
        return get_file_detail(new_file.file_id)
    else:
        abort(400)

def upload_to_sia(new_file, file_save_dir):
    sc.renter.upload(new_file.file_id, file_save_dir, 1, 1)
    t = threading.Thread(target=change_status_when_done, args=(new_file.file_id, file_save_dir))
    t.start()

def change_status_when_done(file_id, file_save_dir):
    session = db_session()
    session.begin()
    while True:
        for f in sc.renter.files:
            if f ['siapath'] == file_id:
                if f['available']:
                    new_file = session.query(File).filter_by(file_id=file_id).first()
                    new_file.status = "available"
                    session.commit()
                    os.remove(file_save_dir)
                    return
    


@app.route('/queue/<string:file_id>/<int:lifetime>', methods=['GET'])
@login_required
def download_file(file_id, lifetime):
    f = File.query.filter_by(user=current_user.id).filter_by(file_id=file_id).first_or_404()
    if f.status == "available":
        if lifetime > 2678400:
            return make_response(jsonify({'error': 'Lifetime too high; max is 2678400 seconds'}), 400)
        new_cached_file = CachedFile(f.file_id, current_user.id, lifetime)
        f.status = new_cached_file.cached_file_id
        sc.renter.download(f.file_id, os.path.join(app.config['CACHE_FOLDER'], new_cached_file.cached_file_id))
        db.session.add(new_cached_file)
        db.session.commit()
        return jsonify(new_cached_file.serialize())
    else:
        if f.status != "not available" or f.status != "uploading":
            return make_response(jsonify({'error': 'File already in cache', 'id': f.status}), 400)

@app.route('/status/<string:cached_file_id>', methods=['GET'])
@login_required
def status_file(cached_file_id):
    cached_file = CachedFile.query.filter_by(cached_file_id=cached_file_id).first_or_404()
    progress = get_downloadprogress(cached_file.file_id)
    if progress == 100 and cached_file.download_code == "":
        cached_file.download_code = secrets.token_hex(64)
        os.rename(os.path.join(app.config['CACHE_FOLDER'], cached_file.cached_file_id), os.path.join(app.config['FINAL_CACHE_FOLDER'], cached_file.download_code))
        db.session.commit()
        return jsonify({'status': 'downloading', 'progress': progress, 'download_code': cached_file.download_code})
    elif progress == 100 and cached_file.download_code != "":
        return jsonify({'status': 'downloading', 'progress': progress, 'download_code': cached_file.download_code})
    else:
        return jsonify({'status': 'downloading', 'progress': progress})
@app.route('/download/<string:download_code>')
def download_cached(download_code):
    filename = File.query.filter_by(file_id=CachedFile.query.filter_by(download_code=download_code).first().file_id).first().name
    print(filename)
    return send_from_directory(app.config['FINAL_CACHE_FOLDER'], download_code, as_attachment=True, attachment_filename=filename)

@app.route('/directdownload/<string:file_id>', methods=['GET'])
@login_required
def direct_download(file_id):
    print(file_id)
    cached_file = json.loads(download_file(file_id, 604800).data)
    cached_id = cached_file['id']
    print(cached_id)
    while 'download_code' not in json.loads(status_file(cached_id).data):
        pass
    return download_cached(json.loads(status_file(cached_id).data)['download_code'])

@app.route('/', methods=['GET'])
@login_required
def index():
    return render_template('index.html', email=current_user.email, files=File.query.filter_by(user=current_user.id).all())

@app.route('/downloads', methods=['GET'])
@login_required
def downloads():
    return render_template('downloads.html', email=current_user.email)

@app.route('/queue_list', methods=['GET'])
@login_required
def queue_list():
    return jsonify([{"cached": f.serialize(), "original": File.query.filter_by(file_id=f.file_id).first().serialize()} for f in CachedFile.query.filter_by(user=current_user.id).all()])

@app.route('/faq', methods=['GET'])
@login_required
def faq():
    return render_template('faq.html', email=current_user.email)

@app.route('/logout', methods=['GET'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('/')) 

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True, port=80, host="0.0.0.0")
    