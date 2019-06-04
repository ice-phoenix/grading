#!/usr/bin/env python
from app import app, contest
import argparse
import subprocess
import os, shutil
import json
import pandas as pd
import random
from urllib.parse import urlencode
from urllib.request import Request, urlopen


"""
./checker matrix <task_file.desc> <task_file.mat>
./checker block -p <current_task.mat> -c <lambda.chain> -b <blockNum> -s <submissionFolder> -o <path-to-scores.csv> -v <true>
"""

NOTIFY_URL = "http://localhost:5000/notify/block_created"

def process_scores(score_file):
    sc = pd.read_csv(score_file, header=None)
    # 0 -> id, 1 -> score, 2 -> puzzle proposal GOOD/BAD
    max_score = sc[1].max()

    # Normalise and sort scores
    sc[1] = sc[1].apply(lambda s: s/max_score)
    sc.sort_values([1, 2], ascending=False, inplace=True)

    return sc

def select_next_puzzle(scores):
    # Remove all BAD entries and limit to N entries
    scores = scores[scores[2] == 'GOOD'].head(contest.BLOCK_PUZZLE_SEL)
    # Return a random entry: there's a bug in DataFrame.sample! (so we roll our own)
    r = 0
    if len(scores) > 1:
        r = random.randrange(0, len(scores))
    return scores.iat[r, 0]

def allocate_coins(balance_file, scores):
    balance = {}
    with open(balance_file, 'r') as f:
        balance = json.load(f)

    new_balance = {}
    total_shares = scores[1].sum()

    for row_id in range(len(scores)):
        row = scores.loc[row_id]
        # Important: team must be str, not int
        team, share = str(row[0]), row[1]/total_shares
        new_balance[team] = balance.get(team, 0) + int(share * contest.BLOCK_SUBSIDY)

    return new_balance

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process block submissions.')
    parser.add_argument('-b', metavar='N', required=True, help='block number')
    args = parser.parse_args()

    os.chdir(app.config['ROOT_DIR'])

    block_path = os.path.join(app.config['BLOCKS_DIR'], args.b)
    if not os.path.exists(block_path):
        parser.error("The given block does not exist in BLOCKS_DIR.")

    # Generate puzzle.mat
    chk = app.config['CHECKER_PATH']
    puzzle_path = os.path.join(block_path, contest.BLOCK_PROBLEM_DESC)
    mat_path = os.path.join(block_path, contest.BLOCK_PROBLEM_MAT)

    process = subprocess.Popen([chk, 'matrix', puzzle_path, mat_path])
    _ = process.wait()

    # Grade submissions
    lmbd = os.path.join(app.config['BLOCKS_DIR'], contest.BLOCK_CHAIN_DESC)
    subs = os.path.join(block_path, contest.BLOCK_SUBMISSIONS_DIR)
    scr = os.path.join(block_path, contest.SCORE_FILE)
    process = subprocess.Popen([chk, 'block', '-p', mat_path, '-c', lmbd, '-b', args.b, '-s',  subs, '-o', scr, '-v', 'true'])
    _ = process.wait()

    balance_file = os.path.join(block_path, contest.BLOCK_BALANCES_FILE)

    ## Next block
    next_b = int(args.b) + 1
    scores = process_scores(scr)

    # Select puzzle
    next_puzzle_team = select_next_puzzle(scores)
    next_puzzle = os.path.join(subs, str(next_puzzle_team), contest.BLOCK_NEXT_PUZZLE_FILE)

    # Compute balances
    next_balances = allocate_coins(balance_file, scores)

    # Write next block
    next_block_path = os.path.join(app.config['BLOCKS_DIR'], str(next_b))
    os.makedirs(next_block_path, exist_ok=True)

    npp = os.path.join(next_block_path, contest.BLOCK_PROBLEM_DESC)
    shutil.copy(next_puzzle, npp)

    nbp = os.path.join(next_block_path, contest.BLOCK_BALANCES_FILE)
    with open(nbp, 'w') as f:
        json.dump(next_balances, f)

    ncp = os.path.join(next_block_path, contest.BLOCK_CONDITIONS_FILE)
    with open(lmbd, 'r') as r:
        lines = r.readlines()
        # Block numbers start at 1, whereas line numbers start at 0
        cond = lines[next_b - 1]
        with open(ncp, 'w') as w:
            w.write(cond)

    nsdp = os.path.join(next_block_path, contest.BLOCK_SUBMISSIONS_DIR)
    os.makedirs(nsdp, exist_ok=True)

    # Notify server that block has been created
    post_fields = {'secret': app.config['NOTIFY_SECRET_KEY'], 'block': next_b}
    request = Request(NOTIFY_URL, urlencode(post_fields).encode())
    response = urlopen(request).read().decode()
    print(response)