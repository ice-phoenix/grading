from app import app, celery
from celery.utils.log import get_task_logger
from app.contest import team_dir, sub_dir
import random
import time
import os, tempfile
from zipfile import ZipFile
import subprocess

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
@celery.task(acks_late=True)
def grade(t_id, t_name, ts, filename, hash, coins):
    location = os.path.join(app.config['SUBMIT_DIR'], filename)

    logger.info(f'Processing {hash}')
    logger.info(f'Extracting archive {location}')

    td = team_dir(t_id)
    os.makedirs(td, exist_ok=True)

    # Create the name file if it doesn't exist
    nf = os.path.join(td, 'name')
    if not os.path.exists(nf):
        with open(nf, 'w') as f:
            f.write(t_name)

    # Extract submission in the appropriate directory
    sd = sub_dir(t_id, ts)
    os.makedirs(sd, exist_ok=True)
    os.chdir(sd)
    with ZipFile(location) as zip:
        zip.extractall()

    hf = os.path.join(sd, 'hash')
    with open(hf, 'w') as f:
        f.write(hash)

    logger.info(f'Running checker on {str(sd)}')
    chk = app.config['CHECKER_PATH']
    pd = app.config['PROBLEM_DIR']
    rf = os.path.join(sd, 'score.csv')

    # Call checker
    os.chdir(app.config['ROOT_DIR'])
    # We use this rather than subprocess.call() to ensure the checker process is
    # killed when the Celery worker is killed
    process = subprocess.Popen([chk, 'team', '-p', pd, '-s', sd, '-o', rf],
	                                      stdout=subprocess.PIPE,
	                                      stderr=subprocess.STDOUT)
    _ = process.communicate()[0]
    _ = process.wait()

    link = os.path.join(td, 'latest-graded')
    graded_before = os.path.exists(link)

    os.chdir(td)
    # Only update 'latest-graded' if first time or we're grading a newer submission
    if (not graded_before) or str(sd) > str(os.path.realpath(link)):
        symlink_force(sd, link)

    return True