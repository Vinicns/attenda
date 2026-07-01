# app.py — Attenda MVP
# Stack 100% gratuita: Groq (IA) + Edge TTS (voz) + Evolution API (WhatsApp)
# Deploy: Render free tier

import os
import json
import hmac
import hashlib
import asyncio
import tempfile
import subprocess
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify
import edge_tts
import httpx
from groq import Groq

from human_personality import HumanPersonality, EmotionalMemory, Humanizer, build_human_prompt

app = Flask(__name__)

from db_setup import init_db
init_db(app)

# ─── Clientes de API ──────────────────────────────────────────────────────────
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

EVOLUTION_URL   = os.environ.get("EVOLUTION_URL", "")
EVOLUTION_KEY   = os.environ.get("EVOLUTION_API_KEY", "")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")

# ─── Personalidade padrão ─────────────────────────────────────────────────────
DEFAULT_PERSONALITY = HumanPersonality(
    nome="Ana",
    idade_aparente=27,
    cidade="São Paulo",
    extroversao=8,
    amabilidade=9,
    formalidade=0.2,
    uso_emoji=0.6,
    humor_atual="feliz",
    gírias=["show", "massa", "top", "demais"],
)

# ─── Sessões em memória (simples pra MVP) ─────────────────────────────────────
# Em produção: Redis
sessions = {}  # phone -> { history, emotional_memory, message_count }

def get_session(phone):
    if phone not in sessions:
        sessions[phone] = {
            "history": [],
            "emotional_memory": EmotionalMemory(),
            "message_count": 0,
            "personality": DEFAULT_PERSONALITY,
        }
    return sessions[phone]

# ─── Validação de webhook ─────────────────────────────────────────────────────

def validate_webhook(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not WEBHOOK_SECRET:
            return f(*args, **kwargs)
        sig = request.headers.get("x-webhook-secret", "")
        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            request.data,
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# ─── Conhecimento da empresa (RAG simples por enquanto) ───────────────────────
# Em produção: pgvector + embeddings
COMPANY_KNOWLEDGE = os.environ.get("COMPANY_KNOWLEDGE", """
Empresa: Attenda
Produto: Sistema de atendimento com IA para WhatsApp
Preços: Plano Starter R$ 497/mês, Growth R$ 1.497/mês, Enterprise R$ 4.997/mês
Diferenciais: IA humanizada, responde em áudio, aprende com cada conversa
Suporte: seg-sex 9h-18h
""")

# ─── Gerar resposta com Groq (Llama 3 — gratuito) ────────────────────────────

def generate_ai_response(message, session):
    personality = session["personality"]
    emotional_memory = session["emotional_memory"]

    # Análise simples de sentimento
    negative_words = ["problema", "erro", "ruim", "péssimo", "horrível", "demora", "não funciona", "raiva", "absurdo"]
    sentiment = -0.5 if any(w in message.lower() for w in negative_words) else 0.3

    # Detectar intenção simples
    intent = "vendas"
    if any(w in message.lower() for w in ["problema", "reclamação", "erro", "não funciona"]):
        intent = "sac"
    elif any(w in message.lower() for w in ["preço", "valor", "quanto", "custo"]):
        intent = "preco"
    elif any(w in message.lower() for w in ["humano", "pessoa", "atendente", "gerente"]):
        intent = "escalacao"

    # Atualiza memória emocional
    emotional_memory.update(message, sentiment, intent)

    # Constrói prompt humanizado
    system_prompt = build_human_prompt(
        personality=personality,
        emotional_memory=emotional_memory,
        knowledge=COMPANY_KNOWLEDGE,
        message=message,
        conversation_history=session["history"],
    )

    # Chama Groq (Llama 3.3 70B — gratuito)
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            *session["history"][-8:],  # últimas 8 mensagens
            {"role": "user", "content": message},
        ],
        temperature=0.85,   # um pouco de criatividade para soar humano
        max_tokens=300,
        top_p=0.9,
    )

    raw_reply = response.choices[0].message.content.strip()

    # Humaniza a resposta
    humanizer = Humanizer(personality)
    now = datetime.now()
    reply = humanizer.add_human_imperfections(raw_reply)
    reply = humanizer.adapt_to_context(reply, now.hour, now.weekday())

    # Atualiza histórico
    session["history"].append({"role": "user", "content": message})
    session["history"].append({"role": "assistant", "content": reply})
    session["message_count"] += 1

    # Mantém histórico pequeno
    if len(session["history"]) > 20:
        session["history"] = session["history"][-20:]

    return reply, intent, sentiment

# ─── Gerar áudio com Edge TTS ─────────────────────────────────────────────────

def get_voice_profile(intent, sentiment):
    """Escolhe perfil de voz baseado na intenção e sentimento"""
    if intent == "sac" or sentiment < -0.3:
        return {
            "voice": "pt-BR-FranciscaNeural",
            "rate": "-10%",     # mais pausada — empatia
            "pitch": "-2Hz",    # timbre mais grave — seriedade
        }
    elif intent == "preco" or intent == "vendas":
        return {
            "voice": "pt-BR-ThalitaNeural",
            "rate": "+5%",      # leve energia
            "pitch": "+2Hz",    # leve animação
        }
    else:
        return {
            "voice": "pt-BR-ThalitaNeural",
            "rate": "0%",
            "pitch": "0Hz",
        }

def build_ssml(text, profile):
    """Constrói SSML com controle fino de voz"""
    # Adiciona pausas naturais
    text_ssml = text
    text_ssml = text_ssml.replace(", ", ', <break time="150ms"/> ')
    text_ssml = text_ssml.replace("... ", '... <break time="400ms"/> ')
    text_ssml = text_ssml.replace("né? ", 'né? <break time="250ms"/> ')
    text_ssml = text_ssml.replace("tá? ", 'tá? <break time="250ms"/> ')
    text_ssml = text_ssml.replace("sabe? ", 'sabe? <break time="200ms"/> ')

    # Destaca preços
    import re
    text_ssml = re.sub(
        r'R\$\s*(\d+[.,\d]*)',
        r'<emphasis level="moderate"><prosody rate="-15%">R$ \1</prosody></emphasis>',
        text_ssml
    )

    # Remove emojis do texto falado (mas mantém no texto enviado)
    import unicodedata
    text_clean = ''.join(
        c for c in text_ssml
        if unicodedata.category(c) not in ('So', 'Sm')
    )

    return f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
    xmlns:mstts="https://www.w3.org/2001/mstts"
    xml:lang="pt-BR">
  <voice name="{profile['voice']}">
    <mstts:express-as style="friendly" styledegree="1.8">
      <prosody rate="{profile['rate']}" pitch="{profile['pitch']}">
        {text_clean}
      </prosody>
    </mstts:express-as>
  </voice>
</speak>"""

async def text_to_speech_async(text, profile):
    """Gera OGG usando Edge TTS"""
    ssml = build_ssml(text, profile)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
        mp3_path = mp3_file.name

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        ogg_path = ogg_file.name

    try:
        # Gera MP3 com Edge TTS
        communicate = edge_tts.Communicate(ssml, profile["voice"])
        communicate._ssml = True
        await communicate.save(mp3_path)

        # Converte para OGG Opus (formato WhatsApp)
        subprocess.run([
            "ffmpeg", "-i", mp3_path,
            "-c:a", "libopus",
            "-b:a", "32k",
            "-vbr", "on",
            "-y", ogg_path
        ], capture_output=True, timeout=15)

        with open(ogg_path, "rb") as f:
            return f.read()

    finally:
        for p in [mp3_path, ogg_path]:
            try:
                os.unlink(p)
            except:
                pass

def generate_audio(text, intent, sentiment):
    """Wrapper síncrono para o async"""
    profile = get_voice_profile(intent, sentiment)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(text_to_speech_async(text, profile))
    finally:
        loop.close()

# ─── Enviar mensagem WhatsApp ─────────────────────────────────────────────────

def send_whatsapp_text(instance, phone, text):
    with httpx.Client(timeout=10) as client:
        client.post(
            f"{EVOLUTION_URL}/message/sendText/{instance}",
            headers={"apikey": EVOLUTION_KEY, "Content-Type": "application/json"},
            json={"number": phone, "textMessage": {"text": text}},
        )

def send_whatsapp_audio(instance, phone, audio_bytes):
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    with httpx.Client(timeout=15) as client:
        client.post(
            f"{EVOLUTION_URL}/message/sendMedia/{instance}",
            headers={"apikey": EVOLUTION_KEY, "Content-Type": "application/json"},
            json={
                "number": phone,
                "mediatype": "audio",
                "media": f"data:audio/ogg;base64,{audio_b64}",
                "fileName": "resposta.ogg",
            },
        )

# ─── Transcrever áudio recebido ───────────────────────────────────────────────

def transcribe_audio(audio_url):
    """Baixa e transcreve áudio do cliente com Whisper (Groq — grátis)"""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(audio_url)
            audio_bytes = resp.content

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcription = groq_client.audio.transcriptions.create(
                    file=("audio.ogg", audio_file, "audio/ogg"),
                    model="whisper-large-v3",
                    language="pt",
                    response_format="text",
                )
            return transcription.strip()
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        app.logger.error(f"Transcription failed: {e}")
        return None

# ─── Webhook principal ────────────────────────────────────────────────────────

@app.route("/webhook/whatsapp/<instance>", methods=["POST"])
@validate_webhook
def whatsapp_webhook(instance):
    data = request.json or {}

    # Ignora eventos que não são mensagens
    event = data.get("event", "")
    if event not in ("messages.upsert", "message"):
        return jsonify({"ok": True})

    msg_data = data.get("data", {})
    key = msg_data.get("key", {})

    # Ignora mensagens próprias
    if key.get("fromMe"):
        return jsonify({"ok": True})

    phone = key.get("remoteJid", "").replace("@s.whatsapp.net", "")
    if not phone or "@g.us" in key.get("remoteJid", ""):
        return jsonify({"ok": True})  # ignora grupos

    message_obj = msg_data.get("message", {})
    message_text = (
        message_obj.get("conversation") or
        message_obj.get("extendedTextMessage", {}).get("text") or
        ""
    )
    audio_url = message_obj.get("audioMessage", {}).get("url")

    # Responde 200 imediatamente, processa em background
    # (evita timeout do Evolution API)
    import threading
    threading.Thread(
        target=process_message_async,
        args=(instance, phone, message_text, audio_url),
        daemon=True
    ).start()

    return jsonify({"ok": True})

def process_message_async(instance, phone, message_text, audio_url):
    """Processa mensagem em background"""
    try:
        # Se for áudio, transcreve
        if audio_url and not message_text:
            message_text = transcribe_audio(audio_url)
            if not message_text:
                send_whatsapp_text(instance, phone, "Oi! Não consegui ouvir direito, pode repetir? 😊")
                return

        if not message_text or len(message_text.strip()) < 1:
            return

        # Pega ou cria sessão
        session = get_session(phone)

        # Gera resposta da IA
        reply, intent, sentiment = generate_ai_response(message_text, session)

        # Decide: enviar como texto OU como áudio
        # Envia como áudio se:
        # - Cliente mandou áudio, OU
        # - É a primeira mensagem (mais impacto), OU
        # - Empresa configurou sempre áudio
        should_send_audio = (
            audio_url is not None or
            session["message_count"] <= 1 or
            os.environ.get("ALWAYS_AUDIO", "false").lower() == "true"
        )

        if should_send_audio:
            try:
                audio_bytes = generate_audio(reply, intent, sentiment)
                send_whatsapp_audio(instance, phone, audio_bytes)
            except Exception as e:
                app.logger.error(f"Audio generation failed: {e}")
                # Fallback para texto
                send_whatsapp_text(instance, phone, reply)
        else:
            send_whatsapp_text(instance, phone, reply)

    except Exception as e:
        app.logger.error(f"Message processing error: {e}")
        try:
            send_whatsapp_text(instance, phone, "Oi! Tive um probleminha aqui, pode repetir? 😊")
        except:
            pass

# ─── Health check ─────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "voice": "edge-tts",
        "ai": "groq-llama3",
    })

# ─── Configurar empresa via API ───────────────────────────────────────────────

@app.route("/api/configure", methods=["POST"])
def configure():
    """Endpoint para configurar o conhecimento da empresa"""
    # Em produção: autenticação JWT obrigatória
    api_key = request.headers.get("X-API-Key")
    if api_key != os.environ.get("ADMIN_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    knowledge = data.get("knowledge", "")
    agent_name = data.get("agentName", "Ana")
    tone = data.get("tone", "friendly")  # friendly, formal, casual

    # Atualiza personalidade global
    DEFAULT_PERSONALITY.nome = agent_name
    if tone == "formal":
        DEFAULT_PERSONALITY.formalidade = 0.8
        DEFAULT_PERSONALITY.uso_emoji = 0.1
    elif tone == "casual":
        DEFAULT_PERSONALITY.formalidade = 0.1
        DEFAULT_PERSONALITY.uso_emoji = 0.8

    global COMPANY_KNOWLEDGE
    COMPANY_KNOWLEDGE = knowledge

    return jsonify({"ok": True, "agentName": agent_name})

# ─── Start ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# ─── Stats para o Admin Panel ─────────────────────────────────────────────────

@app.route("/stats")
def stats():
    api_key = request.headers.get("X-API-Key")
    if api_key != os.environ.get("ADMIN_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401

    today = datetime.now().date().isoformat()
    total_customers = len(sessions)
    messages_today = sum(
        s["message_count"] for s in sessions.values()
    )

    return jsonify({
        "conversations_today": total_customers,
        "total_customers": total_customers,
        "messages_today": messages_today,
        "status": "online",
        "timestamp": datetime.now().isoformat(),
    })

# ─── Salvar conversa no banco ─────────────────────────────────────────────────

def salvar_conversa(phone, intent, sentiment, message_count):
    try:
        from models import Contato, Conversa
        with app.app_context():
            contato = Contato.query.filter_by(phone=phone).first()
            if not contato:
                contato = Contato(
                    cliente_id=1,
                    phone=phone,
                    termometro=50
                )
                db.session.add(contato)
                db.session.flush()

            termometro = contato.termometro
            if sentiment > 0.3:
                termometro = min(100, termometro + 5)
            elif sentiment < -0.3:
                termometro = max(0, termometro - 10)
            contato.termometro = termometro
            contato.ultima_interacao = datetime.utcnow()

            conversa = Conversa(
                cliente_id=1,
                contato_id=contato.id,
                tipo=intent,
                sentimento=sentiment,
                mensagens=message_count
            )
            db.session.add(conversa)
            db.session.commit()
    except Exception as e:
        app.logger.error(f"Erro ao salvar conversa: {e}")

# ─── Autenticação de Clientes ─────────────────────────────────────────────────

@app.route("/auth/login", methods=["POST"])
def cliente_login():
    from models import Cliente
    from werkzeug.security import check_password_hash
    import jwt
    
    data = request.json or {}
    email = data.get("email", "")
    senha = data.get("senha", "")
    
    cliente = Cliente.query.filter_by(email=email).first()
    if not cliente or not check_password_hash(cliente.senha_hash, senha):
        return jsonify({"error": "Email ou senha incorretos"}), 401
    
    token = jwt.encode({
        "cliente_id": cliente.id,
        "email": cliente.email,
        "exp": datetime.utcnow().timestamp() + 86400
    }, os.environ.get("NEXTAUTH_SECRET", "secret"), algorithm="HS256")
    
    return jsonify({
        "token": token,
        "nome": cliente.nome,
        "segmento": cliente.segmento
    })

@app.route("/auth/me", methods=["GET"])
def cliente_me():
    from models import Cliente
    import jwt
    
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, os.environ.get("NEXTAUTH_SECRET", "secret"), algorithms=["HS256"])
        cliente = Cliente.query.get(payload["cliente_id"])
        if not cliente:
            return jsonify({"error": "Cliente não encontrado"}), 404
        return jsonify({
            "id": cliente.id,
            "nome": cliente.nome,
            "email": cliente.email,
            "segmento": cliente.segmento
        })
    except:
        return jsonify({"error": "Token inválido"}), 401

# ─── Stats do Cliente ─────────────────────────────────────────────────────────

@app.route("/cliente/stats", methods=["GET"])
def cliente_stats():
    from models import Cliente, Contato, Conversa
    import jwt

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, os.environ.get("NEXTAUTH_SECRET", "secret"), algorithms=["HS256"])
        cliente_id = payload["cliente_id"]
    except:
        return jsonify({"error": "Token inválido"}), 401

    contatos = Contato.query.filter_by(cliente_id=cliente_id).all()
    conversas = Conversa.query.filter_by(cliente_id=cliente_id).all()

    hoje = datetime.utcnow().date()
    mensagens_hoje = sum(
        c.mensagens for c in conversas
        if c.atualizada_em and c.atualizada_em.date() == hoje
    )

    termometro_medio = 0
    if contatos:
        termometro_medio = int(sum(c.termometro for c in contatos) / len(contatos))

    por_tipo = {"vendas": 0, "sac": 0, "outro": 0}
    for c in conversas:
        if c.tipo == "vendas" or c.tipo == "preco":
            por_tipo["vendas"] += 1
        elif c.tipo == "sac":
            por_tipo["sac"] += 1
        else:
            por_tipo["outro"] += 1

    contatos_list = [{
        "phone": c.phone,
        "termometro": c.termometro,
        "ultima_interacao": c.ultima_interacao.isoformat() if c.ultima_interacao else ""
    } for c in sorted(contatos, key=lambda x: x.ultima_interacao or datetime.min, reverse=True)[:10]]

    return jsonify({
        "total_conversas": len(conversas),
        "mensagens_hoje": mensagens_hoje,
        "termometro_medio": termometro_medio,
        "por_tipo": por_tipo,
        "contatos": contatos_list
    })

# ─── Admin: Gerenciar Clientes ────────────────────────────────────────────────

@app.route("/admin/clientes", methods=["GET"])
def listar_clientes():
    api_key = request.headers.get("X-API-Key")
    if api_key != os.environ.get("ADMIN_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401

    from models import Cliente
    clientes = Cliente.query.all()
    return jsonify({"clientes": [{
        "id": c.id,
        "nome": c.nome,
        "email": c.email,
        "segmento": c.segmento,
        "criado_em": c.criado_em.isoformat() if c.criado_em else ""
    } for c in clientes]})

@app.route("/admin/clientes", methods=["POST"])
def criar_cliente():
    api_key = request.headers.get("X-API-Key")
    if api_key != os.environ.get("ADMIN_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401

    from models import Cliente
    from werkzeug.security import generate_password_hash
    data = request.json or {}
    
    if Cliente.query.filter_by(email=data.get("email")).first():
        return jsonify({"error": "Email já cadastrado"}), 400

    c = Cliente(
        nome=data.get("nome", ""),
        email=data.get("email", ""),
        senha_hash=generate_password_hash(data.get("senha", "")),
        segmento=data.get("segmento", "geral")
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "cliente": {
        "id": c.id,
        "nome": c.nome,
        "email": c.email,
        "segmento": c.segmento,
        "criado_em": c.criado_em.isoformat() if c.criado_em else ""
    }}), 201
