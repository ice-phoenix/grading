#!/usr/bin/env python
from app import app, contest
import argparse
import subprocess
import os, shutil
import json
import pandas as pd
import pandas.errors
import random
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen


"""
./checker matrix <task_file.desc> <task_file.mat>
./checker block -p <current_task.mat> -c <lambda.chain> -b <blockNum> -s <submissionFolder> -o <path-to-scores.csv> -v <true>
"""

NOTIFY_URL = app.config['NOTIFY_URL'] or "http://localhost:5000/notify/block_created"

def process_scores(score_file):
    sc = pd.DataFrame(columns=[0, 1, 2])
    try:
        sc = pd.read_csv(score_file, header=None)
    except (FileNotFoundError, pandas.errors.EmptyDataError) as e:
        print(f"{contest.SCORE_FILE} exception {e}; there are no submissions for this block.")
        pass

    # 0 -> id, 1 -> score, 2 -> puzzle proposal GOOD/BAD

    # Have something to do only if there is a submission
    if len(sc) > 0:
        # minimum non-zero score
        best_score = sc[1][sc[1] > 0].min()
        # Normalise and sort scores
        sc[1] = sc[1].apply(lambda s: 0 if s == 0 else best_score / s)
        sc.sort_values([1, 2], ascending=False, inplace=True)
        sc.reset_index(drop=True, inplace=True)

    return sc

def select_next_puzzle(scores, block_num):
    # Remove all BAD entries and limit to N entries
    scores = scores[scores[2] == 'GOOD'].head(contest.BLOCK_PUZZLE_SEL)
    scores.reset_index(drop=True, inplace=True)

    pp = None
    winner = []
    # If there are no good entries, choose a predefined one
    if len(scores) == 0:
        name = "prob-{:03d}.desc".format(block_num)
        pp = os.path.join(app.config['BLOCKS_DIR'], contest.BLOCK_PREDEF_PUZZLE_DIR, name)

    else:
        # Return a random entry: there's a bug in DataFrame.sample! (so we roll our own)
        r = 0
        if len(scores) > 1:
            r = random.randrange(0, len(scores))
        next_puzzle_team = scores.iat[r, 0]
        
        subs = os.path.join(app.config['BLOCKS_DIR'], str(block_num), contest.BLOCK_SUBMISSIONS_DIR)
        pp = os.path.join(subs, str(next_puzzle_team), contest.BLOCK_NEXT_PUZZLE_FILE)
        winner = [str(next_puzzle_team)]

    print("[Block {}] Puzzle: {}".format(block_num + 1, pp))
    return pp, winner

def allocate_coins(balance_file, scores, winner, late):
    # Determine whether we're doing normal rewards or late-block rewards
    num_sel = contest.BLOCK_LATE_REWARD_SEL if late else contest.BLOCK_REWARD_SEL

    balance = {}
    with open(balance_file, 'r') as f:
        balance = json.load(f)

    new_balance = balance

    scores.reset_index(drop=True, inplace=True)
    # Only reward to top BLOCK_REWARD_SEL (might be more if ties / fewer if not enough subs)
    n_scores = list(scores[1].unique())

    print("All submissions:\n", scores)

    # smallest rewarded share
    srs = 0
    if len(n_scores) != 0:
        srs = n_scores[-1]
    if len(n_scores) >= num_sel:
        srs = n_scores[num_sel - 1]

    # filter to qualifying submissions
    scores = scores[(scores[1] >= srs)]
    scores = scores[scores[2] == 'GOOD']
    scores.reset_index(drop=True, inplace=True)
    print("Qualifying submissions:\n", scores)
    
    total_shares = scores[1].sum()

    # Prevent divide by zero
    if math.isclose(total_shares, 0.0):
        total_shares = 1.0

    for row_id in range(len(scores)):
        row = scores.loc[row_id]
        # Important: team must be str, not int
        team, share = str(row[0]), row[1]/total_shares
        new_balance[team] = balance.get(team, 0) + int(share * contest.BLOCK_SUBSIDY)
        if team in winner:
            new_balance[team] += contest.WINNER_SUBSIDY

    return new_balance

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process block submissions.')
    parser.add_argument('-b', metavar='N', required=True, help='block number')
    parser.add_argument('--late', action="store_true", help='is this a late block?')
    args = parser.parse_args()

    os.chdir(app.config['ROOT_DIR'])

    block_path = os.path.join(app.config['BLOCKS_DIR'], args.b)
    if not os.path.exists(block_path):
        parser.error("The given block does not exist in BLOCKS_DIR.")

    block_num = int(args.b)

    # Generate puzzle.mat
    chk = app.config['CHECKER_PATH']
    puzzle_path = os.path.join(block_path, contest.BLOCK_PROBLEM_DESC)
    mat_path = os.path.join(block_path, contest.BLOCK_PROBLEM_MAT)

    process = subprocess.Popen([chk, 'matrix', puzzle_path, mat_path])
    _ = process.wait()

    # Grade submissions
    # this fails if there are no submissions; SCORE_FILE will not exist
    lmbd = os.path.join(app.config['BLOCKS_DIR'], contest.BLOCK_CHAIN_DESC)
    subs = os.path.join(block_path, contest.BLOCK_SUBMISSIONS_DIR)
    scr = os.path.join(block_path, contest.SCORE_FILE)
    process = subprocess.Popen([chk, 'block', '-p', mat_path, '-c', lmbd, '-b', args.b, '-s',  subs, '-o', scr, '-v', 'true'])
    _ = process.wait()

    balance_file = os.path.join(block_path, contest.BLOCK_BALANCES_FILE)

    ## Next block
    next_b = block_num + 1
    scores = process_scores(scr)

    # Select puzzle
    next_puzzle, winner = select_next_puzzle(scores, block_num)
    # Compute balances
    next_balances = allocate_coins(balance_file, scores, winner, args.late)

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

    exp = os.path.join(next_block_path, contest.BLOCK_WINNER_FILE)
    with open(exp, 'w') as f:
        json.dump({"excluded": winner}, f)

    nsdp = os.path.join(next_block_path, contest.BLOCK_SUBMISSIONS_DIR)
    os.makedirs(nsdp, exist_ok=True)

    # Notify server that block has been created
    post_fields = {'secret': app.config['NOTIFY_SECRET_KEY'], 'block': next_b}
    request = Request(NOTIFY_URL, urlencode(post_fields).encode())
    response = urlopen(request).read().decode()
    print(response)