from app import db
from datetime import datetime

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text(), index=True, unique=True)
    email = db.Column(db.Text(), index=True, unique=True)
    private_id = db.Column(db.Text(), index=True, unique=True)
    reg_time = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    def __repr__(self):
        return '<Team #{}: {} | ({}) | (privID {})>'.format(self.id, self.name, self.email, self.private_id)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, index=True)
    name = db.Column(db.Text(), index=True, unique=True)
    hash = db.Column(db.Text(), index=True)
    sub_time = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    def __repr__(self):
        return '<Submission {} from team {} at time {}>'.format(self.hash, self.team_id, self.sub_time)



