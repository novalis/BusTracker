#!/usr/bin/python

#httplib2 requires gzip, which is part of the Python standard library.
#However, SHR doesn't have it.  We'll just hope we get no gzip-encoded
#responses.
