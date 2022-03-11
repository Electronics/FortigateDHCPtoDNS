class DNSEntry:
	def __init__(self, jsonObj=None, ip=None, ipv6=None, type="ipv4", hostname=None, enabled=True, id=None, ttl=3600):
		if jsonObj is not None:
			try:
				self.ip = jsonObj["ip"]
				self.ipv6 = jsonObj["ipv6"] if jsonObj["ipv6"]!="::" else None
				self.type = "ipv4" if len(self.ip)>0 or self.ipv6=="::" else ("ipv6" if len(self.ipv6)>0 else "")
				self.hostname = jsonObj["hostname"]
				self.enabled = True if jsonObj["status"]=="enable" else False
				if jsonObj["ttl"] != 0:
					self.ttl = jsonObj["ttl"]
					self.ttlNonDefault = True
				else:
					self.ttl = ttl
					self.ttlNonDefault = False
				self.id = jsonObj["id"]
			except KeyError:
				print("DNS item missing an attribute for some reason")
		else:
			self.ip = ip
			self.ipv6 = ipv6
			self.type = type
			self.hostname = hostname
			self.enabled = enabled
			self.ttl = ttl
			self.ttlNonDefault = False
			self.id = id

	def __str__(self):
		return self.ip+": "+self.hostname

	def toFortigate(self):
		d = {}
		d["hostname"] = self.hostname
		d["id"] = self.id
		if self.type=="ipv4":
			d["ip"] = self.ip
			d["type"] = "A"
		else:
			d["ipv6"] = self.ipv6
			d["type"] = "AAAA"
		if self.ttlNonDefault:
			d["ttl"] = self.ttl
		d["status"] = "enable" if self.enabled else "disabled"
		return d

	def toFortigateReverse(self, id):
		# reverse DNS entry
		d = {}
		d["hostname"] = self.hostname+"."
		d["id"] = id
		d["ip"] = self.ip
		d["type"] = "PTR"
		return d

	@classmethod
	def containsIP(cls, ip, dnsList):
		for d in dnsList:
			if d.type=="ipv4" and d.ip==ip:
				return d
			elif d.ipv6==ip:
				return d
		return None

	@classmethod
	def containsHostname(cls, host, dnsList):
		for d in dnsList:
			if d.hostname == host:
				return d
		return None

	@classmethod
	def findFirstFreeId(cls, dnsList):
		used = 0
		for d in dnsList:
			if d.id > used:
				used = d.id
		return used+1