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
import { makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion } from '@whiskeysockets/baileys';

const PORT = process.env.PORT || 3000;
const DJANGO_WEBHOOK = process.env.DJANGO_WEBHOOK || 'http://127.0.0.1:8000/app2/api/whatsapp/webhook/';

// Mapas por sesión (clave: userId)
const sockets = new Map();
const latestQrs = new Map();
const statuses = new Map();
const backoffMap = new Map();

function sessionId(user, slot) {
  const s = slot === undefined || slot === null ? '0' : String(slot);
  const u = user === undefined || user === null ? 'default' : String(user);
  return `${u}_${s}`;
}

// Extrae texto del mensaje en los distintos tipos soportados
function extractMessageText(message) {
  if (!message) return '';
  if (message.conversation) return message.conversation;
  if (message.extendedTextMessage && message.extendedTextMessage.text) return message.extendedTextMessage.text;
  if (message.imageMessage && message.imageMessage.caption) return message.imageMessage.caption;
  if (message.videoMessage && message.videoMessage.caption) return message.videoMessage.caption;
  if (message.buttonsResponseMessage && message.buttonsResponseMessage.selectedButtonId) return message.buttonsResponseMessage.selectedButtonId;
  if (message.templateButtonReplyMessage && message.templateButtonReplyMessage.selectedId) return message.templateButtonReplyMessage.selectedId;
  // fallback: stringify (útil para tipos nuevos o debugging)
  try { return JSON.stringify(message); } catch (e) { return '' }
}

// Inicia el socket de Baileys con persistencia en ./auth_info
async function startSocketFor(sid = 'default:0') {
  try {
    const dir = `./auth_info/${sid}`;
    const { state, saveCreds } = await useMultiFileAuthState(dir);
    const { version } = await fetchLatestBaileysVersion();
    // If there is already a socket for this session id, close the websocket instead of calling logout()
    // to avoid Intentional Logout which invalidates credentials on WhatsApp side.
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
    // clear previous QR and set initializing
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
        console.log(`Conexión abierta con WhatsApp (session=${sid})`);
      }

      if (connection === 'close') {
        statuses.set(sid, 'disconnected');
        // Detectar logout intencional (credenciales invalidas)
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
        // reintentos con backoff exponencial para evitar bucles agresivos
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
        const messages = m.messages || [];
        for (const msg of messages) {
          if (!msg.message || msg.key?.fromMe) continue;
          if (msg.key.remoteJid.endsWith('@g.us')) continue;
          if (msg.key.remoteJid === 'status@broadcast') continue;

          const remoteJid = msg.key.remoteJid || '';
          const pushName = msg.pushName || msg.contact?.name || '';
          const messageText = extractMessageText(msg.message);
          
          console.log(`\n[RECIBIDO] Mensaje de ${remoteJid} (${pushName}): ${messageText}`);

          // Enviar al webhook de Django y reenviar la respuesta al usuario
          try {
            const owner = String(sid).split('_')[0];
            const resp = await axios.post(
                DJANGO_WEBHOOK,
                { remoteJid, pushName, messageText, session: sid, owner },
                { headers: {
                    'Content-Type': 'application/json',
                    'X-Webhook-Secret': process.env.WEBHOOK_SECRET || 'pon-aqui-un-token-largo-y-aleatorio-32chars'
                }}
            );
            
            console.log(`[WEBHOOK] Django respondió con HTTP ${resp.status}`);
            console.log(`[WEBHOOK] Datos recibidos:`, resp.data);

            if (resp && resp.data && resp.data.reply && resp.data.reply.trim() !== '') {
              console.log(`[ENVIANDO] Respondiendo a ${remoteJid}: ${resp.data.reply}`);
              await sock.sendMessage(remoteJid, { text: resp.data.reply });
              console.log(`[ENVIADO] Respuesta enviada con éxito.`);
            } else {
              console.log(`[IGNORADO] Django no proporcionó una respuesta para este mensaje.`);
            }
          } catch (err) {
            console.error('Error enviando webhook a Django o reenviando mensaje:', err.message || err);
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
  app.use(express.json());
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
      // Si ya esta conectado, no hacer nada
      if (statuses.get(sid) === 'connected') {
        return res.json({ ok: true, message: 'Ya conectado', qr: null });
      }
      const dir = path.resolve(`./auth_info/${sid}`);
      if (fs.existsSync(dir)) {
        fs.rmSync(dir, { recursive: true, force: true });
      }
      // (re)inicia socket para esa sesión
      // startSocketFor establecerá statuses.set(sid, 'initializing') y publicará el QR en latestQrs cuando esté listo
      await startSocketFor(sid);

      // Esperar hasta X ms para que aparezca el QR en latestQrs (polling suave)
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
        // Cerrar websocket y eliminar listeners en lugar de logout()
        try {
          if (sock?.ws && typeof sock.ws.close === 'function') sock.ws.close();
        } catch (e) {
          try { sock?.ev?.removeAllListeners && sock.ev.removeAllListeners(); } catch (e2) {}
        }
        sockets.delete(sid);
      }
      const dir = path.resolve(`./auth_info/${sid}`);
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
    if (!number || !message) return res.status(400).json({ error: 'Faltan campos: number y message' });
    const sock = sockets.get(sid);
    if (!sock) return res.status(503).json({ error: `Socket no inicializado para session=${sid}` });

    try {
      const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
      await sock.sendMessage(jid, { text: message });
      return res.json({ ok: true });
    } catch (err) {
      console.error('Error enviando mensaje:', err?.message || err);
      return res.status(500).json({ error: 'Error enviando mensaje', details: err?.message || String(err) });
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

    if (!number || !filedata) return res.status(400).json({ error: 'Faltan campos: number y filedata' });

    const sock = sockets.get(sid);
    if (!sock) return res.status(503).json({ error: `Socket no inicializado para session=${sid}` });

    try {
      const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
      const buffer = Buffer.from(filedata, 'base64');

      if (message) {
        await sock.sendMessage(jid, { text: message });
      }

      await sock.sendMessage(jid, {
        document: buffer,
        mimetype: 'application/pdf',
        fileName: filename || 'consulta.pdf'
      });

      return res.json({ ok: true });
    } catch (err) {
      console.error('Error enviando documento:', err?.message || err);
      return res.status(500).json({ error: 'Error enviando documento', details: err?.message || String(err) });
    }
  });

  app.listen(PORT, () => console.log(`WhatsApp gateway escuchando en http://localhost:${PORT}`));
}


(async () => {
  try {
    // Iniciar servidor HTTP
    startServer();

    // Auto-iniciar sesiones existentes
    const authDir = path.resolve('./auth_info');
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
