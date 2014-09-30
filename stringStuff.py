"""
# String operations - Teil der Sammelbestellungs-Abrechnung
# https://github.com/mgmax/sammelbestellung
# 
# (c) 2014 Max Gaukler <development@maxgaukler.de>
#
# some parts based on Part-DB autoprice - price fetcher
# (c) 2009 Michael Buesch <mb@bu3sch.de>
#
# Licensed under the GNU/GPL version 2 or (at your option) any later version
"""

import re

def removeChars(string, template):
    for t in template:
        string = string.replace(t, "")
    return string

def match(r,s):
    return re.compile(r).match(s).group(1)

def multiMatch(r,s):
    return re.compile(r).findall(s)
