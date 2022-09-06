import json
import socket
import time

import requests
import logging
import urllib3

from DNSEntry import DNSEntry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from DHCPClient import DHCPClient

logging.basicConfig(level=logging.DEBUG,
					format="%(asctime)s %(levelname)-8s %(message)s",
					datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger("FGD2DNS")

fortigateIP = "10.0.1.1"
client = requests.Session()

# Login request
useCSRFToken = False # whether to use the username/password to login (doesn't fucking work) or a generated API token
payload = "username=admin&secretkey=insertpasswordhere"
apiKeyParams = {"access_token": "accessTokenHere"} # created by "New API User"
# base headers otherwise the response takes forever
baseHeaders = {"User-Agent": "Mozilla/5.0 (X11; CrOS x86_64 12871.102.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.141 Safari/537.36"}
headers = {}

def doAuth():
	global headers
	r = client.post("https://" + fortigateIP + "/logincheck", data=payload, headers=baseHeaders, verify=False)

	if r.status_code==200:
		# Retrieve session id. Add to HTTP header for future messages
		headers = baseHeaders
		headers.update(r.headers)
		headers["X-CSRFTOKEN"] = r.cookies["ccsrftoken"]
		# allthough as we're using a client session, we shouldn't need to do this
	else:
		log.error("Failed to authenticate!")

def getReservedDHCP():
	r = client.get("https://"+fortigateIP+"/api/v2/monitor/system/dhcp", params=apiKeyParams, verify=False)
	if r.status_code != 200:
		log.error("Failed to get DHCP list, status code: %d" % (r.status_code))
		if r.status_code==401:
			#todo: raise unauthorised error
			pass
		return None
	resp = json.loads(r.text)
	rawList = resp["results"]
	log.info("Got DHCP list (length %d)"%(len(rawList)))
	dhcpList = []
	for c in rawList:
		dhcpList.append(DHCPClient(c))
	log.info("Parsed DHCP entries")
	return dhcpList

def getDNS(zone="local"):
	global headers
	r = client.get("https://" + fortigateIP + "/api/v2/cmdb/system/dns-database", params=apiKeyParams, verify=False)
	if r.status_code != 200:
		log.error("Failed to get DNS list, status code: %d" % (r.status_code))
		if r.status_code == 401:
			# todo: raise unauthorised error
			pass
		return None
	resp = json.loads(r.text)["results"]
	zoneObj = [x for x in resp if x["name"]==zone]
	if len(zoneObj)!=1:
		log.error("Failed to find/found too many DNS databases for zone %s"%(zone))
		return None
	zoneObj = zoneObj[0]

	num = len(zoneObj["dns-entry"])

	dnsList = []
	for e in zoneObj["dns-entry"]:
		dnsList.append(DNSEntry(e, zoneObj["ttl"]))
	log.info("Parsed DNS entries")
	return dnsList, num

#NB this needs to put ALL the DNS entries back in, it can't just change single items :/
def putDNS(entries,zone="local"):
	reqObj = []
	for e in entries:
		reqObj.append(e.toFortigate())
	log.debug("Trying to write: "+json.dumps({"dns-entry":reqObj}))
	r = client.put("https://"+fortigateIP+"/api/v2/cmdb/system/dns-database/"+zone, json={"dns-entry":reqObj}, params=apiKeyParams, verify=False)
	if r.status_code!=200:
		log.error("Failed to put DNS entries, status code: %d"%(r.status_code))
		log.debug(r.text)
		return
	log.info("Sucessfully pushed %d DNS entries"%(len(entries)))

def putReverseDNS(unfiltered_entries):
	entries = list(dict.fromkeys(unfiltered_entries))
	if len(unfiltered_entries) != len(entries):
		log.warn("There were duplicate IPs")
	reqObj = []
	id = 1
	for e in entries:
		if e.type=="ipv4" and "10." in e.ip:
			reqObj.append(e.toFortigateReverse(id))
			id += 1
			print("%s %s" % (e.ip, e.hostname))
	log.debug("Trying to write: " + json.dumps({"dns-entry": reqObj}))
	# first blank out the entire list because fortigate will otherwise complain as it adds our list that items already exist (even through we're replacing the whole thing as we CAN'T edit in place)
	r = client.put("https://" + fortigateIP + "/api/v2/cmdb/system/dns-database/Reverse-DNS", json={"dns-entry": []}, params=apiKeyParams, verify=False)
	if r.status_code != 200:
		log.error("Failed to remove old reverse-DNS entries, status code: %d",r.status_code)
		log.debug(r.text)
		return
	log.info("Cleared old reverse-DNS entries")
	r = client.put("https://" + fortigateIP + "/api/v2/cmdb/system/dns-database/Reverse-DNS", json={"dns-entry": reqObj}, params=apiKeyParams, verify=False)
	if r.status_code != 200:
		log.error("Failed to put reverse-DNS entries, status code: %d",r.status_code)
		log.debug(r.text)
		return
	log.info("Sucessfully pushed %d reverse-DNS entries" % (len(entries)))

def generateNewDNS(dhcpList, oldDNSList):
	nextId = 1 #DNSEntry.findFirstFreeId(oldDNSList)
	newDNS = []
	updates = False
	for d in dhcpList:
		if d.type!="ipv4":
			log.warn("Unable to currently deal with ipv6 DHCP entries")
			continue
		if d.hostname:
			# see if DNS already contains an entry for the hostname
			oldEntry = DNSEntry.containsHostname(d.hostname, oldDNSList)
			if oldEntry:
				#log.info("Found hostname with old ip: %s",str(oldEntry))
				oldDNSList.remove(oldEntry)
				if oldEntry.type!="ipv4":
					log.error("Unable to currently deal with ipv6 DNS entries")
					newDNS.append(oldEntry)
					continue
				if oldEntry.ip != d.ip:
					log.info("%s has updated ip to %s (from %s)", d.hostname, d.ip, oldEntry.ip)
					#if "10.99" in d.ip:
					#	log.info("Ignoring DMZ IP changes for hostname - probably pesky IoT things with the same hostname")
					#else:
					updates = True
				oldEntry.ip = d.ip
				if DNSEntry.containsHostname(d.hostname, newDNS) is None:
					newDNS.append(oldEntry)
				else:
					log.warn("Skipping duplciate hostname (existing): %s %s",d.hostname, d.ip)
			else:
				if DNSEntry.containsHostname(d.hostname, newDNS) is None:
					updates = True
					newDNS.append(DNSEntry(ip=d.ip, hostname=d.hostname)) # remember to add/renumber id's later
					#log.info("New entry: %s, %s", d.hostname, d.ip)
				else:
					log.warn("Skipping duplciate hostname (new): %s %s",d.hostname, d.ip)
		else:
			log.info("Skipping DHCP entry %s: missing hostname"%(d.ip))
			oldEntry = DNSEntry.containsIP(d.ip, oldDNSList)
			if oldEntry is not None:
				log.info("Removing DNS entry as DHCP has no hostname")
				del oldDNSList[oldDNSList.index(oldEntry)]


	# append any old DNS entries that haven't been updated
	for d in oldDNSList:
		if d.type!="ipv4":
			newDNS.append(d) # hope there's no multiple entries...
		else:
			#log.info("Got old (non updated) %s",str(d))
			if DNSEntry.containsIP(d.ip, newDNS) is None:
				log.info("Appending (non updated) %s %s", d.hostname, d.ip)
				newDNS.append(d) # only append the ip if we haven't encountered a duplicate

	# now re-assign id's
	newDNS.sort(key=lambda item: socket.inet_aton(item.ip))
	for d in newDNS:
		d.id = nextId
		nextId += 1

	return newDNS, updates


def logout():
	r = client.post("https://"+fortigateIP+"/logout")

if useCSRFToken:
	doAuth()
dhcpList = getReservedDHCP()
oldDNS, oldNum = getDNS()
newDNS, areUpdates = generateNewDNS(dhcpList, oldDNS)
if oldNum != len(newDNS) or areUpdates:
	log.info("New DNS entries detected")
	putDNS(newDNS)
	putReverseDNS(newDNS)
else:
	log.info("No new DNS entries detected")

logout()
logging.shutdown()
