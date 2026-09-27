import os
import sys

sys.path.insert(0, '/home/raudajly/saas_demo')
sys.path.insert(1, '/home/raudajly/saas_demo/config')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
