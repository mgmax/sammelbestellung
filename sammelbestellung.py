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

locale.setlocale(locale.LC_ALL, '')


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
        return "<Buyer, name '"+ str(self.name) + "', basket  "+str(self.basket)+" >"
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
        f=open(sys.argv[1])
    except IOError:
        sys.stderr.write("Error opening file.\n")
        sys.stderr.write("usage: '"+sys.argv[0]+"' order_file\n")
        sys.exit(1)
    class ParseContext:
        def __init__(self):
            self.shop=None
            self.buyer=None
            self.basket=pricefetcher.Basket()
    context=ParseContext()
    buyers=[]
    origin=None # for From-field of mail
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
                logging.debug("finished old buyer from context: " + str(context.buyer))
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
            logging.debug("Command " + str(cmd) + ", arg " + str(arg))
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
                #deprecated
                if (origin!=None):
                    raise Exception("you may not specify more than one origin")
                origin = Origin(mail=arg)
            elif cmd=="originname":
                if (origin==None):
                    origin = Origin()
                origin.name = arg
            elif cmd=="originmail":
                if (origin==None):
                    origin = Origin()
                origin.mail = arg
            elif cmd=="originstreet":
                if (origin==None):
                    origin = Origin()
                origin.street = arg
            elif cmd=="origincity":
                if (origin==None):
                    origin = Origin()
                origin.city = arg
            elif cmd=="originac":
                if (origin==None):
                    origin = Origin()
                origin.areacode = arg                
            elif cmd=="originkto":
                if (origin==None):
                    origin = Origin()
                origin.kto = arg
            elif cmd=="originblz":
                if (origin==None):
                    origin = Origin()
                origin.blz = arg
            elif cmd=="originbank":
                if (origin==None):
                    origin = Origin()
                origin.bank = arg    
            elif cmd=="originphone":
                if (origin==None):
                    origin = Origin()
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
        
    
    
        
    totalBasket.fetchPrices()
    for b in buyers:
        b.basket.takePricesFrom(totalBasket)
    subtotalSums=totalBasket.shopSums()
    totalSums={}
    #class ShopInfo:
        #def __init__(self):
            #self.factor=None
            #self.shipping=None
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
        logging.critical("Checksums do not match!")
        sys.exit(1)
    
    logging.info("generating outputs")
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
    if (origin==None):
        origin = Origin()
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
