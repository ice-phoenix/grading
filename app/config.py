import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
    ROOT_DIR = os.path.abspath(os.path.join(basedir, '../'))
    PERSISTENT_DIR = os.environ.get('PERSISTENT_DIR') or os.path.join(ROOT_DIR, 'persistent')
    DB_DIR = os.environ.get('DB_DIR') or ROOT_DIR

    BLOCKS_DIR = os.environ.get('BLOCKS_DIR') or os.path.join(PERSISTENT_DIR, 'blocks')
    BLOCKS_PROC = os.path.join(ROOT_DIR, 'block.py')

    SECRET_KEY = os.environ.get('SECRET_KEY') or '6cb49381bd6a6f239220e42'
    NOTIFY_SECRET_KEY = os.environ.get('NOTIFY_SECRET_KEY') or '1aab559c46c53fb6a6804ab7ae3e826b'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(DB_DIR, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CHECKER_PATH = os.path.join(ROOT_DIR, 'checker')

    PRIV_ID_LEN = 12

    PROBLEM_DIR = os.path.join(PERSISTENT_DIR, 'problems/')
    TEAM_DIR = os.path.join(PERSISTENT_DIR, 'teams/')
    GRADES_DIR = os.path.join(PERSISTENT_DIR, 'grades/')
    SUBMIT_DIR = os.path.join(PERSISTENT_DIR, 'zips/')
    SUBMIT_DELAY = 10  # None or number of seconds

    CELERY_BROKER_URL = os.environ.get('BROKER_URL') or 'pyamqp://guest@localhost//'
    CELERY_RESULT_BACKEND = 'rpc://'
    CELERY_IGNORE_RESULT = True