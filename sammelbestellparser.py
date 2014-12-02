#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
# Sammelbestellungs-Abrechnung
# https://github.com/mgmax/sammelbestellung
# 
# (c) 2013 Max Gaukler <development@maxgaukler.de>
# EML-Output, subdir, billing, ...(c) 2013 Patrick Kanzler <patrick.kanzler@fablab.fau.de>
#
# Licensed under the GNU/GPL version 2 or (at your option) any later version
"""

# TODO there are some unnecessary imports here

import os
import shutil
import sys
import getopt
import httplib
import socket
import urllib
import re
import time
import logging
import cookielib, urllib2
import copy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import subprocess
import shlex
from string import Template
import locale
import codecs

# local imports
import pricefetcher
import stringStuff

# TODO really refactor


class Buyer:
    def __init__(self,name=None,mail=None,basket=None):
        self.basket=basket
        if self.basket==None:
            self.basket=pricefetcher.Basket()
        self.name=name
        self.mail=mail
        if self.mail==None:
            self.mail="NOMAIL"
        self.shopFinalSums={}
        self.shopShipping={}
        self.totalShipping=None
        self.finalSum=None
        self.co=None
        self.street=None
        self.city=None
    def __str__(self):
        return "<Buyer, name '"+ unicode(self.name) + "', basket  "+unicode(self.basket)+" >"
    def __repr__(self):
        return str(self)
    
# needed for From-Field of mail
class Origin:
    def __init__(self,mail=None):
        self.mail=mail
        if self.mail==None:
            self.mail="john.doe@example.org"
        self.name="John Doe"
        self.street="Apfelstraße 23"
        self.city="Heidenheim"
        self.areacode="66666"
        self.kto= "123456789"
        self.blz="123\,123\,12"
        self.bank="Musterbank"
        self.phone="0190\,666\,666"
    def __str__(self):
        return self.name + " <" + self.mail + ">"
    def __repr__(self):
        return(self)
        
# organizes settings
class Settings:
    def __init__(self):
        self.mailtext="emailtext.txt"
        self.billtemplate="billtemplate.tex"
        self.subdir=False
        self.billing=False
        self.paylist=False


def parse(filename):
    f=codecs.open(filename, 'r', 'utf8')
    class ParseContext:
        def __init__(self):
            self.shop=None
            self.buyer=None
            self.basket=pricefetcher.Basket()
    context=ParseContext()
    buyers=[]
    origin=Origin() # for From-field of mail
    settings=Settings() # for settings like subdir
    lines=f.readlines() + [""] # add empty line at end
    for line in lines:
        line=stringStuff.removeChars(line,"\r\n")
        logging.debug("Parsing line: "+line)
        cmdMatch=re.match("^!([a-z]+) (.*)$",line)
        itemMatch=re.match("^([0-9]+)[;\t] *([^#;\t]*)[;\t] *([^#;\t]*[^#;\t ]) *(#.*)?$",line)
        shortItemMatch=re.match("^([0-9]+)[;\t] *([^#;\t]*[^#;\t ]) *(#.*)?$",line)
        if re.match("^\s*$",line):
            # only whitespace - empty line
            logging.debug("empty line, starting new context.")
            if (context.buyer is not None):
                context.buyer.basket.add(context.basket.parts())
                buyers += [copy.copy(context.buyer)]
                logging.debug("finished old buyer from context: " + unicode(context.buyer))
            elif context.basket.parts() != []:
                raise Exception("parts not belonging to anyone - forgot !buyer or added accidental empty line?")
            for p in context.basket.parts():
                if p.shop == None:
                    raise Exception("Some parts have no shop in this block - Missing !shop ?")
            context=ParseContext()
            logging.debug("reset context")
        elif (re.match("^#.*", line)):
            # skip comment
            logging.debug("comment: " + line)
        elif (cmdMatch):
            # special command:
            # !cmd arg...
            cmd=cmdMatch.group(1)
            arg=cmdMatch.group(2)
            logging.debug("Command " + unicode(cmd) + ", arg " + unicode(arg))
            if cmd=="shop":
                context.shop=arg
            elif cmd=="buyer":
                if (context.buyer!=None):
                    raise Exception("two !buyer s per block are not allowed. please insert an empty line before starting a new buyer.")
                context.buyer=Buyer(name=arg)
            elif cmd=="mail":
                if (context.buyer==None):
                    raise Exception("you should specify the mail-address only after a buyer.")
                context.buyer.mail=arg
            elif cmd=="co":
                if (context.buyer==None):
                    raise Exception("you should specify the co-address only after a buyer.")
                context.buyer.co=arg
            elif cmd=="street":
                if (context.buyer==None):
                    raise Exception("you should specify the street-address only after a buyer.")
                context.buyer.street=arg
            elif cmd=="city":
                if (context.buyer==None):
                    raise Exception("you should specify the city-address only after a buyer.")
                context.buyer.city=arg                
            elif cmd=="basket":
                context.basket.add(pricefetcher.shopByName(context.shop).fetchBasket(arg))
            elif cmd=="warning":
                logging.warning("Warning: " + line)
            elif cmd=="setfactor":
                if ("*" in arg): # possible syntax: 1*2*3*4 (multiplied factors)
                    factor=1
                    for i in arg.split("*"):
                        factor *= float(i)
                else: # simple syntax: 1234 (one factor)
                    factor=float(arg)
                pricefetcher.shopByName(context.shop).factor=factor
            elif cmd=="setshipping":
                pricefetcher.shopByName(context.shop).shipping=float(arg)
            elif cmd=="origin":
                # TODO raise Exception("you may not specify more than one origin")
                origin = Origin(mail=arg)
            elif cmd=="originname":
                origin.name = arg
            elif cmd=="originmail":
                origin.mail = arg
            elif cmd=="originstreet":
                origin.street = arg
            elif cmd=="origincity":
                origin.city = arg
            elif cmd=="originac":
                origin.areacode = arg                
            elif cmd=="originkto":
                origin.kto = arg
            elif cmd=="originblz":
                origin.blz = arg
            elif cmd=="originbank":
                origin.bank = arg    
            elif cmd=="originphone":
                origin.phone = arg    
            elif cmd=="locale":
                locale.setlocale(locale.LC_ALL, arg)
            elif cmd=="subdir":
                if arg=="true":
                    settings.subdir = True
                elif arg=="false":
                    settings.subdir = False
                else:
                    raise Exception("write 'subdir true or false' (lower case)")
            elif cmd=="mailtext":
                settings.mailtext=arg
            elif cmd=="billing":
                if arg=="true":
                    settings.billing = True
                elif arg=="false":
                    settings.billing = False
                else:
                    raise Exception("write 'billing true or false' (lower case)")
            elif cmd=="billtemplate":
                settings.billtemplate=arg
            elif cmd=="paylist":
                if arg=="true":
                    settings.paylist = True
                elif arg=="false":
                    settings.paylist = False
                else:
                    raise Exception("write 'paylist true or false' (lower case)")
            else:
                raise Exception("unknown command " + str(cmd))
        elif (shortItemMatch or itemMatch):
            if shortItemMatch:
                shop=context.shop
                count=shortItemMatch.group(1)
                partNr=shortItemMatch.group(2)
            elif itemMatch:
                shop=itemMatch.group(2)
                count=itemMatch.group(1)
                partNr=itemMatch.group(3)
            logging.debug("item: shop " + str(shop) + " part '" + str(partNr) + "' count " + str(count))
            context.basket.add(pricefetcher.Part(shop=shop,partNr=partNr,count=count))
        else:
            raise Exception("Parse error with line " + line)
        
    totalBasket=pricefetcher.Basket()
    for b in buyers:
        totalBasket.add(b.basket.parts())
    
    logging.debug("Total Basket: " + str(totalBasket))
    return [buyers, origin, settings, totalBasket]
