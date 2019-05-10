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