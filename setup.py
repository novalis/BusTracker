# Copyright (C) 2009 The Open Planning Project

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the 
# Free Software Foundation, Inc., 
# 51 Franklin Street, Fifth Floor, 
# Boston, MA  02110-1301
# USA

import sys, os
from setuptools import setup, find_packages

setup(
    name='BusTracker',
    version="0.1",
    #description="",
    author="The Open Planning Project",
    author_email="novalis@openplans.org",
    install_requires=[
      "Django>=1.0.2",
      "pytz",
      "psycopg2",
      "simplejson",
      ],
    packages=find_packages(),
    include_package_data=True,
    test_suite = 'nose.collector',
    package_data={'bustracker': ['i18n/*/LC_MESSAGES/*.mo']},
    entry_points={'django.apps': 'tracker = tracker'},

)
