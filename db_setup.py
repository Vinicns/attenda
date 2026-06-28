import os
from models import db

def init_db(app):
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+pg8000://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
