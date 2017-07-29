from siahost import app, sc

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