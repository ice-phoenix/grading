from app import app
from flask import render_template, flash, redirect, url_for
from app.forms import RegisterForm, SubmitForm
from app import db
from app.models import Team, Submission
import os
from datetime import datetime
import hashlib

ORIG_TIME = '2000-01-01 00:00:00.000000'
DB_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
ZIP_TIME_FORMAT = '%Y-%m-%d-%H-%M-%S-%f'

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    # This also checks that the team name is not already taken
    if form.validate_on_submit():
        t_name = form.team_name.data
        t_email = form.email.data
        t_priv = os.urandom(8).hex()    # Generate private ID

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
    form = SubmitForm()
    if form.validate_on_submit():  
        t_priv = form.private_id.data
        t_id = Team.query.filter(Team.private_id==t_priv).first().id

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
        f.save(location)

        h = ''
        with open(location,"rb") as f:
            bytes = f.read()
            h = hashlib.sha256(bytes).hexdigest()

        sb = Submission(team_id=t_id, name=filename, hash=h)
        db.session.add(sb)
        db.session.commit()

        return render_template('submitted.html', filename=filename, hash=h)

    return render_template('submit.html', title='Submit a solution', form=form)