class DHCPClient:

	def __init__(self, jsonObj):
		keys = jsonObj.keys()
		try:
			self.ip = jsonObj["ip"]
			self.reserved = jsonObj["reserved"]
			self.mac = jsonObj["mac"]
			if "hostname" in keys:
				self.hostname = jsonObj["hostname"]
			else:
				self.hostname = None
			if "vci" in keys:
				self.vendor = jsonObj["vci"]
			else:
				self.vendor = None
			self.expires = jsonObj["expire_time"]
			self.interface = jsonObj["interface"]
			self.type = jsonObj["type"]
		except KeyError:
			print("DHCP item missing an attribute for some reason")

	def __str__(self):
		if self.hostname:
			return self.ip+": "+self.hostname+" ["+self.mac+"]"
		elif self.vendor:
			return self.ip + ": *" + self.vendor + "* [" + self.mac + "]"
		else:
			return self.ip + ": ? [" + self.mac + "]"