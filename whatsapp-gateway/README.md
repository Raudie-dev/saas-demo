# WhatsApp Gateway (Node.js)

Microservicio que actúa como pasarela entre WhatsApp (Multi-Device via @whiskeysockets/baileys) y un backend Django.

Características principales:
- Genera QR en la terminal y expone `GET /qr` para que Django lo consuma.
- Reenvía mensajes entrantes a: `http://127.0.0.1:8000/api/whatsapp/webhook/`.
- Permite a Django enviar mensajes con `POST /send`.
- Persiste sesión en `auth_info/` para evitar re-scan.

Instalación

1. Entrar a la carpeta del servicio:

```bash
cd "whatsapp-gateway"
```

2. Instalar dependencias:

```bash
npm install
```

3. Variables de entorno opcionales:
- `PORT` (por defecto 3000)
- `DJANGO_WEBHOOK` (por defecto http://127.0.0.1:8000/api/whatsapp/webhook/)

Uso

```bash
npm start
```

Endpoints principales
- `GET /qr` → devuelve JSON `{ qr: <string|null> }` (para mostrar en tu panel Django).
- `POST /send` → enviar mensaje. Body JSON: `{ "number": "5733...", "message": "Hola" }`.

Formato webhook enviado a Django (POST JSON):
```json
{ "remoteJid": "123456789@s.whatsapp.net", "pushName": "Nombre Usuario", "messageText": "Texto del mensaje" }
```

Notas
- La carpeta `auth_info` se crea automáticamente y contiene las credenciales de la sesión.
- El QR sólo se muestra mientras la sesión no esté autenticada.
