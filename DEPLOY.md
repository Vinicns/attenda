# GUIA DE DEPLOY — ATTENDA MVP
# Stack gratuita: Groq + Edge TTS + Evolution API + Render

---

## PASSO 1 — Pegar chave do Groq (2 minutos)

1. Acesse: https://console.groq.com
2. Crie uma conta (gratuita)
3. Vá em "API Keys" → "Create API Key"
4. Copie a chave (começa com `gsk_...`)

---

## PASSO 2 — Subir código no GitHub

No terminal do seu celular (Termux):

```bash
cd ~/downloads/attenda
git init
git add .
git commit -m "primeiro commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/attenda.git
git push -u origin main
```

(Precisa criar o repositório em https://github.com/new primeiro)

---

## PASSO 3 — Deploy no Render (gratuito)

1. Acesse: https://render.com
2. "New" → "Web Service"
3. Conecte seu GitHub e selecione o repositório `attenda`
4. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --workers 1 --timeout 120 --bind 0.0.0.0:$PORT`
   - **Plan:** Free

5. Em "Environment Variables", adicione:
   ```
   GROQ_API_KEY = sua-chave-do-groq
   EVOLUTION_URL = https://sua-evolution-api.com
   EVOLUTION_API_KEY = sua-chave-evolution
   WEBHOOK_SECRET = qualquer-string-aleatoria
   ADMIN_API_KEY = outra-string-aleatoria
   COMPANY_KNOWLEDGE = (descrição da empresa do cliente)
   ```

6. Clique "Create Web Service"
7. Aguarda ~3 minutos para subir

Sua URL será algo como: `https://attenda-xxxx.onrender.com`

---

## PASSO 4 — Instalar ffmpeg no Render

No `render.yaml` já está configurado.
Se der erro, adicione no Build Command:
```
apt-get install -y ffmpeg && pip install -r requirements.txt
```

---

## PASSO 5 — Configurar Evolution API

No painel da sua Evolution API:
1. Crie uma instância WhatsApp
2. Em "Webhook", coloque:
   - URL: `https://attenda-xxxx.onrender.com/webhook/whatsapp/NOME_DA_INSTANCIA`
   - Header: `x-webhook-secret: seu-webhook-secret`
   - Eventos: `MESSAGES_UPSERT`

---

## PASSO 6 — Cadastrar conhecimento da empresa

Faça um POST para configurar a empresa:

```bash
curl -X POST https://attenda-xxxx.onrender.com/api/configure \
  -H "Content-Type: application/json" \
  -H "X-API-Key: seu-admin-api-key" \
  -d '{
    "agentName": "Ana",
    "tone": "friendly",
    "knowledge": "Empresa: Loja ABC\nProdutos: Camisetas R$ 89, Calças R$ 149\nFrete: grátis acima R$ 200\nHorário: seg-sex 9h-18h\nGarantia: 30 dias"
  }'
```

---

## PASSO 7 — Testar

1. Abra o WhatsApp
2. Mande uma mensagem para o número conectado na Evolution API
3. A IA deve responder em texto ou áudio

Para testar o health check:
```
https://attenda-xxxx.onrender.com/health
```

---

## VOZES DISPONÍVEIS

| Voz | Estilo | Melhor para |
|-----|--------|-------------|
| pt-BR-ThalitaNeural | Jovem, animada | Vendas, informal |
| pt-BR-FranciscaNeural | Natural, suave | SAC, formal |
| pt-BR-AntonioNeural | Masculina | B2B, formal |

---

## CUSTOS

| Serviço | Custo |
|---------|-------|
| Groq (Llama 3.3) | GRÁTIS |
| Edge TTS (voz) | GRÁTIS |
| Render (hospedagem) | GRÁTIS |
| ffmpeg (conversão) | GRÁTIS |
| **TOTAL** | **R$ 0** |

---

## QUANDO MONETIZAR (primeiro cliente pago)

Upgrade para:
- ElevenLabs → voz ainda mais natural (R$ ~22/mês)
- Render pago → sem sleep em inatividade (R$ ~25/mês)
- PostgreSQL → histórico persistente (grátis no Supabase)
