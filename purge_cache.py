from siahost import app, db, CachedFile
from flask_security import login_required
import datetime
import os

def purge_cache():
    for f in CachedFile.query.all():
        if f.created + datetime.timedelta(seconds=f.lifetime) < datetime.datetime.utcnow():
            os.remove(os.path.join(app.config['FINAL_CACHE_FOLDER'], f.download_code))
            db.session.delete(f)
            db.session.commit()


if __name__ == '__main__':
    purge_cache()