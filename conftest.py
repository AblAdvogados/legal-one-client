import sys
import os

# Garante que a raiz do projeto está no sys.path,
# permitindo imports absolutos como:
#   from infrastructure.crawler.contacts import ContactsCrawler
#   from errors import LegalOneError
sys.path.insert(0, os.path.dirname(__file__))
