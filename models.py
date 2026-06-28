from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Cliente(db.Model):
    __tablename__ = "clientes"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    segmento = db.Column(db.String(50), default="geral")
    conhecimento = db.Column(db.Text, default="")
    agente_nome = db.Column(db.String(50), default="Ana")
    tom = db.Column(db.String(20), default="friendly")
    instancia_whatsapp = db.Column(db.String(100), default="")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    conversas = db.relationship("Conversa", backref="cliente", lazy=True)

class Contato(db.Model):
    __tablename__ = "contatos"
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    nome = db.Column(db.String(100), default="")
    termometro = db.Column(db.Integer, default=50)
    ultima_interacao = db.Column(db.DateTime, default=datetime.utcnow)
    conversas = db.relationship("Conversa", backref="contato", lazy=True)

class Conversa(db.Model):
    __tablename__ = "conversas"
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    contato_id = db.Column(db.Integer, db.ForeignKey("contatos.id"), nullable=False)
    tipo = db.Column(db.String(20), default="outro")
    sentimento = db.Column(db.Float, default=0.0)
    mensagens = db.Column(db.Integer, default=0)
    resumo = db.Column(db.Text, default="")
    iniciada_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizada_em = db.Column(db.DateTime, default=datetime.utcnow)
