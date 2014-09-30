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
import stringStuff


# TODO really refactor

logging.info("generating outputs")
def makeOutput(buyers, origin, settings, totalBasket, totalSums):
    def header(s):
        return "\n==================================\n" + \
        s.upper() +"\n" + \
        "==================================\n"
    outputs={"report":""}
    for (shop,[b,fileEnding]) in totalBasket.exportNativeBaskets().items():
        outputs["basket export "+shop+fileEnding]=b
    outputs["report"] += "Report:\n"
    outputs["report"] += header("total sum")
    outputs["report"] += "Name\ttotal\t(items+shipping)\n"
    for b in buyers:
        outputs["report"] += "%s\t%.2f\t(%.2f+%.2f)\n" % (b.name, b.finalSum,b.finalSum-b.totalShipping,b.totalShipping)
    
    outputs["report"] += header("shops")
    outputs["report"] += "Shop\tSum with shipping\t(items + shipping)\n"
    for (shop, s) in totalSums.items():
        outputs["report"] += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-pricefetcher.shopByName(shop).shipping,pricefetcher.shopByName(shop).shipping)
    
    outputs["report"] += header("details")
    outputs["report"] +=  "name\tcount\traw price each\tfactor\tpartNr\tshop\n"
    for (shop, s) in b.shopFinalSums.items():
        outputs["report"] += "\t\t%.2f\t1\t<Shipping>\t%s\n" % (pricefetcher.shopByName(shop).shipping,shop)
    for b in buyers:
        for p in b.basket.parts():
            outputs["report"] +=  "%s\t%d\t%.3f\t%.4f\t%s\t%s\n" % (b.name,p.count,p.price,pricefetcher.shopByName(p.shop).factor,p.partNr,p.shop)
        for (shop, s) in b.shopFinalSums.items():
            outputs["report"] +=  "%s\t1\t%.3f\t1\t<ShippingPart>\t%s\n" % (b.name,b.shopShipping[shop],shop)
            outputs["report"] +=  "%s\t\t%.3f\t1\t<ShopTotal>\t%s\n" % (b.name, s, shop)
    
    # convert tab-separated table to text with fixed width spaces
    def tabsToFixedWidth(s):
        colWidth={}
        for line in s.splitlines():
            i=0
            for col in line.split("\t"):
                i+=1
                length=len(col.decode("utf-8"))
                try:
                    if colWidth[i] < length:
                        colWidth[i]=length
                except KeyError:
                    # No colWidth entry yet
                    colWidth[i]=length
        r=""
        for line in s.splitlines():
            i=0
            for col in line.split("\t"):
                i+=1
                r += col.decode("utf-8").ljust(colWidth[i]+3)
            r += "\n"
        return r
    
    # insert a linebreak every 5 lines
    def groupLines(s):
        r=""
        n=0
        for line in s.splitlines():
            r+= line +"\n"
            n=n+1
            if n==5:
                n=0
                r+="\n"
        return r
    
    outputs["unpackinglist"]="name\t☒OK\tcount\t(total count)\tpartNr\tshop\n"
    for b in buyers:
        for p in b.basket.parts():
            totalCount=0
            # do items need to be separated?
            for q in totalBasket.parts():
                if (p.partNr==q.partNr and p.shop==q.shop):
                    totalCount=q.count
                    break
            if totalCount==0:
                raise Exception("buyer's item not found in total basket")
            totalCountStr=""
            if totalCount != p.count:
                # buyer must share this item with others - print the total amount to notify him
                totalCountStr="(of %d)" % totalCount
            outputs["unpackinglist"] +=  "%s\t☐\t%d\t%s\t%s\t%s\n" % (b.name,p.count,totalCountStr,p.partNr,p.shop)
    outputs["unpackinglist"]=groupLines(tabsToFixedWidth(outputs["unpackinglist"]))
    outputs["unpackinglist"]=header("unpacking list") + outputs["unpackinglist"]
    outputs["shopTotalBaskets"]="shop\t☒OK\tcount\tpartNr\n";
    totalBasketsLines=[];
    for i in totalBasket.parts():
        totalBasketsLines.append("%s\t☐\t%s\t%s\t\n" % (i.shop,  i.count, i.partNr))
    totalBasketsLines.sort()
    for l in totalBasketsLines:
        outputs["shopTotalBaskets"] += l
    outputs["shopTotalBaskets"]=groupLines(tabsToFixedWidth(outputs["shopTotalBaskets"]))
    outputs["shopTotalBaskets"]=header("Complete basket for each shop (for checking if everything was received correctly)") + outputs["shopTotalBaskets"]
    
    logging.info("generating mail")
    msg = MIMEMultipart()
    msg['From'] = str(origin)
    msg_to = ""
    for b in buyers:
        msg_to += b.name + " <" + b.mail + ">, "
    msg['To'] = msg_to
    order_name = os.path.splitext(sys.argv[1])[0]
    msg['Subject'] = order_name
    try:
        text = open(sys.path[0]+'/'+settings.mailtext, 'r').read()
    except IOError:
        text = "This text will be replaced by emailtext.txt in the same directory as sammelbestellung.py"
    text += header("total sum")
    text += "Name\ttotal\t(items+shipping)\n"
    for b in buyers:
        text += "%s\t%.2f\t(%.2f+%.2f)\n" % (b.name, b.finalSum,b.finalSum-b.totalShipping,b.totalShipping)
    text += header("shops")
    text += "Shop\tSum with shipping\t(items + shipping)\n"
    for (shop, s) in totalSums.items():
        text += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-pricefetcher.shopByName(shop).shipping,pricefetcher.shopByName(shop).shipping)
    msg.attach(MIMEText(text.encode('utf-8'), 'plain', 'UTF-8'))
    outputs["mail.eml"] = str(msg)
    
    #paylist
    if settings.paylist:
        outputs["paylist"] = "Note who has payed yet:\n"
        outputs["paylist"] += header("total sum")
        outputs["paylist"] += "Name\ttotal\t(items+shipping)\n"
        for b in buyers:
            outputs["paylist"] += "%s\t%.2f\t(%.2f+%.2f)\t\t\t---\n" % (b.name, b.finalSum,b.finalSum-b.totalShipping,b.totalShipping)
        
        outputs["paylist"] += header("shops")
        outputs["paylist"] += "Shop\tSum with shipping\t(items + shipping)\n"
        for (shop, s) in totalSums.items():
            outputs["paylist"] += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-pricefetcher.shopByName(shop).shipping,pricefetcher.shopByName(shop).shipping)
        
    
    if settings.billing:
        logging.info("should generate bills")
        try:
            content = open(sys.path[0]+'/'+settings.billtemplate, 'r').read()
        except IOError:
            text = "This text will be replaced by billtemplate.tex (or the filename set by !billtemplate) in the same directory as sammelbestellung.py, "
        for b in buyers:
            logging.info("generating bill for " + b.name)
            tabledata=""
            #tabledata += "%s\t%.2f\t(%.2f+%.2f)\n" % (b.name, b.finalSum,b.finalSum-b.totalShipping,b.totalShipping)
            totalWithoutShipping = locale.format("%.3f",b.finalSum-b.totalShipping, True, True)
            
            for p in b.basket.parts():
                #tabledata +=  "%d %.3f %.4f %s %s\n" % (p.count,p.price,pricefetcher.shopByName(p.shop).factor,p.partNr,p.shop)
                tabledata +=  "%d & %s & \multicolumn{1}{r}{%s \euro} & \multicolumn{1}{r}{%s \euro} \\\\ \hline\n" % (p.count,p.partNr,locale.format("%.3f", p.price, True, True),locale.format("%.3f", p.price*p.count, True, True))
                
            ShippingTotal=0
            for (shop, s) in b.shopFinalSums.items():
                ShippingTotal += pricefetcher.shopByName(shop).shipping
                #tabledata +=  "%s\t1\t%.3f\t1\t<ShippingPart>\t%s\n" % (b.name,b.shopShipping[shop],shop)
                #tabledata +=  "%s\t\t%.3f\t1\t<ShopTotal>\t%s\n" % (b.name, s, shop)
            
            globalSum = 0
            for (shop, s) in totalSums.items():
                globalSum += s-pricefetcher.shopByName(shop).shipping
                #outputs["report"] += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-pricefetcher.shopByName(shop).shipping,pricefetcher.shopByName(shop).shipping)
            
            t = Template(content)
            if b.co==None:
                rco=""
            else:
                rco=b.co + "\\\\"
            if b.street==None:
                rstreet=""
            else:
                rstreet=b.street + "\\\\"
            if b.city==None:
                rcity=""
            else:
                rcity=b.city + "\\\\"
            content_out = t.substitute({'SUBJECT': order_name, 
            'INVOICE': order_name,
            'NAME': origin.name, 
            'STREET': origin.street,
            'AREACODE': origin.areacode,
            'CITY': origin.city, 
            'MAIL_S': origin.mail, 
            'PHONE': origin.phone,
            'TABLE': tabledata, 
            'TOTWOSHIP': totalWithoutShipping, 
            'PARTSHIP': locale.format("%.3f", b.totalShipping, True, True),
            'TOTALSHIP': locale.format("%.2f", ShippingTotal, True, True),
            'PERCENTAGE': locale.format("%.3f",(100*b.totalShipping/ShippingTotal)),
            'TOTAL': locale.format("%.2f", round(b.finalSum,2), True, True),
            'KTO': origin.kto,
            'BLZ': origin.blz,
            'BANK': origin.bank,
            'GLOBTOTAL': locale.format("%.3f", globalSum, True, True),
            'RNAME': b.name,
            'RCO': rco,
            'RSTREET': rstreet,
            'RCITY': rcity})
            outputs["bill." + b.name + ".tex"] = content_out
            logging.info("bill " + b.name + " done")
            
            #id, einzelpreis, anzahl, gesamtpreis
            #subtotal, versananteil von gesamt und total
            #"zwischensumme 42€ (17% der gesamten bestellung), versandanteil 5,90*17%=..."
            #getrennt nach shops
            
        
        
    subdirectory=""
    if (settings.subdir):
        subdirectory = os.path.splitext(sys.argv[1])[0] + "-output"
        try:
            #TODO ordentlich machen
            os.mkdir(subdirectory)
        except OSError as e:
            logging.info("directory seems to exist")
        subdirectory = subdirectory + os.sep
        #create .gitignore in subdir --> is irrelevant for dev
        f=open(subdirectory+".gitignore",'w')
        f.write("*")
        f.close()
    basename=subdirectory+sys.argv[1]+"-output-"        
    for (filename, content) in outputs.items():
        if (not ('.' in filename)):
            filename = filename + ".txt"
        f=open(basename+filename,'w')
        f.write(content)
        f.close()
        
    if settings.billing:
        logging.info("trying to build all latexfiles")
        if (settings.subdir):
            os.chdir(subdirectory)
        for files in os.listdir("."):
            if files.endswith(".tex"):
                for i in range(0, 2):
                    proc=subprocess.Popen(shlex.split('pdflatex "' + files + '"'))
                    proc.communicate()
                    #achtung bei non-subdir: baut ALLES (weniger greedy machen?)
