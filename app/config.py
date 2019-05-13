import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or '6cb49381bd6a6f239220e42'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ROOT_DIR = os.path.abspath(os.path.join(basedir, '../'))
    CHECKER_PATH = os.path.join(ROOT_DIR, 'checker')

    PROBLEM_DIR = os.path.join(ROOT_DIR, 'persistent/problems')
    TEAM_DIR = os.path.join(ROOT_DIR, 'persistent/')

    SUBMIT_DIR = os.path.join(ROOT_DIR, 'persistent/zips/')
    SUBMIT_DELAY = 10  # None or number of seconds

    CELERY_BROKER_URL = 'pyamqp://guest@localhost//'
    CELERY_RESULT_BACKEND = 'rpc://'
