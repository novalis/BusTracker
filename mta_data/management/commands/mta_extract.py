from django.core.management.base import BaseCommand
from zipfile import ZipFile
import os

def recursive_extract(dirname):
    files = os.listdir(dirname)
    for filename in files:
        if filename.endswith('.zip'):
            zip = ZipFile(os.path.join(dirname, filename))
            zip.extractall(dirname)

    files = os.listdir(dirname)
    for filename in files:
        if os.path.isdir(filename):
            recursive_extract(os.path.join(dirname, filename))
        
class Command(BaseCommand):
    def handle(self, dirname, **kw):
        recursive_extract(dirname)

