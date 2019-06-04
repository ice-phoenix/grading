from app import app, db, celery
from app.models import Team, Submission
import os

ZIP_TIME_FORMAT = '%Y-%m-%d-%H-%M-%S-%f'
ZIP_TIME_MINUTE = '%Y-%m-%d-%H-%M'
HASH_FILE = "hash.txt"
SCORE_FILE = "score.csv"
TIMING_FILE = "timing.txt"
SUBMISSIONS_FILE = "submissions.txt"
TEAM_NAME_FILE = "team_name.txt"
TEAM_ID_FILE = "team_id.txt"
SIZES_FILE = "sizes.csv"

PROFILE_FILE = "profile.json"
PROFILE_ZIP = "code.zip"
PROFILE_HASH = HASH_FILE

BLOCK_SUBSIDY = 1000 * 1000
BLOCK_PUZZLE_SEL = 10   # consider this many top-scoring proposals

BLOCK_WAIT_FOR_SUBS = 1
BLOCK_WAIT_FOR_SECS = 60

BLOCK_CHAIN_DESC = "lambda.chain"
BLOCK_PROBLEM_DESC = "puzzle.desc"
BLOCK_PROBLEM_MAT = "puzzle.mat"
BLOCK_SOL_FILE = "puzzle.sol"
BLOCK_NEXT_PUZZLE_FILE = "next-puzzle.desc"
BLOCK_BALANCES_FILE = "balances.json"
BLOCK_CONDITIONS_FILE = "next-puzzle.cond"
BLOCK_SUBMISSIONS_DIR = "submissions"

def team_dir(t_id):
    return os.path.join(app.config['TEAM_DIR'], f'{t_id}/')

def grades_dir(t_priv):
    return os.path.join(app.config['GRADES_DIR'], f'{t_priv}/')

def sub_dir(t_id, ts):
    return os.path.join(team_dir(t_id), f'{ts}/')

def grades_sub_dir(t_priv, ts):
    return os.path.join(grades_dir(t_priv), f'{ts}/')

def block_sub_dir(t_id, block_num):
    return os.path.join(app.config['BLOCKS_DIR'], f'{block_num}', BLOCK_SUBMISSIONS_DIR, f'{t_id}')

def profile_dir(t_id):
    return os.path.join(app.config['PROFILES_DIR'], f'{t_id}/')

@app.shell_context_processor
def make_shell_context():
    return {'celery': celery, 'db': db, 'Team': Team, 'Submission': Submission}