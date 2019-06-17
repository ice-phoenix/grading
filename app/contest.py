from app import app, db, celery
from app.models import Team, Submission
import os
from datetime import datetime

ZIP_TIME_FORMAT = '%Y-%m-%d-%H-%M-%S-%f'
ZIP_TIME_MINUTE = '%Y-%m-%d-%H-%M'
HASH_FILE = "hash.txt"
SCORE_FILE = "score.csv"
TIMING_FILE = "timing.txt"
SPENT_LAM_FILE = "spent.txt"
SUBMISSIONS_FILE = "submissions.txt"
TEAM_NAME_FILE = "team_name.txt"
TEAM_ID_FILE = "team_id.txt"
SIZES_FILE = "sizes.csv"

BUY_EXT = ".buy"
BOOSTER_PRICES = {
    'B': 1000,  # batteries/brush
    'F': 300,   # fast wheels/coffee
    'L': 700,   # drill
    'R': 1200,  # teleport
    'C': 2000   # clone/call friend
}

PROFILE_FILE = "profile.json"
PROFILE_ZIP = "code.zip"
PROFILE_HASH = HASH_FILE

BLOCK_SUBSIDY = 100 * 1000
WINNER_SUBSIDY = 2000

BLOCK_REWARD_SEL = 25                 # award coins to this many 
BLOCK_LATE_REWARD_SEL = 9999          # large number / award to all submissions if late
BLOCK_PUZZLE_SEL = 10                 # consider this many top-scoring proposals for next puzzle

BLOCK_WAIT_FOR_SUBS = 25
BLOCK_WAIT_FOR_SECS = 15 * 60

BLOCK_LATE_WAIT_FOR_SUBS = 0
BLOCK_LATE_WAIT_FOR_SECS = 30 * 60

BLOCK_CHAIN_DESC = "lambda.chain"
BLOCK_PROBLEM_DESC = "puzzle.desc"
BLOCK_PROBLEM_MAT = "puzzle.mat"
BLOCK_SOL_FILE = "puzzle.sol"
BLOCK_NEXT_PUZZLE_FILE = "next-puzzle.desc"
BLOCK_BALANCES_FILE = "balances.json"
BLOCK_WINNER_FILE = "excluded.json"
BLOCK_CONDITIONS_FILE = "next-puzzle.cond"
BLOCK_SUBMISSIONS_DIR = "submissions"
BLOCK_PREDEF_PUZZLE_DIR = "predef"

### STAGES

# ZIP_TIME_MINUTE = '%Y-%m-%d-%H-%M'

# oficial
C_TIME_STAGE_1 = C_TIME_STAGE_INITIAL       = "2019-06-21-10-00"
C_TIME_STAGE_2 = C_TIME_STAGE_TELEPORTS     = "2019-06-21-17-00"
C_TIME_STAGE_3 = C_TIME_STAGE_CLONES        = "2019-06-22-00-00"
C_TIME_STAGE_4a = C_TIME_STAGE_LAM_REVEAL   = "2019-06-22-10-00"
C_TIME_STAGE_4b = C_TIME_STAGE_LAM_MINE     = "2019-06-22-14-00"
C_TIME_STAGE_4c = C_TIME_STAGE_LAM_STOP     = "2019-06-24-07-00"
C_TIME_STAGE_5 = C_TIME_STAGE_FINISH        = "2019-06-24-10-00"
C_TIME_STAGE_6 = C_TIME_PROFILE_FINISH      = "2019-06-24-12-00"

FREEZE_LIGHTNING_START  = "2019-06-22-07-00"
FREEZE_LIGHTNING_END    = "2019-06-22-13-00"
FREEZE_CONTEST_START    = "2019-06-24-07-00"

# XXX Testing
C_TIME_STAGE_1 = C_TIME_STAGE_INITIAL       = "2019-06-17-09-00"
C_TIME_STAGE_2 = C_TIME_STAGE_TELEPORTS     = "2019-06-17-09-05"
C_TIME_STAGE_3 = C_TIME_STAGE_CLONES        = "2019-06-17-09-10"
C_TIME_STAGE_4a = C_TIME_STAGE_LAM_REVEAL   = "2019-06-17-09-15"
C_TIME_STAGE_4b = C_TIME_STAGE_LAM_MINE     = "2019-06-17-09-23"
C_TIME_STAGE_4c = C_TIME_STAGE_LAM_STOP     = "2019-06-17-09-40"
C_TIME_STAGE_5 = C_TIME_STAGE_FINISH        = "2019-06-17-09-45"
C_TIME_STAGE_6 = C_TIME_PROFILE_FINISH      = "2019-06-17-09-55"

FREEZE_LIGHTNING_START  = "2019-06-17-09-12"
FREEZE_LIGHTNING_END    = "2019-06-17-09-18"
FREEZE_CONTEST_START    = "2019-06-17-09-40"

BLOCK_WAIT_FOR_SUBS = 5
BLOCK_WAIT_FOR_SECS = 2.5 * 60
BLOCK_LATE_WAIT_FOR_SUBS = 0
BLOCK_LATE_WAIT_FOR_SECS = 5 * 60

def get_stage():
    now = datetime.utcnow().strftime(ZIP_TIME_MINUTE)
    if now < C_TIME_STAGE_2:
        return C_TIME_STAGE_1

    elif now < C_TIME_STAGE_3:
        return C_TIME_STAGE_2

    elif now < C_TIME_STAGE_4a:
        return C_TIME_STAGE_3

    elif now < C_TIME_STAGE_4b:
        return C_TIME_STAGE_4a

    elif now < C_TIME_STAGE_4c:
        return C_TIME_STAGE_4b

    elif now < C_TIME_STAGE_5:
        return C_TIME_STAGE_4c

    elif now < C_TIME_STAGE_6:
        return C_TIME_STAGE_5

    else:
        return C_TIME_STAGE_6

def get_num_probs():
    stage = get_stage()
    probs_by_stage = {
        C_TIME_STAGE_1: 150,
        C_TIME_STAGE_2: 220,
        C_TIME_STAGE_3: 300,
        C_TIME_STAGE_4a: 300,
        C_TIME_STAGE_4b: 300,
        C_TIME_STAGE_4c: 300,
        C_TIME_STAGE_5: 0
    }

    return probs_by_stage.get(stage, 0)

def can_submit():
    stage = get_stage()
    return stage >= C_TIME_STAGE_INITIAL and stage < C_TIME_STAGE_FINISH

def can_register():
    return can_submit()

def can_edit_profile():
    stage = get_stage()
    return stage >= C_TIME_STAGE_INITIAL and stage < C_TIME_PROFILE_FINISH

def can_buy():
    stage = get_stage()
    return stage >= C_TIME_STAGE_LAM_REVEAL

def blockchain_can_see():
    stage = get_stage()
    return stage >= C_TIME_STAGE_LAM_REVEAL

def blockchain_can_mine():
    stage = get_stage()
    return stage >= C_TIME_STAGE_LAM_MINE and stage < C_TIME_STAGE_LAM_STOP

def rankings_frozen():
    now = datetime.utcnow().strftime(ZIP_TIME_MINUTE)
    lightning = (now >= FREEZE_LIGHTNING_START and now < FREEZE_LIGHTNING_END)
    end = (now >= FREEZE_CONTEST_START)
    return lightning or end

def rankings_coins():
    now = datetime.utcnow().strftime(ZIP_TIME_MINUTE)
    return now >= C_TIME_STAGE_4a

###

def team_dir(t_id):
    return os.path.join(app.config['TEAM_DIR'], f'{t_id}/')

def grades_dir(t_priv):
    return os.path.join(app.config['GRADES_DIR'], f'{t_priv}/')

def sub_dir(t_id, ts):
    return os.path.join(team_dir(t_id), f'{ts}/')

def grades_sub_dir(t_priv, ts):
    return os.path.join(grades_dir(t_priv), f'{ts}/')

def block_dir(block_num):
    return os.path.join(app.config['BLOCKS_DIR'], f'{block_num}')

def block_sub_dir(t_id, block_num):
    return os.path.join(block_dir(block_num), BLOCK_SUBMISSIONS_DIR, f'{t_id}')

def profile_dir(t_id):
    return os.path.join(app.config['PROFILES_DIR'], f'{t_id}/')

@app.shell_context_processor
def make_shell_context():
    return {'celery': celery, 'db': db, 'Team': Team, 'Submission': Submission}