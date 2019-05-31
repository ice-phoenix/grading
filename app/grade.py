from app import app, celery
from celery.utils.log import get_task_logger
from app.contest import team_dir, sub_dir, grades_sub_dir, ZIP_TIME_FORMAT, HASH_FILE, SCORE_FILE, TIMING_FILE
import random
import time
import os, tempfile
from zipfile import ZipFile
from datetime import datetime
import subprocess
import sys
import shutil

logger = get_task_logger(__name__)

# https://stackoverflow.com/questions/8299386/modifying-a-symlink-in-python/55742015#55742015
def symlink_force(target, link_name):
    '''
    Create a symbolic link link_name pointing to target.
    Overwrites link_name if it exists.
    '''

    # os.replace() may fail if files are on different filesystems
    link_dir = os.path.dirname(link_name)

    while True:
        temp_link_name = tempfile.mktemp(dir=link_dir)

        # os.* functions mimic as closely as possible the underlying system functions
        # The POSIX symlink() returns EEXIST if link_name already exists
        # https://pubs.opengroup.org/onlinepubs/9699919799/functions/symlink.html
        try:
            os.symlink(target, temp_link_name)
            break
        except FileExistsError:
            pass
    try:
        os.replace(temp_link_name, link_name)
    except:  # OSError (permission denied), or SIG{INT,QUIT,...}
        if os.path.exists(temp_link_name):
            os.remove(temp_link_name)

# acks_late=True means the task is ACKed after it finishes executing
# if worker crashes, it is retried!
@celery.task(bind=True, autoretry_for=(Exception,), acks_late=True, default_retry_delay=30)
def grade(self, t_id, t_priv, t_name, ts, filename, hash, coins):
    location = os.path.join(app.config['SUBMIT_DIR'], filename)

    logger.info(f'Processing {hash}')
    logger.info(f'Extracting archive {location}')

    td = team_dir(t_id)
    os.makedirs(td, exist_ok=True)

    # Extract submission in the appropriate directory
    sd = sub_dir(t_id, ts)
    os.makedirs(sd, exist_ok=True)
    os.chdir(sd)
    with ZipFile(location) as zip:
        zip.extractall()

    logger.info(f'Running checker on {str(sd)}')
    chk = app.config['CHECKER_PATH']
    pd = app.config['PROBLEM_DIR']
    rf = os.path.join(sd, SCORE_FILE)

    # Call checker
    os.chdir(app.config['ROOT_DIR'])
    checker_start_time = datetime.utcnow()

    # We use this rather than subprocess.call() to ensure the checker process is
    # killed when the Celery worker is killed

    process = subprocess.Popen([chk, 'team', '-p', pd, '-s', sd, '-o', rf],
	                                      stdout=subprocess.PIPE,
	                                      stderr=subprocess.STDOUT)
    out = process.communicate()[0]
    _ = process.wait()
    # Hack to get output into stderr
    if out != b'Grading complete\n':
        print(out, file=sys.stderr)
        raise Exception('Checker failed.')

    checker_end_time = datetime.utcnow()

    # Compute timing information
    task_received_time = datetime.strptime(ts, ZIP_TIME_FORMAT)
    queue_time = (checker_start_time - task_received_time).total_seconds()
    checker_time = (checker_end_time - checker_start_time).total_seconds()
    total_time = queue_time + checker_time

    # Put the hash in the grades directory
    gd = grades_sub_dir(t_priv, ts)
    os.makedirs(gd, exist_ok=True)

    hf = os.path.join(gd, HASH_FILE)
    with open(hf, 'w') as f:
        f.write(hash)

    # Write timing information
    for dir in [sd, gd]:
        tf = os.path.join(dir, TIMING_FILE)
        with open(tf, 'w') as f:
            info = "Task ID: {}\nQueue waiting time: {}\nChecker time: {}\nTotal waiting time: {}\n".format(self.request.id, queue_time, checker_time, total_time)
            f.write(info)

    # Copy score from submission directory to grades directory
    # TODO: sanitize
    src_fn = rf
    dst_fn = os.path.join(gd, SCORE_FILE)
    shutil.copyfile(src_fn, dst_fn)

    # Update latest
    link = os.path.join(td, 'latest-graded')
    graded_before = os.path.exists(link)

    os.chdir(td)
    # Only update 'latest-graded' if first time or we're grading a newer submission
    if (not graded_before) or str(sd) > str(os.path.realpath(link)):
        symlink_force(sd, link)

    return True