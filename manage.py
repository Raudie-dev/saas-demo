#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import subprocess
import atexit
import signal


def _start_whatsapp_gateway():
    """Inicia el microservicio Node.js (whatsapp-gateway) automáticamente al correr runserver."""
    # En desarrollo con reloader de Django, solo iniciar en el proceso hijo (RUN_MAIN == 'true')
    # O si se ejecuta con --noreload
    is_runserver = len(sys.argv) > 1 and sys.argv[1] == 'runserver'
    if not is_runserver:
        return None

    use_reloader = '--noreload' not in sys.argv
    if use_reloader and os.environ.get('RUN_MAIN') != 'true':
        return None

    base_dir = os.path.dirname(os.path.abspath(__file__))
    gw_dir = os.path.join(base_dir, 'whatsapp-gateway')
    if not os.path.exists(gw_dir):
        return None

    node_bin = os.environ.get('NODE_PATH_BIN') or 'node'

    sys.stdout.write("\033[92m🚀 [WhatsApp Gateway] Iniciando microservicio Node.js en segundo plano (http://127.0.0.1:3000)...\033[0m\n")
    sys.stdout.flush()

    try:
        proc = subprocess.Popen(
            [node_bin, 'index.js'],
            cwd=gw_dir,
            stdout=sys.stdout,
            stderr=sys.stderr
        )

        def _cleanup():
            if proc and proc.poll() is None:
                sys.stdout.write("\n\033[93m🛑 Deteniendo microservicio WhatsApp Gateway...\033[0m\n")
                sys.stdout.flush()
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()

        atexit.register(_cleanup)

        # Manejador de señal de interrupción para salida limpia
        orig_sigint = signal.getsignal(signal.SIGINT)
        def _sigint_handler(signum, frame):
            _cleanup()
            if callable(orig_sigint):
                orig_sigint(signum, frame)
            else:
                sys.exit(0)

        signal.signal(signal.SIGINT, _sigint_handler)
        return proc
    except Exception as e:
        sys.stderr.write(f"\033[91m⚠️ Error al iniciar WhatsApp Gateway: {e}\033[0m\n")
        sys.stderr.flush()
        return None


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    gw_proc = _start_whatsapp_gateway()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    try:
        execute_from_command_line(sys.argv)
    finally:
        if gw_proc and gw_proc.poll() is None:
            try:
                gw_proc.terminate()
            except Exception:
                pass


if __name__ == '__main__':
    main()

