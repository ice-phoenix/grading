from app import app
from flask import render_template, flash, request, redirect, url_for, abort, jsonify
from app.forms import RegisterForm, SubmitForm, LambdaSubmitForm, PrivForm, ProfileForm
from app import db
from app.models import Team, Submission, Block, BlockSubmission
from app.grade import grade
from app.contest import team_dir, sub_dir, grades_dir, block_dir, block_sub_dir, profile_dir,\
    ZIP_TIME_FORMAT, SUBMISSIONS_FILE, TEAM_NAME_FILE, TEAM_ID_FILE,\
    PROFILE_FILE, PROFILE_ZIP, PROFILE_HASH,\
    BLOCK_SOL_FILE, BLOCK_WINNER_FILE, BLOCK_NEXT_PUZZLE_FILE, BLOCK_PROBLEM_DESC, BLOCK_CONDITIONS_FILE
from app.blockchain import *
import os
from datetime import datetime
import hashlib
import json
import random, string
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

@app.route('/profile/', methods=['GET', 'POST'])
def login():
    form = PrivForm()
    if form.validate_on_submit():
        return redirect(url_for('profile', priv_id=form.private_id.data))
    return render_template('priv.html', title='Enter your private ID', form=form)

def save_profile(t_id, form, zip_hash):
    dir = profile_dir(t_id)
    os.makedirs(dir, exist_ok=True)

    pp = os.path.join(dir, PROFILE_FILE)
    fields = {
        'id': t_id,
        'name': form.team_name.data,
        'email': form.email.data,
        'members': form.members.data,
        'countries': form.countries.data,
        'langs': form.langs.data,
        'comments': form.comments.data,
        'zip_hash': zip_hash
    }

    if form.file.data is not None:
        # Save ZIP
        zp = os.path.join(dir, PROFILE_ZIP)
        form.file.data.save(zp)

        # Compute hash
        h = ''
        with open(zp,"rb") as f:
            bytes = f.read()
            h = hashlib.sha256(bytes).hexdigest()

        fields['zip_hash'] = h

    with open(pp, 'w') as f:
        json.dump(fields, f)

def read_profile(t_id):
    pp = os.path.join(profile_dir(t_id), PROFILE_FILE)
    fields = {}
    if os.path.exists(pp):
        with open(pp, 'r') as f:
            fields = json.load(f)
    return fields

@app.route('/profile/<priv_id>', methods=['GET', 'POST'])
def profile(priv_id):
    t = Team.query.filter(Team.private_id==priv_id).first()
    if t is None:
        return redirect(url_for('login'))

    saved = read_profile(t.id)
    # Fill in pre-existing details
    zip_hash = saved.get('zip_hash')
    t_m = saved.get('members', '')
    t_co = saved.get('countries', '')
    t_l = saved.get('langs', '')
    t_cc = saved.get('comments', '')

    form = ProfileForm(team_name=t.name, email=t.email, members=t_m, countries=t_co, langs=t_l, comments=t_cc)

    if form.validate_on_submit():
        n_name = form.team_name.data
        n_email = form.email.data

        # Is this a name change?
        if t.name != n_name:
            # Ensure the new name is not already taken
            q = db.session.query(Team).filter(Team.name == n_name)
            ex = db.session.query(q.exists()).scalar()
            if ex:
                flash('Chosen team name {} is already taken! Please choose another.'.format(n_name))
                return render_template('profile.html', title='Update your profile', form=form, zip_hash=zip_hash)

        # Is this an email change?
        if t.email != n_email:
            # Ensure the new name is not already taken
            q = db.session.query(Team).filter(Team.email == n_email)
            ex = db.session.query(q.exists()).scalar()
            if ex:
                flash('Email {} is already taken! Please choose another.'.format(n_email))
                return render_template('profile.html', title='Update your profile', form=form, zip_hash=zip_hash)

        # Update name and email in database
        t.name = n_name
        t.email = n_email
        db.session.commit()

        # Save profile and ZIP on disk
        save_profile(t.id, form, zip_hash)
        return redirect(url_for('profile', priv_id=priv_id))

    return render_template('profile.html', title='Update your profile', form=form, zip_hash=zip_hash)

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
        num_coins = get_balance(t_id)
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

@app.route('/lambda/getblockchaininfo')
def getblockchaininfo():
    block = get_current_block()
    ts = block.created.timestamp()
    subs = BlockSubmission.query.filter(BlockSubmission.block_num==block.id).count()
    total = db.session.query(BlockSubmission).count()

    info = {
        'chain': 'lambda',
        'block': block.id,
        'block_ts': ts,
        'block_subs': subs,
        'total_subs': total,
    }
    return jsonify(info)

@app.route('/lambda/getbalance/<t_id>')
def getbalance(t_id):
    return jsonify(get_balance(t_id))

@app.route('/lambda/getbalances')
def getbalances():
    return jsonify(get_balances())

@app.route('/lambda/getmininginfo')
def getmininginfo():
    block = get_current_block()
    excluded = get_excluded(block.id)
    puzzle = None
    conditions = None

    bd = block_dir(block.id)
    pp = os.path.join(bd, BLOCK_PROBLEM_DESC)
    cp = os.path.join(bd, BLOCK_CONDITIONS_FILE)
    with open(pp, 'r') as f:
        puzzle = f.read().rstrip()
    with open(cp, 'r') as f:
        conditions = f.read().rstrip()

    info = {
        'block': block.id,
        'excluded': excluded,
        'puzzle': puzzle,
        'conditions': conditions
    }
    return jsonify(info)

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
