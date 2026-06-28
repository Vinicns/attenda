import os
from flask import Flask
from models import db, Cliente, Contato, Conversa
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

with app.app_context():
    db.create_all()
    print("Tabelas criadas com sucesso!")
    
    # Cria admin padrão se não existir
    if not Cliente.query.filter_by(email="admin@attenda.app").first():
        admin = Cliente(
            nome="Admin",
            email="admin@attenda.app",
            senha_hash=generate_password_hash("Attenda@2026"),
            segmento="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin criado!")
