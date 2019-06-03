from app import app
from flask import render_template, flash, redirect, url_for, abort
from app.forms import RegisterForm, SubmitForm
from app import db
from app.models import Team, Submission
from app.grade import grade
from app.contest import team_dir, sub_dir, grades_dir, ZIP_TIME_FORMAT, SUBMISSIONS_FILE, TEAM_NAME_FILE, TEAM_ID_FILE
import os
from datetime import datetime
import hashlib
import random, string

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
