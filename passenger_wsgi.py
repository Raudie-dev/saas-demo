import glob
import os
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, '/home/raudajly/saas_demo')
sys.path.insert(1, '/home/raudajly/saas_demo/config')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def _ensure_cpanel_whatsapp_gateway():
    """
    Asegura que el microservicio Node.js (whatsapp-gateway) esté corriendo en el puerto 3000
    cuando Phusion Passenger levanta la aplicación en cPanel.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', 3000)) == 0:
                return
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    gw_dir = os.path.join(base_dir, 'whatsapp-gateway')
    if not os.path.exists(gw_dir):
        return

    # Buscar binario de Node.js en rutas estándar y de CloudLinux / cPanel NodeJS Selector
    node_bin = os.environ.get('NODE_PATH_BIN') or shutil.which('node')
    if not node_bin:
        candidates = (
            glob.glob('/opt/alt/alt-nodejs*/root/usr/bin/node')
            + glob.glob('/home/*/nodevenv/*/*/bin/node')
            + ['/usr/local/bin/node', '/usr/bin/node']
        )
        for cand in sorted(candidates, reverse=True):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                node_bin = cand
                break

    if not node_bin:
        return

    env = os.environ.copy()
    site_url = os.environ.get('SITE_URL', 'https://os.raudie.net').rstrip('/')
    env.setdefault('DJANGO_WEBHOOK', f'{site_url}/ia/webhook/whatsapp/')

    try:
        log_path = os.path.join(gw_dir, 'gateway.log')
        log_file = open(log_path, 'a', encoding='utf-8')
        subprocess.Popen(
            [node_bin, 'index.js'],
            cwd=gw_dir,
            env=env,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )
    except Exception:
        pass


_ensure_cpanel_whatsapp_gateway()

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
