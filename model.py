from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Router(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    community_string = db.Column(db.String(50), nullable=False)

class Interface(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    router_id = db.Column(db.Integer, db.ForeignKey('router.id'), nullable=False)
    ip_address = db.Column(db.String(15), nullable=False)
    router = db.relationship('Router', backref=db.backref('interfaces', lazy=True))
