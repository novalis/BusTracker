"""
Wrapper script for django's mod_python handler:
We need to get our virtualenv's library into site-packages.
Based on suggestions from
http://paste.lisp.org/display/59757
and
http://blog.ianbicking.org/2007/10/10/workingenv-is-dead-long-live-virtualenv/
"""

import os
import site

basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sitepkgs = os.path.join(basedir, 'lib', 'python2.4', 'site-packages')
site.addsitedir(sitepkgs)

from django.core.handlers.modpython import handler
