import base64
import hashlib
import hmac
import logging
import os
from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_FERNET = True
except ImportError:
    Fernet = None
    InvalidToken = Exception
    HAS_FERNET = False

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc::v1::"
STDLIB_PREFIX = "enc::s1::"


def _get_secret_bytes() -> bytes:
    secret = getattr(settings, 'ENCRYPTION_KEY', None) or getattr(settings, 'SECRET_KEY', 'default-insecure-key-fallback')
    if isinstance(secret, str):
        return secret.encode('utf-8')
    return bytes(secret)


def _get_fernet_cipher():
    """
    Deriva una clave simétrica Fernet de 32 bytes a partir de ENCRYPTION_KEY o SECRET_KEY.
    """
    key_32 = hashlib.sha256(_get_secret_bytes()).digest()
    urlsafe_key = base64.urlsafe_b64encode(key_32)
    return Fernet(urlsafe_key)


def _stdlib_encrypt(plaintext: str) -> str:
    """Cifrado autenticado de respaldo usando únicamente la librería estándar de Python (PBKDF2 + HMAC-SHA256)."""
    salt = os.urandom(16)
    secret_bytes = _get_secret_bytes()
    raw = plaintext.encode('utf-8')
    keystream = hashlib.pbkdf2_hmac('sha256', secret_bytes, salt, 10000, dklen=len(raw))
    ciphertext = bytes(a ^ b for a, b in zip(raw, keystream))
    mac = hmac.new(secret_bytes, salt + ciphertext, hashlib.sha256).digest()
    payload = base64.urlsafe_b64encode(salt + mac + ciphertext).decode('utf-8')
    return f"{STDLIB_PREFIX}{payload}"


def _stdlib_decrypt(token_with_prefix: str) -> str:
    payload_b64 = token_with_prefix[len(STDLIB_PREFIX):]
    raw_blob = base64.urlsafe_b64decode(payload_b64.encode('utf-8'))
    salt = raw_blob[:16]
    mac = raw_blob[16:48]
    ciphertext = raw_blob[48:]
    secret_bytes = _get_secret_bytes()
    expected_mac = hmac.new(secret_bytes, salt + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Firma HMAC inválida")
    keystream = hashlib.pbkdf2_hmac('sha256', secret_bytes, salt, 10000, dklen=len(ciphertext))
    plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return plaintext_bytes.decode('utf-8')


def is_encrypted(value: str) -> bool:
    """
    Indica si una cadena ya está cifrada con el prefijo Fernet o Stdlib.
    """
    if not value or not isinstance(value, str):
        return False
    clean = value.strip()
    return clean.startswith(ENCRYPTION_PREFIX) or clean.startswith(STDLIB_PREFIX)


def encrypt_secret(value: str) -> str:
    """
    Cifra una cadena sensible (API Key, Token) usando Fernet (AES-128-CBC + HMAC)
    o PBKDF2+HMAC-SHA256 si cryptography no está instalado en el servidor.
    """
    if not value:
        return ""
    clean = str(value).strip()
    if not clean:
        return ""
    if is_encrypted(clean):
        return clean
    try:
        if HAS_FERNET:
            cipher = _get_fernet_cipher()
            token = cipher.encrypt(clean.encode('utf-8')).decode('utf-8')
            return f"{ENCRYPTION_PREFIX}{token}"
        return _stdlib_encrypt(clean)
    except Exception as e:
        logger.error(f"Error al cifrar secreto: {e}")
        return clean


def decrypt_secret(value: str) -> str:
    """
    Descifra un secreto previamente cifrado con encrypt_secret.
    Si el valor no estaba cifrado (legacy / texto plano), retorna el texto tal cual.
    """
    if not value:
        return ""
    clean = str(value).strip()
    if not clean:
        return ""
    if not is_encrypted(clean):
        return clean
    try:
        if clean.startswith(STDLIB_PREFIX):
            return _stdlib_decrypt(clean)
        if clean.startswith(ENCRYPTION_PREFIX) and HAS_FERNET:
            token = clean[len(ENCRYPTION_PREFIX):]
            cipher = _get_fernet_cipher()
            return cipher.decrypt(token.encode('utf-8')).decode('utf-8')
        return ""
    except (InvalidToken, Exception) as e:
        logger.warning(f"No se pudo descifrar el secreto: {e}")
        return ""


def mask_secret(value: str, visible_start: int = 4, visible_end: int = 4) -> str:
    """
    Mascara un secreto para visualización segura en interfaz (ej: sk-a...9f12).
    """
    if not value:
        return ""
    raw = decrypt_secret(value)
    if not raw:
        return ""
    if len(raw) <= (visible_start + visible_end):
        return "•" * len(raw)
    return f"{raw[:visible_start]}...{raw[-visible_end:]}"
