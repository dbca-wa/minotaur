"""
WSGI config for minotaur project.
It exposes the WSGI callable as a module-level variable named ``application``.
"""
import os
from django.core.wsgi import get_wsgi_application
from pathlib import Path

# These lines are required for interoperability between local and container environments.
d = Path(__file__).resolve().parent
dot_env = os.path.join(str(d), '.env')
if os.path.exists(dot_env):
    from dotenv import read_dotenv
    read_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minotaur.settings')
application = get_wsgi_application()
