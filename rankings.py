#!/usr/bin/env python
from app import app, contest
import argparse
from datetime import datetime
import os
import math
import numpy as np
import pandas as pd

NUM_DIGITS = 2
FLOAT_FORMAT = '%.{}f'.format(NUM_DIGITS)
TEAM_NAME_MAX_LEN = 120

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
    ids.drop(columns='path', inplace=True)

    scores = pd.concat(raw_subs)
    scores.reset_index(inplace=True, drop=True)

    # Automatically handles "expanding" subs to num_problems (for submissions
    # that came before a stage change).
    ranking = pd.concat([ids, scores], axis=1)
    ranking.fillna(0, inplace=True, downcast='infer')

    return num_problems, ranking

def compute_score(row, max, multiplier):
    total = 0
    for prob, score in row.iteritems():
        if max[prob] > 0:
            total += round((score / max[prob]) * 1000 * multiplier[prob], NUM_DIGITS)
    return total

def get_ranking(num_problems, raw_ranking, multiplier):
    max = {}
    ranking = raw_ranking.copy()

    probs = list(range(1, num_problems + 1))
    for p in probs:
        max[p] = raw_ranking[p].max()
        ranking.drop(columns=p, inplace=True)

    scores = []
    raw_ranking = raw_ranking[probs]
    for row_id in range(len(ranking)):
        scores.append(compute_score(raw_ranking.loc[row_id], max, multiplier))

    scores = pd.DataFrame(scores)
    scores.columns = ['score']
    ranking = pd.concat([ranking, scores], axis=1)
    ranking.sort_values('score', ascending=False, inplace=True)

    return ranking

def parse_sizes_file(path):
    mult = {}

    x = pd.read_csv(path, header=None)
    for row_id in range(len(x)):
        row = x.loc[row_id]
        # Start at 1
        mult[row_id + 1] = math.log2(row[1] * row[2])
        
    return mult

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute rankings.')

    start = datetime.utcnow()
    default_time = start.strftime(contest.ZIP_TIME_FORMAT)

    parser.add_argument('-t', metavar='TIME', default=default_time, help='latest submission time to consider')
    parser.add_argument('-p', metavar='PATH', required=True, help='problems folder')
    parser.add_argument('-g', metavar='PATH', required=True, help='grades folder')
    parser.add_argument('--output-folder', metavar='PATH', required=True, help='output path to save CSV and HTML files')

    args = parser.parse_args()

    # Parse multiplier
    mutliplier = parse_sizes_file(os.path.join(args.p, contest.SIZES_FILE))
    num_probs, raw = get_raw_ranking(args.g, args.t)
    ranking = get_ranking(num_probs, raw, mutliplier)

    ranking.reset_index(inplace=True)
    ranking.index += 1
    ranking.drop(columns=['index', 'id', 'time'], inplace=True)

    # Remove seconds and microseconds from filename
    filename = start.strftime(contest.ZIP_TIME_MINUTE)

    csv_output = os.path.join(args.output_folder, filename + '.csv')
    html_output = os.path.join(args.output_folder, filename + '.html')

    # Create folder if it doesn't exist
    os.makedirs(args.output_folder, exist_ok=True)

    ranking.to_csv(csv_output, float_format=FLOAT_FORMAT, index=True)
    ranking.to_html(html_output, float_format=FLOAT_FORMAT, justify='center')

    html_latest = os.path.join(args.output_folder, 'latest.html')
    wrapper = """<!DOCTYPE html>
    <html>
    <head>
    <title>Live Rankings</title>
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
