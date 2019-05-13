from app import app, celery
import random
import time
import os
from zipfile import ZipFile
import subprocess

def team_dir(t_id):
    return os.path.join(app.config['TEAM_DIR'], 'team{}/'.format(t_id))

def sub_dir(t_id, ts):
    return os.path.join(team_dir(t_id), '{}/'.format(ts))

@celery.task
def grade(t_id, ts, filename, coins):
    location = os.path.join(app.config['SUBMIT_DIR'], filename)

    # Extract submission in the appropriate directory
    sd = sub_dir(t_id, ts)
    os.makedirs(sd, exist_ok=True)
    os.chdir(sd)
    with ZipFile(location) as zip:
        zip.extractall()

    chk = app.config['CHECKER_PATH']
    pd = app.config['PROBLEM_DIR']
    r = os.path.join(sd, 'score.csv')

    # Call checker
    os.chdir(app.config['ROOT_DIR'])
    subprocess.call([chk, 'team', '-p', pd, '-s', sd, '-o', r, '-v', 'true'])

    return True