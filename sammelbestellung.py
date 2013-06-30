#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
# Sammelbestellungs-Abrechnung
# https://github.com/mgmax/sammelbestellung
# 
# (c) 2013 Max Gaukler <development@maxgaukler.de>
#
# some parts based on Part-DB autoprice - price fetcher
# (c) 2009 Michael Buesch <mb@bu3sch.de>
#
# Licensed under the GNU/GPL version 2 or (at your option) any later version
"""

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

defaultHttpHeader = \
	{ "User-Agent": "Mozilla/5.0 (X11; U; Linux ppc; en-US; rv:1.9.0.12) " +\
		       "Gecko/2009072221 Iceweasel/3.0.6 (Debian-3.0.6-1)",
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language": "en-us,en;q=0.5",
	"Accept-Charset": "ISO-8859-1,utf-8;q=0.7,*;q=0.7",
	"Keep-Alive": "300",
	"Connection": "keep-alive"}

# Setup automatic cookie handling and default headers, just like in a browser
def httpSetup():
	global cj
	
	cj = cookielib.CookieJar()
	opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
	opener.addheaders = defaultHttpHeader.items()
	urllib2.install_opener(opener)

# http GET
def httpGet(url, headers={}):
	return httpRequest(url, None, headers)

# http POST
def httpPost(url, data={}, headers={}):
	return httpRequest(url, urllib.urlencode(data), headers)

def httpRequest(url, data=None, headers={}):
	# sleep random time
	#time.sleep(random.uniform(0.4,1.8))
	req=urllib2.Request(url, data, headers)
	return urllib2.urlopen(req)
#def getCookie

def httpCookies():
	return enumerate(cj);

def httpPrintAllCookies():
	r=[]
	for index, cookie in httpCookies():
		r += [ [cookie.domain, cookie.name, cookie.value] ]
	print r
		#import inspect
		#print inspect.getmembers(cookie)




def httpCookieValue(domain, name):
	for index, cookie in httpCookies():
		if (cookie.domain == domain and cookie.name == name):
			return urllib.unquote(cookie.value)
	# not found
	raise KeyError()

reicheltSessionId = None
pollinSessionId = None

# generic price finding error
class NoPriceError(Exception): pass

# special price finding errors
class UnknownShopError(NoPriceError): pass
class PriceParseError(NoPriceError): pass
class BasketParseError(NoPriceError): pass
class UnknownPartError(NoPriceError): pass


def removeChars(string, template):
	for t in template:
		string = string.replace(t, "")
	return string



# basic price fetcher - inherit this class for each shop
class PriceFetcher(object):
	name=None
	
	
	def __init__(self):
		# info - should not really be inside PriceFetcher - maybe rename it to Shop?
		self.factor=None
		self.shipping=None
		pass
	
	def _emptyBasket(self):
		raise NotImplementedError()
	
	def emptyBasket(self):
		try:
			emptiedBasket = self._emptyBasket()
		except NotImplementedError:
			logging.warning("pricefetcher has no _emptyBasket function")
			return
			
		# check that emptied basket is empty
		if self._parseSum(emptiedBasket) != 0:
			raise Exception("Failed to empty the basket")
	
	# exprot the basket in a format suitable to upload it to the webpage and place the order
	# return: [ file content, ".fileEnding" ]
	def exportNativeBasket(self,b):
		s=""
		for p in b.parts():
			s += "%s; %d\n" % (p.partNr, p.count)
		return [s,".csv"]
	
	def getSessionId(self):
		raise NotImplementedError()
	
	# fetch the total price (not the price per item!) for <count> items of <partNr>
	def fetchTotalPrice(self, partNr, count):
		raise NotImplementedError()

# open a debug shell - code from phihag at http://stackoverflow.com/questions/5597836/how-can-i-embedcreate-an-interactive-python-shell-in-my-python-program
def debugShell():
	import readline # optional, will allow Up/Down/History in the console
	import code
	vars = globals().copy()
	vars.update(locals())
	shell = code.InteractiveConsole(vars)
	shell.interact()

class PriceFetcherReichelt(PriceFetcher):
	_sessionID = None
	
	# change these (and some functions) for another shop
	name="reichelt.de"
	parseSumRegexp=r".+Summe: <span id=\"basketsum\">(?P<price>\d+,\d+)</span> &euro;.+"
	parseSumDecimal=","
	parseSumIgnore="."

	
	
	
	def _newSessionId(self):
		httpGet("http://www.reichelt.de/")
		reicheltSessionId = httpCookieValue(".reichelt.de","Reichelt_SID")
		return reicheltSessionId
	
	def getSessionId(self):
		if self._sessionID != None:
			return self._sessionID
		logging.debug("Fetching " + self.name + " session ID")
		self._sessionID=self._newSessionId()
		if self._sessionID == None:
			raise Exception("session ID was None!")
		return self._sessionID
	
	def _basketURL(self):
		return "http://www.reichelt.de/Warenkorb/index.html?SID=" + urllib.quote_plus(self.getSessionId()) + ";ACTION=5;SORT=USER;"
	
	def _insertBasket(self, partNr, count):
		return httpPost(self._basketURL(), { "DirectInput_[1]": partNr.encode("iso8859-1"), "DirectInput_count_[1]": str(count), "insert": "WK aktualisieren"}).read()
	
	def _emptyBasket(self):
		return httpPost(self._basketURL(), {"Delete[_all_]": "WK löschen"}).read()
	
	# get sum from basket HTML page
	def _parseSum(self,basket):
		basket = removeChars(basket, "\r\n")
		r = re.compile(self.parseSumRegexp)
		m = r.match(basket)
		if not m:
			raise NoPriceError("Failed to parse basket sum")
		price = m.group("price")
		price = price.replace(self.parseSumIgnore, "")
		price = price.replace(self.parseSumDecimal, ".")
		
		try:
			price = float(price)
		except ValueError:
			raise NoPriceError("Got price, but it doesn't seem to be a float number: %s" % price)
		return price
	

	
	def fetchTotalPrice(self, partNr, count):
		# Fetch the price for a count of item from Reichelt.
		# The Reichelt search feature is not reliable, so we abuse
		# the shopping basket for our purpose. We put the item into the basket,
		# read the basket sum and remove it from the basket again.
		
		# Put the item into the shopping basket
		
		basket=self._insertBasket(partNr, count)
		
		# Parse the shipping basket sum
		price=self._parseSum(basket)
		
		if price == 0:
			raise UnknownPartError("Failed to put the item into the basket") # Most likely caused by invalid partNr
		
		# Remove the item from the shopping basket
		self.emptyBasket()
		
		return price
	

	
	def fetchBasket(self, url):
		global s
		s=httpGet(url).read()
		s = removeChars(s, "\r\n")
		#debugShell()
		# find cart table and get individual cell texts
		table=match('.*<table[^<>]*summary="MyCatchMyBasket"[^<>]*>(.*?)</table>.*',s)
		rows=[]
		for row in multiMatch('<tr[^<>]*>(.*?)</tr>',table):
			cols=[]
			for col in multiMatch('<td[^<>]*>(.*?)</td>', row):
				cols += [col]
			rows += [cols]
		# 
		# 
		parts=[]
		
		def removeTags(s):
			return re.sub('<.*?>','',s)
		
		def getText(s):
			return unescapeHtml(removeTags(s))
		
		def getCount(s):
			try:
				return int(re.match('.*<input[^<>]* value="([0-9]*)"[^<>]*/>.*', s).group(1))
			except:
				raise Exception("cannot get count")
		
		for row in rows:
			#print row[1], row[4]
			try:
				parts += [Part(self.name, getText(row[1]), getCount(row[5]))]
			except:
				raise BasketParseError("trouble parsing basket. Are all articles available?")
		
		self._emptyBasket()
		return parts
	
	def exportNativeBasket(self,b):
		s=""
		for p in b.parts():
			s += "%s;%d\n" % (p.partNr, p.count)
		return [s.encode("iso8859-15"),".csv"]


class PriceFetcherFarnell(PriceFetcherReichelt):
	name="de.farnell.com"
	parseSumRegexp=r".+Warenwert:[^&]*(\d+,\d+) &euro;.+"
	parseSumDecimal=","
	parseSumIgnore="."
	
	def __init__(self):
		httpGet("http://de.farnell.com/");
		pass
	
	# TODO handle requestId=...
	def _basketURL(self):
		return "http://de.farnell.com/jsp/shoppingCart/shoppingCart.jsp"
	
	def _newSessionId(self):
		return ""
	
	def _insertBasket(self, partNr, count):
		requestData = "_dyncharset=UTF-8&%2Fpf%2Fcommerce%2FCartHandler.punchOutSuccessURL=orderReviewPunchOut.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.punchOutSuccessURL=+&%2Fpf%2Fcommerce%2FCartHandler.setOrderSuccessURL=..%2FshoppingCart%2FshoppingCart.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.setOrderSuccessURL=+&%2Fpf%2Fcommerce%2FCartHandler.setOrderErrorURL=..%2FshoppingCart%2FshoppingCart.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.setOrderErrorURL=+&%2Fpf%2Fcommerce%2FCartHandler.addLinesSuccessURL=..%2FshoppingCart%2FshoppingCart.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.addLinesSuccessURL=+&reqFromCart=true&_D%3AreqFromCart=+&topUpdateCart=Warenkorb+aktualisieren&_D%3AtopUpdateCart=+&%2Fpf%2Fcommerce%2FCartHandler.moveToPurchaseInfoErrorURL=..%2FshoppingCart%2FshoppingCart.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.moveToPurchaseInfoErrorURL=+&%2Fpf%2Fcommerce%2FCartHandler.moveToPurchaseInfoSuccessURL=..%2Fcheckout%2FpaymentMethod.jsp&_D%3A%2Fpf%2Fcommerce%2FCartHandler.moveToPurchaseInfoSuccessURL=+&_D%3AcontinueWithShipping=+&lineNote=" \
		+ urllib.quote_plus(partNr) + "&_D%3AlineNote=+&lineQuantity=" + urllib.quote_plus(str(count)) + \
		"&_D%3AlineQuantity=+&%2Fpf%2Fcommerce%2FCartHandler.addItemCount=4&_D%3A%2Fpf%2Fcommerce%2FCartHandler.addItemCount=+&lineNote=&_D%3AlineNote=+&lineQuantity=1&_D%3AlineQuantity=+&lineNote=&_D%3AlineNote=+&lineQuantity=1&_D%3AlineQuantity=+&lineNote=&_D%3AlineNote=+&lineQuantity=1&_D%3AlineQuantity=+&lineNote=&_D%3AlineNote=+&lineQuantity=1&_D%3AlineQuantity=+&emptyLinesA=10&_D%3AemptyLinesA=+&emptyLinesB=10&_D%3AemptyLinesB=+&_D%3AaddEmptyLines=+&_D%3AclearBlankLines=+&_DARGS=%2Fjsp%2FshoppingCart%2Ffragments%2FshoppingCart%2FcartContent.jsp.cart"
		
		httpRequest("http://de.farnell.com/jsp/checkout/paymentMethod.jsp?_DARGS=/jsp/shoppingCart/fragments/shoppingCart/cartContent.jsp.cart", requestData)
		# TODO catch exception when count < minimum count (then the wrong price is returned!)
		return httpGet("http://de.farnell.com/jsp/shoppingCart/shoppingCart.jsp").read()
	
	def _emptyBasket(self):
		# TODO... ugly crap
		raise NotImplementedError()
		#2097803
		

class PriceFetcherRS(PriceFetcherReichelt):
	name="de.rs-online.com"
	parseSumRegexp=r'.+Position(en)?:\s*(?P<price>[\d\.,]*) €.+'
	parseSumDecimal=","
	parseSumIgnore="."
	
	def __init__(self):
		httpGet("http://de.rs-online.com/web/ca/Warenkorb/");
		pass
	
	def _basketURL(self):
		return ""
	
	def _newSessionId(self):
		return ""
	
	def _insertBasket(self, partNr, count):
		raise NotImplementedError()
		# WARNING kaputt
		requestData="AJAXREQUEST=quickOrderForm%3Aj_id243&quickOrderForm=quickOrderForm&quickOrderForm%3AquickStockNo_0=" + str(partNr) + "&quickOrderForm%3AquickQty_0=" + str(count) + "&quickOrderForm%3AquickStockNo_1=&quickOrderForm%3AquickQty_1=&quickOrderForm%3AquickStock"
		httpRequest("http://de.rs-online.com/web/qa/Schnellbestellung/",requestData).read();
		basket=httpGet("http://de.rs-online.com/web/ca/Warenkorb/").read()
		print basket
		return basket
	
	def _emptyBasket(self):
		# WARNING: TODO
		raise NotImplementedError()
		return httpGet("http://de.rs-online.com/web/cart/shoppingCart.html?method=removeAllItems&mediaCode=").read()
	
	# export the basket in a format suitable to upload it to the webpage and place the order
	def exportNativeBasket(self,b):
		s=""
		for p in b.parts():
			s += "%s, %d\n" % (p.partNr, p.count)
		return [s,".txt"]

# TODO rework this to use httpGet() etc.
class PriceFetcherPollin(PriceFetcher):
	name="pollin.de"

	def getSessionId(self):
		global pollinSessionId

		if pollinSessionId is not None:
			return pollinSessionId

		logging.debug("Fetching Pollin session ID")
		for i in range(0, 5): # Try five times.
			http = httplib.HTTPConnection("www.pollin.de")
			http.request("GET", "/shop/index.html")
			resp = http.getresponse()
			c = resp.getheader("Set-Cookie")
			if c:
				m = re.compile(r'PHPSESSID=(\w+).*').match(c)
				if m:
					pollinSessionId = m.group(1)
					break
		if pollinSessionId is None:
			print "Failed to get Pollin session ID"
			sys.exit(1)

		return pollinSessionId

	def fetchTotalPrice(self, partNr, count):
		# Fetch the price for an item from Pollin.
		# We abuse the shopping basket for our purpose. We put the item into the
		# basket read the basket sum and remove it from the basket again.
		if not partNr:
			raise UnknownPartError("No part number")

		partNr = partNr.split("-")
		if len(partNr) == 1:
			wkz = ""
			bestellnr = partNr[0]
		elif len(partNr) == 2:
			wkz = partNr[0]
			bestellnr = partNr[1]
		else:
			raise UnknownPartError("Invalid part number format (must be  00-000 000  or  000 000)")
		wkz = removeChars(wkz, "\r\n\t ")
		bestellnr = removeChars(bestellnr, "\r\n\t ")

		# Put the item into the shopping basket
		http = httplib.HTTPConnection("www.pollin.de")
		body = "do_anzahl_0=" + urllib.quote_plus(str(count)) + "&do_wkz_0=" + urllib.quote_plus(wkz) +\
		"&do_bestellnr2_0=" + urllib.quote_plus(bestellnr)
		header = defaultHttpHeader.copy()
		header["Host"] = "www.pollin.de"
		header["Cookie"] = "PHPSESSID=" + self.getSessionId() + "; pollincookie=1"
		header["Content-Type"] = "application/x-www-form-urlencoded"
		header["Content-Length"] = str(len(body))
		http.request("POST", "/shop/warenkorb.html HTTP/1.1", body, header)
		basket = http.getresponse().read()
		basket = removeChars(basket, "\r\n")

		# Remove the item from the shopping basket
		body = "remoteAction=deleteRemote&type=basket&" +\
		"items=%5B%7B%22artnrKurz%22%3A%22" + bestellnr + "%22%2C%22" +\
		"menge%22%3A%221%22%2C%22selected%22%3Atrue%2C%22itemRow%22%3A%220%22%7D%5D"
		header["Content-Length"] = str(len(body))
		http.request("POST", "/shop/ajax.html HTTP/1.1", body, header)
		http.getresponse() # discard result
		
		# TODO testen ob wirklich 0 Artikel im Warenkorb
		
		# Parse the shipping basket sum
		# This always says "1 Artikel" because multiple pieces of the same article count as one
		r = re.compile(r".+<small>1 Artikel: (\d[\.\d]*,\d\d) &euro;</small>.+")
		m = r.match(basket)
		if not m:
			raise PriceParseError("Failed to parse Pollin basket sum") # Most likely caused by invalid partNr
		price = m.group(1)
		
		
		# convert german to english number format: (1.000.000,00 -> 1000000.00)
		# replace . with ,
		price = price.replace(".", "").replace(",",".")
		
		try:
			price = float(price)
		except ValueError:
			raise PriceParseError( "Got price, but it doesn't seem to be a float number: %s" % price)
		

		return price
	
	def exportNativeBasket(self,b):
		# format this to be run with xdotool (emulates keystrokes)
		def xdotool_format(s):
			r=""
			for c in s:
				r += "xdotool key "
				if c=="\t":
					r += "Tab"
				else:
					r += c
				r += "\n"
			return r
		
		s=""
		for p in b.parts():
			partNr=p.partNr
			if "-" in partNr:
				partNr=partNr.split("-")[1]
			partNr=removeChars(partNr," ")
			s += "%d\t\t%s\t" % (p.count, partNr)
		
		return ["#!/bin/sh\n" + xdotool_format(s), ".type.sh"]

shops = [ PriceFetcherReichelt, PriceFetcherRS, PriceFetcherPollin ]


def fetchPrice(shopName, partNr, count):
	logging.debug("Fetching price for %s: %s x \"%s\"" % (shopName,count, partNr))
	count=int(count)
	
	if not partNr:
		raise UnknownPartError("No part number given")
	
	shop = shopByName(shopName)
	
	if not shop:
		raise UnknownShopError("Unknown Shop %s" % shopName)
	
	price=None
	try:
		price = shop.fetchTotalPrice(partNr, count)/count
		if price==None:
			raise NoPriceError("Got 'None' price")
	except NoPriceError, e:
		logging.error(e)
		logging.error("for shop: '%s', part %sx '%s')" % (str(shopName), str(count), str(partNr)))
		sys.exit(1)
	
	logging.debug("Got price for %s: %d x \"%s\" = %.3f" % (shopName,count, partNr,price))
	return price

def shopClassByName(shopName):
	for s in shops:
		if s.name == shopName:
			return s
	# shop not found!
	knownShops=[]
	for s in shops:
		knownShops += [s.name]
	raise UnknownShopError("Unknown shop '%s', known shops are: %s" % (str(shopName), str(knownShops)))

shopInstances = {}

def shopByName(shopName):
	try:
		return shopInstances[shopName]
	except KeyError:
		shopInstances[shopName]=shopClassByName(shopName)()
		return shopInstances[shopName]


class Part(object):
	def __init__(self, shop, partNr, count, price=None):
		self.shop=shop
		self.partNr=partNr
		self.count=int(count)
		self.price=price
	
	def __str__(self):
		r="<Part: shop '%s', part '%s', count '%d', price per item " % (self.shop, self.partNr, self.count)
		if (self.price is not None):
			r += "'%.3f'>" % self.price
		else:
			r += "[None]>"
		return r
		
	def __repr__(self):
		return self.__str__()
	
	def fetchPrice(self):
		self.price=fetchPrice(self.shop, self.partNr, self.count)


def match(r,s):
	return re.compile(r).match(s).group(1)

def multiMatch(r,s):
	return re.compile(r).findall(s)

# convert entities like &#45; to characters
# TODO add named entities like nbsp etc.
def unescapeHtml(s):
	# &#45; to ASCII 45
	def unescape8bit(match):
		return chr(int(match.group(1)))
	s=re.sub('&#([0-9][0-9]);',unescape8bit,s)
	# &#181; to µ
	def unescapeUnicode(match):
		## TODO ugly hack treating unicode as normal string - convert everything else to unicode and remove "encode"
		return unichr(int(match.group(1),10))
	s=re.sub("&#([0-9]+);",unescapeUnicode,s)
	return s


class Basket(object):
	def __init__(self):
		self._parts=[]
	
	def __str__(self):
		return "<Basket, parts " + str(self._parts) +  ">"
	
	def add(self,x):
		if isinstance(x, Part):
			x=[x]
		
		if not isinstance(x, list):
			raise TypeError("argument is not a Part or a list of Parts!")
		
		# merge in new list
		for i in x:
			found=False
			for j in self._parts:
				if (j.shop==i.shop and j.partNr == i.partNr):
					# we already have this part, increase count
					j.count += i.count
					found=True
					break
			if found:
				continue
			# we do not have this part yet, just add it to the list
			self._parts += [ copy.copy(i) ]
	
	def parts(self):
		return copy.deepcopy(self._parts)
	
	def fetchPrices(self):
		logging.info("Fetching prices")
		for p in self._parts:
			p.fetchPrice()
	
	# list of shops
	def shops(self):
		shops=[]
		for p in self._parts:
			if not p.shop in shops:
				shops+=[p.shop]
		return shops
	
	# sum for one shop
	def shopSum(self, shop):
		s=0
		for p in self._parts:
			if (p.shop==shop):
				s+=p.price*p.count
		return s
	
	# separate sum for each shop
	def shopSums(self):
		r={}
		for s in self.shops():
			r[s]=self.shopSum(s)
		return r
	
	# sum for all shops
	def totalSum(self):
		for p in self._parts:
			s+=p.price*p.count
		return s
	
	# store the prices from another basket
	# use case: in a collective order, many people buy 1 piece which costs 2€ each if you order one, but only 1€ each if you order ten.
	# you then build one collective basket, do collectiveBasket.fetchPrices() and then takePricesFrom(collectiveBasket)
	def takePricesFrom(self, basket):
		for my_part in self._parts:
			for other_part in basket.parts():
				if my_part.shop==other_part.shop and my_part.partNr==other_part.partNr:
					my_part.price = other_part.price
	
	# export baskets in a format suitable to load them into the webpage and place the order
	# returns: { shopName: [ fileContents, ".fileEnding" ], ... }
	def exportNativeBaskets(self):
		r={}
		for shop in self.shops():
			b=Basket()
			for p in self._parts:
				if p.shop != shop:
					continue
				b.add(p)
			r[shop]=shopByName(shop).exportNativeBasket(b)
		return r

class Buyer:
	def __init__(self,name=None,mail=None,basket=None):
		self.basket=basket
		if self.basket==None:
			self.basket=Basket()
		self.name=name
		self.mail=mail
		if self.mail==None:
			self.mail="NOMAIL"
		self.shopFinalSums={}
		self.shopShipping={}
		self.totalShipping=None
		self.finalSum=None
	def __str__(self):
		return "<Buyer, name '"+ str(self.name) + "', basket  "+str(self.basket)+" >"
	def __repr__(self):
		return str(self)
	
# needed for From-Field of mail	
class Origin:
	def __init__(self,mail=None):
		self.mail=mail
		if self.mail==None:
			self.mail="John Doe <john.doe@example.org>"
	def __str__(self):
		return self.mail
	def __repr__(self):
		return(self)

try:
	reload(sys)
	sys.setdefaultencoding("utf8")
	# Setup automatic cookie handling, just like in a browser
	httpSetup()
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
		sys.stderr.write("Error opening file.")
		sys.stderr.write("usage: '"+sys.argv[0]+"' order_file")
	class ParseContext:
		def __init__(self):
			self.shop=None
			self.buyer=None
			self.basket=Basket()
	context=ParseContext()
	buyers=[]
	origin=None # for From-field of mail
	lines=f.readlines() + [""] # add empty line at end
	for line in lines:
		line=removeChars(line,"\r\n")
		logging.debug("Parsing line: "+line)
		cmdMatch=re.match("^!([a-z]+) (.*)$",line)
		itemMatch=re.match("^([0-9]+)[;\t] *([^;\t]*)[;\t] *([^;\t]*[^;\t ]) *$",line)
		shortItemMatch=re.match("^([0-9]+)[;\t] *([^;\t]*[^;\t ]) *$",line)
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
			elif cmd=="basket":
				context.basket.add(shopByName(context.shop).fetchBasket(arg))
			elif cmd=="warning":
				logging.warning("Warning: " + line)
			elif cmd=="setfactor":
				if ("*" in arg): # possible syntax: 1*2*3*4 (multiplied factors)
					factor=1
					for i in arg.split("*"):
						factor *= float(i)
				else: # simple syntax: 1234 (one factor)
					factor=float(arg)
				shopByName(context.shop).factor=factor
			elif cmd=="setshipping":
				shopByName(context.shop).shipping=float(arg)
			elif cmd=="origin":
				if (origin!=None):
					raise Exception("you may not specify more than one origin")
				origin = Origin(mail=arg)
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
			context.basket.add(Part(shop=shop,partNr=partNr,count=count))
		else:
			raise Exception("Parse error with line " + line)
		
	totalBasket=Basket()
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
		if shopByName(shop).factor is None or shopByName(shop).shipping is None:
			raise Exception("no factor or shipping set for shop %s. Please at least put !shop shopname, !setfactor 1 and !setshipping 0 for each shop at the beginning of your file" % str(shop))
		totalSums[shop]=s*shopByName(shop).factor + shopByName(shop).shipping
		print "Shop " + shop + " subtotal " + str(s) + ". * factor " + str(shopByName(shop).factor) + " + shipping " + str(shopByName(shop).shipping) + " = Total " + str(totalSums[shop])
	
	
	for b in buyers:
		b.finalSum=0
		b.totalShipping=0
		for (shop,s) in totalSums.items():
			subtotal=b.basket.shopSum(shop)
			shipping=b.basket.shopSum(shop)/subtotalSums[shop]*shopByName(shop).shipping
			total=subtotal*shopByName(shop).factor + shipping
			if total != 0:
				logging.info("buyer " + b.name + ", shop "+ shop + " : " + str(total) + " subtotal  (" + str(subtotal) + " * factor " + str(shopByName(shop).factor) + " + shipping  " + str(shipping))
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
		outputs["report"] += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-shopByName(shop).shipping,shopByName(shop).shipping)
	
	outputs["report"] += header("details")
	outputs["report"] +=  "name\tcount\traw price each\tfactor\tpartNr\tshop\n"
	for (shop, s) in b.shopFinalSums.items():
		outputs["report"] += "\t\t%.2f\t1\t<Shipping>\t%s\n" % (shopByName(shop).shipping,shop)
	for b in buyers:
		for p in b.basket.parts():
			outputs["report"] +=  "%s\t%d\t%.3f\t%.4f\t%s\t%s\n" % (b.name,p.count,p.price,shopByName(p.shop).factor,p.partNr,p.shop)
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
	msg['Subject'] = "Sammelbestellung " + sys.argv[1]
	text = "Hallo, die Sammelbestellung wurde losgeschickt."
	text += "Bitte überweist gemäß der untenstehenden Tabelle an folgendes Konto."
	text += header("total sum")
	text += "Name\ttotal\t(items+shipping)\n"
	for b in buyers:
		text += "%s\t%.2f\t(%.2f+%.2f)\n" % (b.name, b.finalSum,b.finalSum-b.totalShipping,b.totalShipping)
	text += header("shops")
	text += "Shop\tSum with shipping\t(items + shipping)\n"
	for (shop, s) in totalSums.items():
		text += "%s\t%.2f\t(%.2f+%.2f)\n" % (shop, s,s-shopByName(shop).shipping,shopByName(shop).shipping)
	msg.attach(MIMEText(text.encode('utf-8'), 'plain', 'UTF-8'))
	outputs["mail.eml"] = str(msg)
    
    
	basename=sys.argv[1]+"-output-"
	for (filename, content) in outputs.items():
		if (not ('.' in filename)):
			filename = filename + ".txt"
		f=open(basename+filename,'w')
		f.write(content)
		f.close()
	print "Success!"
	sys.exit(0)
	
	# TODO Mindeststückzahl-Error bei Rei? und RS

except Exception, e:
	#pass
	#print "Error:"
	#print e
	#sys.exit(1)
	raise
