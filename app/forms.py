from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError
from app import db
from app.models import Team

def name_unique(form, field):
    name = field.data
    q = db.session.query(Team).filter(Team.name == name)
    already_exists = db.session.query(q.exists()).scalar()
    if already_exists:
        raise ValidationError('Name {} is already taken! Choose another.'.format(name))

def email_unique(form, field):
    email = field.data
    q = db.session.query(Team).filter(Team.email == email)
    already_exists = db.session.query(q.exists()).scalar()
    if already_exists:
        raise ValidationError('Email {} has already been used. If you think this is an error, contact the organisers.'.format(email))

def no_redundant_spaces(form, field):
    if field.data != field.data.strip():
        raise ValidationError('Please remove leading/trailing whitespace.')

class RegisterForm(FlaskForm):
    team_name = StringField('Team Name', validators=[DataRequired(message=u'You must enter a team name.'), name_unique, no_redundant_spaces])
    email = StringField('Email', validators=[Email(message=u'That\'s not a valid email address.'), email_unique])
    submit = SubmitField('Register')