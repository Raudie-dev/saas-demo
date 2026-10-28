import base64
import hashlib
import logging
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc::v1::"


def _get_fernet_cipher() -> Fernet:
    """
    Deriva una clave simétrica Fernet de 32 bytes a partir de ENCRYPTION_KEY o SECRET_KEY.
    """
    secret = getattr(settings, 'ENCRYPTION_KEY', None) or getattr(settings, 'SECRET_KEY', 'default-insecure-key-fallback')
    if isinstance(secret, str):
        secret_bytes = secret.encode('utf-8')
    else:
        secret_bytes = bytes(secret)
    # Genera digest de 32 bytes con SHA-256 y codifica a urlsafe base64 para Fernet
    key_32 = hashlib.sha256(secret_bytes).digest()
    urlsafe_key = base64.urlsafe_b64encode(key_32)
    return Fernet(urlsafe_key)


def is_encrypted(value: str) -> bool:
    """
    Indica si una cadena ya está cifrada con el prefijo o formato Fernet.
    """
    if not value or not isinstance(value, str):
        return False
    clean = value.strip()
    return clean.startswith(ENCRYPTION_PREFIX)


def encrypt_secret(value: str) -> str:
    """
    Cifra una cadena sensible (API Key, Token) usando Fernet (AES-128-CBC + HMAC).
    Retorna la cadena con prefijo enc::v1::
    Si ya está cifrada o vacía, retorna el valor apropiado sin doble cifrado.
    """
    if not value:
        return ""
    clean = str(value).strip()
    if not clean:
        return ""
    if is_encrypted(clean):
        return clean
    try:
        cipher = _get_fernet_cipher()
        token = cipher.encrypt(clean.encode('utf-8')).decode('utf-8')
        return f"{ENCRYPTION_PREFIX}{token}"
    except Exception as e:
        logger.error(f"Error al cifrar secreto: {e}")
        # En caso de error inesperado, preserva el valor
        return clean


def decrypt_secret(value: str) -> str:
    """
    Descifra un secreto previamente cifrado con encrypt_secret.
    Si el valor no estaba cifrado (legacy / texto plano), retorna el texto tal cual
    para garantizar retrocompatibilidad.
    """
    if not value:
        return ""
    clean = str(value).strip()
    if not clean:
        return ""
    if not is_encrypted(clean):
        return clean
    token = clean[len(ENCRYPTION_PREFIX):]
    try:
        cipher = _get_fernet_cipher()
        decrypted = cipher.decrypt(token.encode('utf-8')).decode('utf-8')
        return decrypted
    except InvalidToken:
        logger.warning("Token de cifrado inválido al intentar descifrar secreto.")
        return ""
    except Exception as e:
        logger.error(f"Error al descifrar secreto: {e}")
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
