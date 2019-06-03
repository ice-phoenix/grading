from app import app
from flask import render_template, flash, request, redirect, url_for, abort, jsonify
from app.forms import RegisterForm, SubmitForm, LambdaSubmitForm
from app import db
from app.models import Team, Submission, Block, BlockSubmission
from app.grade import grade
from app.contest import team_dir, sub_dir, grades_dir, block_sub_dir,\
    ZIP_TIME_FORMAT, SUBMISSIONS_FILE, TEAM_NAME_FILE, TEAM_ID_FILE,\
    BLOCK_WAIT_FOR_SECS, BLOCK_WAIT_FOR_SUBS, BLOCK_SOL_FILE, BLOCK_NEXT_PUZZLE_FILE
import os
from datetime import datetime
import hashlib
import random, string
from sqlalchemy import and_
from multiprocessing import Lock
import subprocess

ORIG_TIME = '2000-01-01 00:00:00.000000'
DB_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'

# MAIN CONTEST

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    # This also checks that the team name is not already taken
    if form.validate_on_submit():
        t_name = form.team_name.data
        t_email = form.email.data
        t_priv = os.urandom(app.config['PRIV_ID_LEN']).hex()    # Generate private ID

        t = Team(name=t_name, email=t_email, private_id=t_priv)
        db.session.add(t)
        
        try:
            db.session.commit()
            t_id = Team.query.filter(Team.name==t_name).first().id

            flash('Team {} with email {} is now registered.'.format(form.team_name.data, form.email.data))
            flash('You are team number {}.'.format(t_id))
            flash('Your private ID (write this down!) is {}.'.format(t_priv))
            return redirect(url_for('registered'))
        except:
            flash('There was a database error at time {}'.format(datetime.utcnow()))
            flash('Your registration did not go through! Please try again shortly.')
            flash('If this keeps happening, contact the contest organisers.')

    return render_template('register.html', title='Register your team', form=form)

@app.route('/registered')
def registered():
    return render_template('registered.html', title='Successfuly registered!')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    form = SubmitForm(meta={'csrf': False})
    if form.validate_on_submit():  
        t_priv = form.private_id.data
        team = Team.query.filter(Team.private_id==t_priv).first()
        t_id = team.id
        t_name = team.name

        # Find previous submission time (if exists)
        prev_sub = Submission.query.filter(Submission.team_id==t_id).order_by(Submission.sub_time.desc()).first()
        prev_time = datetime.strptime(ORIG_TIME, DB_TIME_FORMAT)
        if prev_sub:
            prev_time = prev_sub.sub_time

        # Rate limit submissions
        now = datetime.utcnow()
        if app.config['SUBMIT_DELAY']:
            diff = (now - prev_time).total_seconds()
            if diff < app.config['SUBMIT_DELAY']:
                return render_template('rate-limit.html', time_diff=diff, sub_delay=app.config['SUBMIT_DELAY'])

        f = form.file.data
        now_str = now.strftime(ZIP_TIME_FORMAT)

        filename = 'team_{}_{}.zip'.format(t_id, now_str)
        location = os.path.join(app.config['SUBMIT_DIR'], filename)
        os.makedirs(os.path.dirname(location), exist_ok=True)
        f.save(location)

        h = ''
        with open(location,"rb") as f:
            bytes = f.read()
            h = hashlib.sha256(bytes).hexdigest()

        # Schedule for grading
        num_coins = 0
        # TODO: this will just timeout if the broker is offline
        grade.delay(t_id, t_priv, t_name, now_str, filename, h, num_coins)

        # Register submission in database
        sb = Submission(team_id=t_id, name=filename, hash=h, sub_time=now)
        db.session.add(sb)
        db.session.commit()

        # Acknowledge submission to team
        gd = grades_dir(t_priv)
        os.makedirs(gd, exist_ok=True)

        sf = os.path.join(gd, SUBMISSIONS_FILE)
        with open(sf, 'a+') as f:
            f.write('{} -> {}\n'.format(now_str, h))

        # Create team identifiers in case they don't exist
        nf = os.path.join(gd, TEAM_NAME_FILE)
        with open(nf, 'w') as f:
            f.write('{}\n'.format(t_name))

        idf = os.path.join(gd, TEAM_ID_FILE)
        with open(idf, 'w') as f:
            f.write('{}\n'.format(t_id))

        team_folder = '/grades/{}/'.format(t_priv)

        return render_template('submitted.html', filename=filename, hash=h, team_folder=team_folder)

    return render_template('submit.html', title='Submit a solution', form=form)

# BLOCKCHAIN

blockchain_lock = Lock()

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

    return len(errors) == 0, block, errors

def lambda_init_if_needed():
    # Creates the database record for the first block if it doesn't exist
    block = Block.query.order_by(Block.id.desc()).first()
    if block is None:
        block = Block()
        db.session.add(block)
        db.session.commit()

    return block

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

@app.route('/lambda/submit', methods=['POST'])
def lambda_submit():
    form = LambdaSubmitForm(meta={'csrf': False})

    if form.validate_on_submit():
        t_priv = form.private_id.data
        team = Team.query.filter(Team.private_id==t_priv).first()
        t_id = team.id
        t_name = team.name

        # We need to lock to ensure only one submission is processed at a time,
        # since the block might become full/complete.
        with blockchain_lock:
            lambda_init_if_needed()
            accept_sub, block, errors = decide_accept_sub(t_id, form)
            if not accept_sub:
                return jsonify({'errors': errors}), 400

            block_num = block.id

            # Can now accept submission
            dir = block_sub_dir(t_id, block_num)
            os.makedirs(dir, exist_ok=True)
            sol_path = os.path.join(dir, BLOCK_SOL_FILE)
            puzzle_path = os.path.join(dir, BLOCK_NEXT_PUZZLE_FILE)

            # Save to disk
            form.solution.data.save(sol_path)
            form.puzzle.data.save(puzzle_path)

            # Register in database
            sb = BlockSubmission(block_num=block_num, team_id=t_id)
            db.session.add(sb)
            db.session.commit()

            process_block()

            sub = {'block_num': block_num, 'team_id': t_id, 'sub_id': sb.id}
            return jsonify({'success': sub})

    # Report form errors
    else:
        errors = {
            'private_id': form.private_id.errors,
            'block_num': form.block_num.errors,
            'solution': form.solution.errors,
            'puzzle': form.puzzle.errors
        }

        return jsonify({'errors': errors}), 400

# This needs to be called externally!
@app.route('/notify/block_timer')
def block_timer():
    with blockchain_lock:
        lambda_init_if_needed()
        process_block()
    return 'OK'

@ app.route('/notify/block_created', methods=['POST'])
def block_created():
    data = request.form

    # Only accept notification if secret key is present
    if data['secret'] != app.config['NOTIFY_SECRET_KEY']:
        abort(403)

    with blockchain_lock:
        lambda_init_if_needed()

        block_num = data['block']
        block = Block()
        db.session.add(block)
        db.session.commit()

        # Something really dodgy is going on if this isn't the case
        app.logger.info("block_num  = {} | block.id = {}".format(block_num, block.id))

        return 'ACK block {}'.format(block.id)


# TODO: remove
# TESTING
@app.route('/testing/register/<int:n>')
def register_many(n):
    ids = []

    for i in range(n):
        t_name = 'test_' + ''.join([random.choice(string.ascii_letters) for n in range(12)])
        t_email = '{}@example.com'.format(t_name)
        t_priv = os.urandom(app.config['PRIV_ID_LEN']).hex()    # Generate private ID

        ids.append(t_priv)

        t = Team(name=t_name, email=t_email, private_id=t_priv)
        db.session.add(t)

    db.session.commit()
    return '\n'.join(ids)
