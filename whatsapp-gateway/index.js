// Microservicio gateway WhatsApp -> Django
// - Conexión usando @whiskeysockets/baileys (Multi-Device)
// - Persiste credenciales en ./auth_info para evitar re-scan del QR
// - Muestra QR en terminal y expone endpoint GET /qr para que Django lo pida
// - Reenvía mensajes entrantes al webhook de Django
// - Expone endpoint POST /send para enviar mensajes desde Django

import express from 'express';
import axios from 'axios';
import qrcode from 'qrcode-terminal';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion } from '@whiskeysockets/baileys';

// Ruta absoluta de credenciales (en cPanel/Passenger el cwd puede no ser la carpeta del proyecto)
const __dirname_gw = path.dirname(fileURLToPath(import.meta.url));
const AUTH_ROOT = path.join(__dirname_gw, 'auth_info');

const PORT = process.env.PORT || 3000;
const IS_PROD_ENV = process.env.NODE_ENV === 'production' || Boolean(process.env.PASSENGER_APP_ENV) || Boolean(process.env.PASSENGER_BASE_URI);
const DEFAULT_WEBHOOK = IS_PROD_ENV
  ? 'https://os.raudie.net/ia/webhook/whatsapp/'
  : 'http://127.0.0.1:8000/ia/webhook/whatsapp/';
const PRIMARY_WEBHOOK = process.env.DJANGO_WEBHOOK || DEFAULT_WEBHOOK;
const FALLBACK_WEBHOOKS = [
  PRIMARY_WEBHOOK,
  'https://os.raudie.net/ia/webhook/whatsapp/',
  'http://os.raudie.net/ia/webhook/whatsapp/',
  'http://127.0.0.1:8000/ia/webhook/whatsapp/',
  'http://127.0.0.1:5555/ia/webhook/whatsapp/'
];

// Mapas por sesión (clave: userId)
const sockets = new Map();
const latestQrs = new Map();
const statuses = new Map();
const backoffMap = new Map();
// Registro de IDs de mensajes enviados por el propio bot/sistema para evitar bucles infinitos
const sentByBotIds = new Set();

function rememberBotMessageId(sentMsg) {
  const msgId = sentMsg?.key?.id;
  if (msgId) {
    sentByBotIds.add(msgId);
    // Limpiar después de 5 minutos para no crecer en memoria
    setTimeout(() => sentByBotIds.delete(msgId), 5 * 60 * 1000);
  }
}

function sessionId(user, slot) {
  const s = slot === undefined || slot === null ? '0' : String(slot);
  const u = user === undefined || user === null ? 'default' : String(user);
  return `${u}_${s}`;
}

function normalizeBareJid(jid) {
  if (!jid) return '';
  return String(jid).split('@')[0].split(':')[0];
}

// Extrae texto del mensaje en los distintos tipos soportados (incluyendo chats con mensajes temporales)
function extractMessageText(message) {
  if (!message) return '';
  const inner =
    message.ephemeralMessage?.message ||
    message.viewOnceMessage?.message ||
    message.viewOnceMessageV2?.message ||
    message.documentWithCaptionMessage?.message ||
    message;

  // Ignorar mensajes internos de protocolo, reacciones o sincronización de historial
  if (
    inner.protocolMessage ||
    inner.senderKeyDistributionMessage ||
    inner.reactionMessage ||
    inner.keepInChatMessage ||
    inner.pollUpdateMessage
  ) {
    return '';
  }

  if (inner.conversation) return inner.conversation;
  if (inner.extendedTextMessage && inner.extendedTextMessage.text) return inner.extendedTextMessage.text;
  if (inner.imageMessage && inner.imageMessage.caption) return inner.imageMessage.caption;
  if (inner.videoMessage && inner.videoMessage.caption) return inner.videoMessage.caption;
  if (inner.buttonsResponseMessage && inner.buttonsResponseMessage.selectedButtonId) return inner.buttonsResponseMessage.selectedButtonId;
  if (inner.templateButtonReplyMessage && inner.templateButtonReplyMessage.selectedId) return inner.templateButtonReplyMessage.selectedId;
  if (inner.listResponseMessage?.singleSelectReply?.selectedRowId) return inner.listResponseMessage.singleSelectReply.selectedRowId;
  return '';
}

async function postToDjangoWebhook(payload) {
  const uniqueUrls = [...new Set(FALLBACK_WEBHOOKS)];
  let lastErr = null;
  for (const url of uniqueUrls) {
    try {
      const resp = await axios.post(url, payload, {
        headers: {
          'Content-Type': 'application/json',
          'X-Webhook-Secret': process.env.WEBHOOK_SECRET || 'pon-aqui-un-token-largo-y-aleatorio-32chars'
        },
        timeout: 25000
      });
      return resp;
    } catch (err) {
      lastErr = err;
      // Si es error de conexión rechazada (puerto distinto), probar el siguiente puerto
      if (['ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'ENOTFOUND', 'EAI_AGAIN', 'ECONNABORTED'].includes(err.code) || (err.response && err.response.status >= 404)) {
        continue;
      }
      throw err;
    }
  }
  throw lastErr;
}

async function resolveWhatsAppJid(sock, rawNumberOrJid) {
  const input = String(rawNumberOrJid || '').trim();
  if (!input) return '';
  if (input.includes('@')) {
    return input;
  }
  const cleanDigits = input.replace(/\D/g, '');
  if (!cleanDigits) return '';
  const candidateJid = `${cleanDigits}@s.whatsapp.net`;
  try {
    if (typeof sock.onWhatsApp === 'function') {
      const results = await sock.onWhatsApp(candidateJid);
      if (Array.isArray(results) && results[0]?.exists && results[0]?.jid) {
        return results[0].jid;
      }
    }
  } catch (e) {
    // Continuar con candidateJid
  }
  return candidateJid;
}

// Inicia el socket de Baileys con persistencia en ./auth_info
async function startSocketFor(sid = 'default_0') {
  try {
    const dir = path.join(AUTH_ROOT, sid);
    const { state, saveCreds } = await useMultiFileAuthState(dir);
    const { version } = await fetchLatestBaileysVersion();
    const existing = sockets.get(sid);
    if (existing) {
      try {
        if (existing?.ws && typeof existing.ws.close === 'function') existing.ws.close();
      } catch (e) {
        try { existing?.ev?.removeAllListeners && existing.ev.removeAllListeners(); } catch (e2) {}
      }
      sockets.delete(sid);
    }

    // initialize socket for this session id
    const sock = makeWASocket({ auth: state, version });
    sockets.set(sid, sock);
    latestQrs.set(sid, null);
    statuses.set(sid, 'initializing');

    // Guarda credenciales cuando se actualizan
    sock.ev.on('creds.update', saveCreds);

    // Manejo de eventos de conexión y QR
    sock.ev.on('connection.update', (update) => {
      const { connection, qr, lastDisconnect } = update;

      if (qr) {
        latestQrs.set(sid, qr);
        qrcode.generate(qr, { small: true });
      }

      if (connection === 'open') {
        latestQrs.set(sid, null); // autenticado, no hay QR activo
        statuses.set(sid, 'connected');
        backoffMap.set(sid, 0);
        console.log(`Conexión abierta con WhatsApp (session=${sid})`);
      }

      if (connection === 'close') {
        statuses.set(sid, 'disconnected');
        let isIntentional = false;
        try {
          const err = lastDisconnect?.error;
          if (err && typeof err === 'object') {
            if (err.output && err.output.statusCode === 401) isIntentional = true;
            if (String(err.message || err).toLowerCase().includes('intentional logout')) isIntentional = true;
          } else if (String(lastDisconnect).toLowerCase().includes('intentional logout')) {
            isIntentional = true;
          }
        } catch (e) { /* ignore */ }

        if (isIntentional) {
          console.error(`Intentional Logout detectado para session=${sid} — marcando como 'unlinked' y no reconectando automáticamente.`);
          statuses.set(sid, 'unlinked');
          latestQrs.delete(sid);
          try { sockets.get(sid)?.ev?.removeAllListeners && sockets.get(sid).ev.removeAllListeners(); } catch(e){}
          sockets.delete(sid);
          return;
        }

        console.error(`Conexión cerrada para session=${sid}, intentando reconectar...`, lastDisconnect?.error || 'sin error');
        const prev = backoffMap.get(sid) || 0;
        const attempts = Math.min(prev + 1, 6);
        backoffMap.set(sid, attempts);
        const delay = Math.min(30000, 1000 * Math.pow(2, attempts));
        setTimeout(() => {
          startSocketFor(sid).catch(err => console.error('Error reconectando:', err));
        }, delay);
      }
    });

    // Escucha mensajes entrantes, los reenvía al webhook de Django y responde al usuario
    sock.ev.on('messages.upsert', async (m) => {
      try {
        // Ignorar volcados antiguos de historial al reconectar
        if (m.type && m.type !== 'notify') return;

        const messages = m.messages || [];
        for (const msg of messages) {
          if (!msg.message) continue;
          if (msg.key?.id && sentByBotIds.has(msg.key.id)) continue;

          const remoteJid = msg.key?.remoteJid || '';
          if (!remoteJid || remoteJid.endsWith('@g.us') || remoteJid === 'status@broadcast') continue;

          // Si el mensaje fue enviado desde este mismo teléfono (fromMe: true),
          // solo permitir si el usuario se está escribiendo a su propio chat ("Tú") para probar el bot.
          if (msg.key?.fromMe) {
            const myPhone = normalizeBareJid(sock.user?.id);
            const myLid = normalizeBareJid(sock.user?.lid);
            const targetBare = normalizeBareJid(remoteJid);
            const isSelfChat = (myPhone && targetBare === myPhone) || (myLid && targetBare === myLid);
            if (!isSelfChat) continue;
          }

          const messageText = extractMessageText(msg.message);
          if (!messageText || !messageText.trim()) continue;

          const pushName = msg.pushName || msg.contact?.name || '';
          const senderPn = msg.key?.senderPn || msg.key?.participant || remoteJid;

          console.log(`\n[RECIBIDO] Mensaje de ${remoteJid} (${pushName}): ${messageText}`);

          // Enviar al webhook de Django y reenviar la respuesta al usuario
          try {
            const owner = String(sid).split('_')[0];
            const resp = await postToDjangoWebhook({
              remoteJid,
              senderPn,
              pushName,
              messageText,
              session: sid,
              owner
            });

            console.log(`[WEBHOOK] Django respondió con HTTP ${resp.status}`);
            console.log(`[WEBHOOK] Datos recibidos:`, resp.data);

            if (resp && resp.data && resp.data.reply && resp.data.reply.trim() !== '') {
              console.log(`[ENVIANDO] Respondiendo a ${remoteJid}: ${resp.data.reply}`);
              const sentMsg = await sock.sendMessage(remoteJid, { text: resp.data.reply });
              rememberBotMessageId(sentMsg);
              console.log(`[ENVIADO] Respuesta enviada con éxito.`);
            } else {
              console.log(`[IGNORADO] Django no proporcionó una respuesta para este mensaje.`);
            }
          } catch (err) {
            console.error('Error enviando webhook a Django o reenviando mensaje:', err.code || '', err.response?.status || '', err.message || err);
          }
        }
      } catch (err) {
        console.error('Error procesando messages.upsert:', err);
      }
    });

    console.log(`Socket inicializado para session=${sid}`);
    return sock;
  } catch (err) {
    console.error('Error iniciando socket:', err);
    throw err;
  }
}

// Servidor HTTP minimal con Express
function startServer() {
  const app = express();
  app.use(express.json({ limit: '15mb' }));

  // Normalizar prefijo /whatsapp cuando corre bajo cPanel Phusion Passenger (os.raudie.net/whatsapp)
  app.use((req, res, next) => {
    if (req.url.startsWith('/whatsapp/')) {
      req.url = req.url.slice('/whatsapp'.length);
    } else if (req.url === '/whatsapp') {
      req.url = '/';
    }
    next();
  });

  // Endpoint para que Django pida el QR (string) por usuario
  app.get('/qr', (req, res) => {
    const user = req.query.user || 'default';
    const slot = req.query.slot || '0';
    const sid = sessionId(user, slot);
    const qr = latestQrs.get(sid) || null;
    const status = statuses.get(sid) || 'disconnected';
    if (status === 'connected') return res.json({ qr: null, status, message: 'Conectado, no hay QR activo.' });
    if (!qr) return res.json({ qr: null, status, message: 'No QR disponible actualmente.' });
    return res.json({ qr, status });
  });

  // Endpoint para solicitar generación de nuevo QR (reinicia la sesión para ese user+slot)
  app.post('/generate', async (req, res) => {
    const user = req.query.user || 'default';
    const slot = req.query.slot || '0';
    const sid = sessionId(user, slot);
    try {
      if (statuses.get(sid) === 'connected') {
        return res.json({ ok: true, message: 'Ya conectado', qr: null });
      }
      const dir = path.join(AUTH_ROOT, sid);
      if (fs.existsSync(dir)) {
        fs.rmSync(dir, { recursive: true, force: true });
      }
      await startSocketFor(sid);

      const maxWait = 10000; // 10s
      const interval = 500;
      let waited = 0;
      let qr = latestQrs.get(sid) || null;
      while (!qr && waited < maxWait) {
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, interval));
        waited += interval;
        qr = latestQrs.get(sid) || null;
      }

      return res.json({ ok: true, message: `Generando QR para session=${sid}`, qr });
    } catch (err) {
      console.error('Error generando QR:', err);
      return res.status(500).json({ ok: false, error: String(err) });
    }
  });

  // Endpoint para desvincular un teléfono (cierra sesión y borra credenciales)
  app.post('/unlink', async (req, res) => {
    const user = req.query.user || 'default';
    const slot = req.query.slot || '0';
    const sid = sessionId(user, slot);
    try {
      const sock = sockets.get(sid);
      if (sock) {
        try {
          if (sock?.ws && typeof sock.ws.close === 'function') sock.ws.close();
        } catch (e) {
          try { sock?.ev?.removeAllListeners && sock.ev.removeAllListeners(); } catch (e2) {}
        }
        sockets.delete(sid);
      }
      const dir = path.join(AUTH_ROOT, sid);
      if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true });
      latestQrs.delete(sid);
      statuses.set(sid, 'unlinked');
      backoffMap.delete(sid);
      return res.json({ ok: true, message: `Desvinculado session=${sid}` });
    } catch (err) {
      console.error('Error desvinculando:', err);
      return res.status(500).json({ ok: false, error: String(err) });
    }
  });

  // Endpoint para enviar mensajes desde Django: { number, message } admite ?user=
  app.post('/send', async (req, res) => {
    const { number, message } = req.body || {};
    const user = req.query.user || req.body.user || 'default';
    const slot = req.query.slot || req.body.slot || '0';
    const sid = sessionId(user, slot);
    if (!number || !message) return res.status(400).json({ ok: false, success: false, error: 'Faltan campos: number y message' });
    const sock = sockets.get(sid);
    if (!sock || statuses.get(sid) !== 'connected') return res.status(503).json({ ok: false, success: false, error: `WhatsApp no vinculado para session=${sid}` });

    try {
      const jid = await resolveWhatsAppJid(sock, number);
      if (!jid) return res.status(400).json({ ok: false, success: false, error: 'Número inválido' });
      const sentMsg = await sock.sendMessage(jid, { text: message });
      rememberBotMessageId(sentMsg);
      return res.json({ ok: true, success: true, jid });
    } catch (err) {
      console.error('Error enviando mensaje:', err?.message || err);
      return res.status(500).json({ ok: false, success: false, error: 'Error enviando mensaje', details: err?.message || String(err) });
    }
  });

  // Endpoint para consultar estado del bot por user
  app.get('/status', (req, res) => {
    const user = req.query.user || 'default';
    const slot = req.query.slot || '0';
    const sid = sessionId(user, slot);
    const status = statuses.get(sid) || 'disconnected';
    return res.json({ status });
  });

  app.post('/send-doc', async (req, res) => {
    const { number, message, filename, filedata } = req.body || {};
    const user = req.query.user || req.body.user || 'default';
    const slot = req.query.slot || req.body.slot || '0';
    const sid = sessionId(user, slot);

    if (!number || !filedata) return res.status(400).json({ ok: false, success: false, error: 'Faltan campos: number y filedata' });

    const sock = sockets.get(sid);
    if (!sock) return res.status(503).json({ ok: false, success: false, error: `Socket no inicializado para session=${sid}` });

    try {
      const jid = await resolveWhatsAppJid(sock, number);
      const buffer = Buffer.from(filedata, 'base64');

      if (message) {
        const sentTxt = await sock.sendMessage(jid, { text: message });
        rememberBotMessageId(sentTxt);
      }

      const sentDoc = await sock.sendMessage(jid, {
        document: buffer,
        mimetype: 'application/pdf',
        fileName: filename || 'consulta.pdf'
      });
      rememberBotMessageId(sentDoc);

      return res.json({ ok: true, success: true, jid });
    } catch (err) {
      console.error('Error enviando documento:', err?.message || err);
      return res.status(500).json({ ok: false, success: false, error: 'Error enviando documento', details: err?.message || String(err) });
    }
  });

  return new Promise((resolve, reject) => {
    let retries = 0;
    const maxRetries = 8;

    const tryListen = () => {
      const srv = app.listen(PORT, () => {
        console.log(`WhatsApp gateway escuchando en http://localhost:${PORT} (Webhook -> ${PRIMARY_WEBHOOK})`);
        resolve(srv);
      });
      srv.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
          retries += 1;
          if (retries <= maxRetries) {
            setTimeout(tryListen, 400);
          } else {
            console.log(`Puerto ${PORT} ya está en uso por otra instancia activa de WhatsApp Gateway. Saliendo sin duplicar sesión.`);
            process.exit(0);
          }
        } else {
          reject(err);
        }
      });
    };

    tryListen();
  });
}


(async () => {
  try {
    // Iniciar servidor HTTP primero (evita conflictos de sesión si ya hay otra instancia activa)
    await startServer();

    // Auto-iniciar sesiones existentes
    const authDir = AUTH_ROOT;
    if (fs.existsSync(authDir)) {
      const sessions = fs.readdirSync(authDir);
      for (const sid of sessions) {
        if (fs.statSync(path.join(authDir, sid)).isDirectory()) {
          console.log(`Auto-iniciando sesión existente: ${sid}`);
          startSocketFor(sid).catch(err => console.error(`Error auto-iniciando ${sid}:`, err));
        }
      }
    }
  } catch (err) {
    console.error('Fallo en el arranque del servicio:', err);
    process.exit(1);
  }
})();
