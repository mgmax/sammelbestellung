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

# local imports
import pricefetcher
import sammelbestellparser
import sammelbestellOutput
import stringStuff

# returns: [buyers, origin, settings, totalBasket]
def parseAndFetch(file):
    [buyers, origin, settings, totalBasket]=sammelbestellparser.parse(file)
    return fetchAndCalculatePrices(buyers, origin, settings, totalBasket)

# returns: [buyers, origin, settings, totalBasket, totalSums]
def fetchAndCalculatePrices(buyers, origin, settings, totalBasket):
    totalBasket.fetchPrices()
    for b in buyers:
        b.basket.takePricesFrom(totalBasket)
    subtotalSums=totalBasket.shopSums()
    totalSums={}
    
    for (shop,s) in subtotalSums.items():
        if pricefetcher.shopByName(shop).factor is None or pricefetcher.shopByName(shop).shipping is None:
            raise Exception("no factor or shipping set for shop %s. Please at least put !shop shopname, !setfactor 1 and !setshipping 0 for each shop at the beginning of your file" % str(shop))
        totalSums[shop]=s*pricefetcher.shopByName(shop).factor + pricefetcher.shopByName(shop).shipping
        print "Shop " + shop + " subtotal " + str(s) + ". * factor " + str(pricefetcher.shopByName(shop).factor) + " + shipping " + str(pricefetcher.shopByName(shop).shipping) + " = Total " + str(totalSums[shop])
    
    
    for b in buyers:
        b.finalSum=0
        b.totalShipping=0
        for (shop,s) in totalSums.items():
            subtotal=b.basket.shopSum(shop)
            shipping=b.basket.shopSum(shop)/subtotalSums[shop]*pricefetcher.shopByName(shop).shipping
            total=subtotal*pricefetcher.shopByName(shop).factor + shipping
            if total != 0:
                logging.info("buyer " + b.name + ", shop "+ shop + " : " + str(total) + " subtotal  (" + str(subtotal) + " * factor " + str(pricefetcher.shopByName(shop).factor) + " + shipping  " + str(shipping))
            b.shopFinalSums[shop]=total
            b.shopShipping[shop]=shipping
            b.totalShipping += shipping
            b.finalSum += total
        logging.info("buyer " + b.name + ", final sum: " + str(b.finalSum) + "  , shops:" + str(b.shopFinalSums))
    
    # checksumming:
    buyersChecksum=0
    for b in buyers:
        buyersChecksum += b.finalSum
    
    shopsChecksum=0
    for (shop, s) in totalSums.items():
        shopsChecksum += s
    logging.info("checksum difference: " + str(shopsChecksum-buyersChecksum)  + ", shop total: " + str(shopsChecksum) + ", buyer total: " + str(buyersChecksum) + ";  individual shops: " + str(totalSums))    
    if (abs(shopsChecksum-buyersChecksum) >= 0.005):
        raise Exception("Checksums do not match!")
    
    return [buyers, origin, settings, totalBasket, totalSums]


if __name__=="__main__":
    locale.setlocale(locale.LC_ALL, '')


    try:
        reload(sys)
        sys.setdefaultencoding("utf8")
        logging.basicConfig(level=logging.DEBUG)
        #logging.basicConfig(level=logging.INFO)
        
        #print "Es kostet %.2f" % fetchPrice("reichelt.de", "PFL 10", 100)
        #print "Es kostet %.2f" % fetchPrice("de.rs-online.com", "666-1608", 10)

        #[ 100, "Reichelt", "PFL 10" ], 
        
        #print PriceFetcherReichelt().fetchBasket("https://secure.reichelt.de/index.html?;ACTION=20;LA=5010;AWKID=619772;PROVID=2084")
        #sys.exit(0)
        if len(sys.argv) != 2:
            sys.stderr.write("usage: '"+sys.argv[0]+"' order_file")
        try:
            [buyers, origin, settings, totalBasket, totalSums]=parseAndFetch(sys.argv[1])
        except IOError:
            sys.stderr.write("Error opening file.\n")
            sys.stderr.write("usage: '"+sys.argv[0]+"' order_file\n")
            sys.exit(1)
        
        sammelbestellOutput.makeOutput(buyers, origin, settings, totalBasket, totalSums)
            
        print "Success!"
        sys.exit(0)
        
        # TODO Mindeststückzahl-Error bei Rei? und RS
        
        #TODO Adresse bei Buyer
        #TODO Adresse des Bestellers
        #TODO Posten ausrechnen und malen
        #TODO pdflatex vorsichtig suchen?
        #TODO extra config-Datei?
        #TODO LongTable?

    except Exception, e:
        #pass
        #print "Error:"
        #print e
        #sys.exit(1)
        raise
