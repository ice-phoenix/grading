from app import app, db, celery
from app.models import Team, Submission
import os

ZIP_TIME_FORMAT = '%Y-%m-%d-%H-%M-%S-%f'

def team_dir(t_id):
    return os.path.join(app.config['TEAM_DIR'], f'{t_id}/')

def grades_dir(t_id):
    return os.path.join(app.config['GRADES_DIR'], f'{t_id}/')

def sub_dir(t_id, ts):
    return os.path.join(team_dir(t_id), f'{ts}/')

def grades_sub_dir(t_id, ts):
    return os.path.join(grades_dir(t_id), f'{ts}/')


@app.shell_context_processor
def make_shell_context():
    return {'celery': celery, 'db': db, 'Team': Team, 'Submission': Submission}