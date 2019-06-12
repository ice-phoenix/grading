from app import app, db
from app.models import Block, BlockSubmission
from app.contest import block_dir, block_sub_dir,\
    BLOCK_WAIT_FOR_SECS, BLOCK_WAIT_FOR_SUBS, BLOCK_SOL_FILE,\
    BLOCK_NEXT_PUZZLE_FILE, BLOCK_WINNER_FILE, BLOCK_BALANCES_FILE,\
    BLOCK_PROBLEM_DESC, BLOCK_CONDITIONS_FILE, BOOSTER_PRICES, BUY_EXT
import os
import subprocess
import json
from datetime import datetime
from sqlalchemy import and_
from zipfile import ZipFile
import tempfile
import shutil
import collections

def block_complete(block):
    now = datetime.utcnow()
    diff = (now - block.created).total_seconds()
    num_subs = BlockSubmission.query.filter(BlockSubmission.block_num == block.id).count()

    return (diff >= BLOCK_WAIT_FOR_SECS) and (num_subs >= BLOCK_WAIT_FOR_SUBS)

def decide_accept_sub(t_id, form):
    block = Block.query.order_by(Block.id.desc()).first()
    errors = {}

    # Submission is for current block
    if form.block_num.data != block.id:
        errors['block_num'] = "Invalid block_num {}: current block is {}.".format(form.block_num.data, block.id)

    # Block still accepting submissions
    complete = block_complete(block)
    if complete:
        errors['block_complete'] = "Block {} is complete: no more submissions accepted.".format(block.id)

    # Team hasn't submitted before for this block
    is_resubmit = BlockSubmission.query.filter(
                    and_(BlockSubmission.block_num == block.id, BlockSubmission.team_id == t_id)
                ).count() > 0
    if is_resubmit:
        errors['is_resubmit'] = "You (team {}) have already sent a submission for block {}.".format(t_id, block.id)

    # Team hasn't selected the puzzle for this block
    if str(t_id) in get_excluded(block.id):
        errors['excluded'] = "Your (team {}) puzzle proposal is the puzzle for this block.".format(t_id)

    return len(errors) == 0, block, errors

def lambda_init_if_needed():
    # Creates the database record for the first block if it doesn't exist
    block = Block.query.order_by(Block.id.desc()).first()
    if block is None:
        block = Block()
        db.session.add(block)
        db.session.commit()

    return block

def get_current_block():
    return lambda_init_if_needed()

def process_block():
    block = Block.query.order_by(Block.id.desc()).first()

    # If block is now full and processing script not run already
    # (order reversed to short-circuit as early as possible)
    if not block.scheduled_proc and block_complete(block):
        pb = app.config['BLOCKS_PROC']
        process = subprocess.Popen([pb, '-b', str(block.id)])
        # Very important: DO _NOT_ wait for process to finish!
        # We don't want to block the request handler.
        block.scheduled_proc = True
        db.session.commit()

def get_balances(block_num=None):
    if block_num is None:
        block_num = get_current_block().id
    bp = os.path.join(block_dir(block_num), BLOCK_BALANCES_FILE)

    balances = {}
    with open(bp, 'r') as f:
        balances = json.load(f)
    return balances

def get_balance(t_id):
    t_id = str(t_id)
    return get_balances().get(t_id, 0)

def get_excluded(block_num=None):
    if block_num is None:
        block_num = get_current_block().id

    exp = os.path.join(block_dir(block_num), BLOCK_WINNER_FILE)
    ex = {'excluded': []}
    if os.path.exists(exp):
        with open(exp, 'r') as f:
            ex = json.load(f)
    return ex['excluded']

def get_problem(block_num=None):
    if block_num is None:
        block_num = get_current_block().id

    bd = block_dir(block_num)
    pp = os.path.join(bd, BLOCK_PROBLEM_DESC)
    problem = None
    with open(pp, 'r') as f:
        problem = f.read().rstrip()
    return problem

def get_conditions(block_num=None):
    if block_num is None:
        block_num = get_current_block().id

    bd = block_dir(block_num)
    cp = os.path.join(bd, BLOCK_CONDITIONS_FILE)
    conditions = None
    with open(cp, 'r') as f:
        conditions = f.read().rstrip()
    return conditions

def validate_booster_purchase(num_coins, filename):
    total = 0

    # This is nice since it removes the directory & files automatically
    with tempfile.TemporaryDirectory() as tmp:
        with ZipFile(filename) as zip:
            buy = list(filter(lambda fn: fn.endswith(BUY_EXT), zip.namelist()))
            zip.extractall(tmp, buy)

            cfn = os.path.join(tmp, "concat.txt")
            buy = list(map(lambda fn: os.path.join(tmp, fn), buy))

            # Concatenate all the buy files in one
            with open(cfn,'wb') as wfd:
                for fn in buy:
                    with open(fn,'rb') as fd:
                        shutil.copyfileobj(fd, wfd)

            with open(cfn, 'r') as f:
                count = collections.Counter(f.read())
                for booster in BOOSTER_PRICES.keys():
                    total += count.get(booster, 0) * BOOSTER_PRICES[booster]

    return total <= num_coins, total