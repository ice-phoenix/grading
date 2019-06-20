#!/usr/bin/env python
from app import app, contest
import argparse
from datetime import datetime
import os
import math
import numpy as np
import pandas as pd
import requests

NUM_DIGITS = 2
FLOAT_FORMAT = '%.{}f'.format(NUM_DIGITS)
TEAM_NAME_MAX_LEN = 120
BALANCES_URL = app.config['BALANCES_URL'] or "http://localhost:5000/lambda/getbalances"
TEAMS_URL = app.config['TEAMS_URL'] or "http://localhost:5000/teams"

def get_team_info(root, f=contest.TEAM_ID_FILE):
    info = 0
    with open(os.path.join(root, f), 'r') as f:
        info = f.readline().rstrip('\n')
    return info

def get_latest_submissions(grade_dir, time):
    subs = []

    for root, dirs, files in os.walk(grade_dir):
        # Descend into per-team directories
        if root != grade_dir:
            # Get only last submission
            dirs = list(filter(lambda d: d <= time, dirs))
            path = None
            ts = None
            if len(dirs) > 0:
                dirs = [sorted(dirs)[-1]]
                ts = dirs[0]
                path = os.path.join(root, ts)

            if ts is not None:
                t_id = get_team_info(root, contest.TEAM_ID_FILE)
                t_name = get_team_info(root, contest.TEAM_NAME_FILE)
                subs.append({'id':t_id, 'name':t_name, 'time':ts, 'path':path})

    return subs

def get_raw_ranking(grade_dir, time):
    latest_subs = get_latest_submissions(grade_dir, time)
    
    # num_problems = max problems in _any_ submission
    # Doing it this way so this script doesn't need to know about different
    # stages in the contest.
    num_problems = 0
    raw_subs = []

    for sub in latest_subs:
        path = os.path.join(sub['path'], contest.SCORE_FILE)
        s = pd.read_csv(path, header=None, names=['prob', 'score', 'msg'])
        s.drop(columns='msg', inplace=True)
        s.set_index('prob', inplace=True)

        num_problems = max(num_problems, len(s))
        raw_subs.append(s.T)

    ids = pd.DataFrame(latest_subs)
    scores = pd.concat(raw_subs) if len(raw_subs) > 0 else pd.DataFrame()
    scores.reset_index(inplace=True, drop=True)

    # Automatically handles "expanding" subs to num_problems (for submissions
    # that came before a stage change).
    ranking = pd.concat([ids, scores], axis=1)
    ranking.fillna(0, inplace=True, downcast='infer')

    return num_problems, ranking

def compute_score(row, best, multiplier):
    total = 0
    for prob, score in row.iteritems():
        if score > 0:
            total += math.ceil((best[prob] / score) * 1000 * multiplier[prob])
    return total

def compute_unspent(row, balances):
    t_id = row['id']
    sp = os.path.join(row['path'], contest.SPENT_LAM_FILE)

    total = balances.get(t_id, 0)
    spent = 0
    # Get value in spent.txt
    try:
        with open(sp, 'r') as f:
            spent = int(f.read())
    except:
        pass

    unspent = total - spent
    return unspent, total

def get_ranking(num_problems, raw_ranking, multiplier, consider_coins):
    best = {}
    ranking = raw_ranking.copy()

    probs = list(range(1, num_problems + 1))
    for p in probs:
        nonzero = raw_ranking[raw_ranking[p] > 0][p]
        best[p] = nonzero.min()
        ranking.drop(columns=p, inplace=True)

    scores = []
    raw_ranking = raw_ranking[probs]
    for row_id in range(len(ranking)):
        scores.append(compute_score(raw_ranking.loc[row_id], best, multiplier))

    # Collect teams with no submission
    response = requests.get(TEAMS_URL, allow_redirects=True)
    teams = response.json()
    to_add = []
    for t_id, t_name in teams.items():
        exists = (len(ranking) > 0) and (ranking['id'] == t_id).any()
        if not exists:
            to_add.append({'id': t_id, 'name': t_name, 'path': '', 'time': ''})
            scores.append(0)

    # Insert teams with no submission into ranking
    to_add = pd.DataFrame(to_add)
    ranking = ranking.append(to_add, ignore_index=True)

    # If len(ranking) == 0, just break; no one has registered yet
    if len(ranking) == 0:
        return None, None

    scores = pd.DataFrame(scores)
    scores.columns = ['score']

    hodl = None
    if consider_coins:
        # Get LAM balances for all teams
        response = requests.get(BALANCES_URL, allow_redirects=True)
        balances = response.json()

        unspent_coins = []
        total_coins = []
        for row_id in range(len(ranking)):
            u, t = compute_unspent(ranking.loc[row_id], balances)
            unspent_coins.append(u)
            total_coins.append(t)

        unspent = pd.DataFrame(unspent_coins)
        unspent.columns = ['unspent LAM']

        hodl = ranking.copy()
        hodl = pd.concat([hodl, unspent], axis=1)
        hodl.sort_values('unspent LAM', ascending=False, inplace=True)

        ranking = pd.concat([ranking, scores, unspent], axis=1)
        ranking['score + unspent LAM'] = ranking['score'] + ranking['unspent LAM']
        ranking.drop(columns=['unspent LAM'], inplace=True)
        ranking.sort_values('score + unspent LAM', ascending=False, inplace=True)

    else:
        ranking = pd.concat([ranking, scores], axis=1)
        ranking.sort_values('score', ascending=False, inplace=True)

    return ranking, hodl

def parse_sizes_file(path):
    mult = {}

    x = pd.read_csv(path, header=None)
    for row_id in range(len(x)):
        row = x.loc[row_id]
        # Start at 1
        mult[row_id + 1] = math.log2(row[1] * row[2])
        
    return mult

def write_latest(ranking, args):
    # Write latest.html
    html_latest = os.path.join(args.output_folder, 'latest.html')
    wrapper = """<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Live Rankings</title>
    <link rel="stylesheet" href="https://icfpcontest2019.github.io/assets/main.css">
    </head>
    <center>
    <h1>Live Rankings</h1>
    <pre>Last updated: {}</pre>
    {}
    </center>
    </html>"""

    time = datetime.strptime(args.t, contest.ZIP_TIME_FORMAT).strftime("%c")
    pd.option_context('display.max_colwidth', TEAM_NAME_MAX_LEN)
    table = ranking.to_html(float_format=FLOAT_FORMAT, justify='center')
    page=wrapper.format(time, table)

    with open(html_latest, 'w') as f:
        f.write(page)

def write_hodl(hodl, args):
    # Write hodl.html
    hodl_latest = os.path.join(args.output_folder, 'hodl.html')
    wrapper = """<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Biggest HODLers</title>
    <link rel="stylesheet" href="https://icfpcontest2019.github.io/assets/main.css">
    </head>
    <center>
    <h1>Biggest HODLers</h1>
    <h2>(Teams with most unspent LAM)</h2>
    <pre>Last updated: {}</pre>
    {}
    </center>
    </html>"""

    time = datetime.strptime(args.t, contest.ZIP_TIME_FORMAT).strftime("%c")
    pd.option_context('display.max_colwidth', TEAM_NAME_MAX_LEN)
    table = hodl.to_html(float_format=FLOAT_FORMAT, justify='center')
    page=wrapper.format(time, table)

    with open(hodl_latest, 'w') as f:
        f.write(page)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute rankings.')

    start = datetime.utcnow()
    default_time = start.strftime(contest.ZIP_TIME_FORMAT)

    parser.add_argument('-t', metavar='TIME', default=default_time, help='latest submission time to consider')
    parser.add_argument('-p', metavar='PATH', required=True, help='problems folder')
    parser.add_argument('-g', metavar='PATH', required=True, help='grades folder')
    parser.add_argument('--output-folder', metavar='PATH', required=True, help='output path to save CSV and HTML files')
    parser.add_argument('--coins', action="store_true", help='take LAM balance into consideration?')

    args = parser.parse_args()

    # XXX: stages; args.coins
    args.coins = args.coins or contest.rankings_coins()
    # Write empty hodl.html (to handle stage transition when rankings frozen)
    if args.coins:
        hodl_path = os.path.join(args.output_folder, 'hodl.html')
        # ... only if file doesn't exist already
        if not os.path.exists(hodl_path):
            write_hodl(pd.DataFrame(), args)
    if contest.rankings_frozen():
        print("[{}] Rankings frozen.".format(default_time))
        exit(0)

    # Parse multiplier
    mutliplier = parse_sizes_file(os.path.join(args.p, contest.SIZES_FILE))
    num_probs, raw = get_raw_ranking(args.g, args.t)
    ranking, hodl = get_ranking(num_probs, raw, mutliplier, args.coins)

    # Remove seconds and microseconds from filename
    filename = start.strftime(contest.ZIP_TIME_MINUTE)

    csv_output = os.path.join(args.output_folder, filename + '.csv')
    html_output = os.path.join(args.output_folder, filename + '.html')

    # Create folder if it doesn't exist
    os.makedirs(args.output_folder, exist_ok=True)

    # Reset indices and make something up if nothing exists yet
    if ranking is not None:
        ranking.reset_index(inplace=True)
        ranking.index += 1
        ranking.drop(columns=['index', 'id', 'time', 'path'], inplace=True)
    else:
        ranking = pd.DataFrame()

    if hodl is not None:
        hodl.reset_index(inplace=True)
        hodl.index += 1
        hodl.drop(columns=['index', 'id', 'time', 'path'], inplace=True)
    else:
        hodl = pd.DataFrame()

    ## Write the files!
    ranking.to_csv(csv_output, float_format=FLOAT_FORMAT, index=True, encoding='utf-8')
    ranking.to_html(html_output, float_format=FLOAT_FORMAT, justify='center')

    write_latest(ranking, args)

    if args.coins:
        write_hodl(hodl, args)
