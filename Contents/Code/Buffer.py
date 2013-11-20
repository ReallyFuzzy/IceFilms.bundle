import cerealizer
import uuid
import os
import socket
from urllib2 import HTTPError


class BufferManager(object):

	ITEMS_KEY = "BUFFER_ITEMS_KEY"
	RUN_KEY = "BUFFER_RUN_KEY"
	DOWNLOAD_KEY = "BUFFER_DOWNLOAD_KEY"
	INSTANCE = None
	
	@staticmethod
	def instance():
			
		# FIXME: Should be synchronised.
		if (BufferManager.INSTANCE is None):
			Log("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
			Log("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
			Log("CREATING INSTANCE")
			Log("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
			Log("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
		
			BufferManager.INSTANCE = BufferManager(doNotManuallyInstantiate=False)
			
		return BufferManager.INSTANCE
	
	def __init__(self, doNotManuallyInstantiate=True):
	
		if (doNotManuallyInstantiate):
			raise Exception("Object should be treated as singleton. Use Buffer.instance() to get instance")
		
		Log("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
		Log("INIT")
		Log(self.items())
		
		self.bufferItems = {}
	
	def hasItem(self, url):
	
		return self.item(url) is not None
		
	def isReady(self, url):
	
		item = self.item(url)
		return item is not None and item['currentStatus'] == "FINISHED"
		
	def isActive(self, url):
	
		return self.hasItem(url) and   self.bufferItem(url).isActive()
		
	def fileLoc(self, url):
	
		item = self.item(url)
		if (item is not None and item['outputFile'] is not None):
			return item['outputFile']
		else:
			return None
			
	def adtlInfo(self, url):
	
		if (self.hasItem(url) and "adtlInfo" in self.item(url)):
			 return cerealizer.loads(self.item(url)["adtlInfo"])
		else:
			return None
		
	def create(self, url, adtlInfo):
	
		# Create the bufferItem which will do the work.
		self.bufferItems[url] = BufferItem({})
		
		# And also save its state to Plex's Dict() so that it can share state info
		# from the thread doing the downloading back to the rest of the system.
		self.items()[url] = self.bufferItems[url].dict()
		
		# And add a serialised version of any additional info caller wanted us to store.
		self.items()[url]["adtlInfo"] = cerealizer.dumps(adtlInfo)
		
	def addSource(self, url, sources):
	
		bufferItem = self.bufferItem(url)
		bufferItem.addSource(sources)
		return
	
	def resume(self, url, savePath):
	
		self.bufferItem(url).makeStartable()
		Dict.Save()
		self.launch(savePath)

	def stop(self, url):
	
		Thread.Block("DOWNLOAD_OK")
		
		# Wait up to 10 secs to see if the thread correctly picks up the signal.
		res = Thread.Wait("DOWNLOAD_OK", 10)

		Dict.Save()

		return res

	def remove(self, url):
	
		self.bufferItem(url).cleanData()
		del self.bufferItems[url]
		del self.items()[url]
		Dict.Save()
		
	def stopAndRemove(self, url):
	
		self.stop(url)
		self.remove(url)
	
	def nextSource(self, url):
	
		Thread.Block("CURRENT_SOURCE_OK")
		
		# Wait up to 5 secs to see if the thread correctly picks up the signal.
		return Thread.Wait("CURRENT_SOURCE_OK", 5)
		
		
	def stats(self, url, itemDuration=None):
	
		item = self.item(url)
		stats = {}
		
		stats['status'] = item['currentStatus']
		
		if (item['fileSize'] is not None and item['fileSize'] > 0):
			stats['fileSize'] = self.humanizeFileSize(item['fileSize'])
		else:
			stats['fileSize'] = "-"
			
		stats['percentComplete'] = "-"
		stats['downloadRemaing'] = "-"
		
		if (item['totalDownloaded'] is not None and item['totalDownloaded'] > 0):
		
			stats['downloaded'] = self.humanizeFileSize(item['totalDownloaded'])
			Log(item)
			stats['downloadRemaining'] = self.humanizeFileSize(item['fileSize'] - item['totalDownloaded'])
			Log(stats)
			if (item['percentComplete'] is not None):
				stats['percentComplete'] = round(item['percentComplete'] * 100, 1)
			
		else:
			stats['downloaded'] = '-'
			
		if (item['totalDownloadTime'] is not None and item['totalDownloadTime'] > 0):
			stats['timeElapsed'] = self.humanizeTimeLong(int(item['totalDownloadTime']), "seconds", 3)
		else:
			stats['timeElapsed'] = '-'
			
		stats["avgRate"] = self.humanizeFileSize(item['avgRate']) + "/s"

		# Some defaults.
		stats["curRate"] = "-"
		stats["timeRemaining"] = "-"
		stats["timeRemainingShort"] = "-"
		stats["provider"] = "-"
		stats["safeToPlay"] = False
		
		if (item['currentStatus'] == "ACTIVE" and item['currentSource'] is not None):
			
			stats["curRate"] = self.humanizeFileSize(item['curRate']) + "/s"
			stats["timeRemaining"] = self.humanizeTimeLong(int(item['timeRemaining']), "seconds", 3)
			stats["timeRemainingShort"] = self.humanizeTimeShort(int(item['timeRemaining']), "s", 2)
			stats["provider"] = item['sources'][item['currentSource']]['provider']
						
			#Log("PC: %s, PR: %s, BR: %s (%s)" % (item['percentComplete'], item['percentRemaining'], item['bytesRemaining'],  self.humanizeFileSize(item['bytesRemaining'])))
			#Log("TRAR: %s (%s)" % (item['timeRemainingAvgRate'], self.humanizeTime(int(item['timeRemainingAvgRate']), "seconds")))
			#Log("TRCR: %s (%s)" % (item['timeRemainingCurRate'], self.humanizeTime(int(item['timeRemainingCurRate']), "seconds")))
			#Log("TR: %s (%s)" % (item['timeRemaining'], self.humanizeTime(int(item['timeRemaining']), "seconds")))

			if (itemDuration is not None):
			
				itemDurationRemaining = item['percentRemaining'] * itemDuration
				# See if item is safe to play (i.e: we've already buffered enough of the
				# item such that it will finish downloading before we catchup to it).
				# Note the majoration of timeRemaining by 5% to give ourselves a little more
				# safe room.
				stats["safeToPlay"] = itemDurationRemaining > (item['timeRemaining'] * 1.05)
		
		return stats
		
	def item(self, url):
	
		if url in self.items():
			return self.items()[url]
		else:
			return None
				
	def items(self):
	
		if (BufferManager.ITEMS_KEY not in Dict):
			Dict[BufferManager.ITEMS_KEY] = {}
			
		return Dict[BufferManager.ITEMS_KEY]
		
	def bufferItem(self, url):
	
		# Do we have a bufferItem's state but not the object itself?
		# If so, re-create the object.
		if (self.item(url) is not None and url not in self.bufferItems):
			self.bufferItems[url] = BufferItem(self.items()[url])
				
		if (url in self.bufferItems):
			return self.bufferItems[url]
		else:
			raise Exception("Can't access bufferItem with id %s has it doesn't exist" % url)
	
	def humanizeFileSize(self, num):
	
		for x in ['bytes','KB','MB','GB']:
			if num < 1024.0 and num > -1024.0:
				return "%3.1f%s" % (num, x)
			num = num / 1024.0
		return "%3.1f%s" % (num, 'TB')
	
	def humanizeTimeShort(self, amount, units, precision):
	
		names = [('s', 's'),
				 ('m', 'm'),
				 ('h', 'h'),
				 ('d', 'd'),
				 ('w', 'w'),
				 ('m', 'm'),
				 ('y', 'y')]
				 
		result = self.humanizeTime(names, amount, units)
				
		# Only show 2 most relevant scales.
		resStr = ""
		for item in result[0:precision]:
			resStr = resStr + str(item[0]) + item[1]
		
		return str(resStr)
    	
	def humanizeTimeLong(self, amount, units, precision):
	
		names = [('sec', 'seconds'),
				 ('min', 'minutes'),
				 ('hour', 'hours'),
				 ('day', 'days'),
				 ('week', 'weeks'),
				 ('month', 'months'),
				 ('year', 'years')]
				  
		result = self.humanizeTime(names, amount, units)
				
		# Only show 2 most relevant scales.
		resStr = ""
		for item in result[0:precision]:
			resStr = resStr + str(item[0]) + " " + item[1] + " "
		
		return str(resStr).strip()
		
	def humanizeTime(self, names, amount, units):
	
		INTERVALS = [1, 60, 3600, 86400, 604800, 2419200, 29030400]			
					 
		result = []
	
		unit = map(lambda a: a[1], names).index(units)
		# Convert to seconds
		amount = amount * INTERVALS[unit]
		for i in range(len(names)-1, -1, -1):
			a = amount / INTERVALS[i]
			if a > 0:
				result.append( (a, names[i][1 % a]) )
				amount = amount - (a * INTERVALS[i])
				
		return result
		
	# Launch the overall download manager in a separate thread.
	# Launch through here to ensure only one instance ever runs.
	def launch(self, savePath):
	
		Dict.Save()
		semaphore = Thread.Semaphore(BufferManager.RUN_KEY)
		if (semaphore.acquire(False)):
			Log("*******************************")
			Log("Launch buffering")
			Thread.Create(self.run, savePath=savePath)
		else:
			Log("*******************************")
			Log("Did not Launch buffering as already running.")
				
	def run(self, savePath):
	
		try:
		
			while (True):
			
				# Whilst we have items to download....
				items = self.items()
				itemToDownload = None
				
				for itemKey in self.items():
					if (self.bufferItem(itemKey).isStartable()):
						itemToDownload = itemKey
						break
				
				if (itemToDownload):
					semaphore = Thread.Semaphore(BufferManager.DOWNLOAD_KEY, int(Prefs["max_concurrent_buffers"]))
					if (semaphore.acquire(False)):
						Log("*******************************")
						Log("Launching download thread....")
						Thread.Create(self.download, item=itemToDownload, savePath=savePath)
						Thread.Sleep(5)
					else:
						# Looks like the queue is currently full.
						# Wait X seconds before trying again.
						Log("*******************************")
						Log("Download queue is full. Sleeping.")
						Thread.Sleep(15)
				else:
					# We don't currently have any items to download.
					# Check again in X seconds.
					Log("*******************************")
					Log("No more items to download. Sleeping.")
					break
			
		finally:
			Log("*******************************")
			Log("Releasing.........")
			semaphore = Thread.Semaphore(BufferManager.RUN_KEY)
			semaphore.release()
			
			
	def download(self, item, savePath):
	
		try:
			Log("*******************************")
			Log("Starting download for item: " + str(item))
			Thread.Unblock("DOWNLOAD_OK")
			Thread.Unblock("CURRENT_SOURCE_OK")
			self.bufferItem(item).download(savePath)
			Log("*******************************")
			Log("Ending download for item: " + str(item))
			
		finally:
			semaphore = Thread.Semaphore(BufferManager.DOWNLOAD_KEY)
			semaphore.release()
	
	
class BufferItem(object):

	PLEX_URL = "http://127.0.0.1:32400"
	BLOCK_SIZE = 8192
	
	def __init__(self, item):
	
		self.blockTargetTime = 0
		self.curDownloaded = 0
		self.curDownloadTime = 0
		self.lastDownloadTime = 0
		
		# Item is a dictionary backed by Plex's Dict().
		# We're using it to share state back to other parts of the system.
		self.item = item
		
		if (len(item) == 0):
		
			item['id'] = str(uuid.uuid4())
			item['sources'] = {}
			item['outputFile'] = None
			item['currentSource'] = None
			item['currentStatus'] = "ADDED"
			
			item['curRate'] = 0
			item['avgRate'] = 0
			item['curRateTarget'] = 0
			
			item['fileSize'] = 0
			item['totalDownloaded'] = 0
			item['totalDownloadTime'] = 0
			
			item['percentComplete'] = 0.0
			item['percentRemaining'] = 0.0
			item['timeRemaining'] = 0
			item['timeRemainingCurRate'] = 0
			item['timeRemainingAvgRate'] = 0
			item['bytesRemaining'] = 0
			
		elif self.isActive():
		
			# We've just been restored from stored state.
			# We can't be active yet.
			item['currentStatus'] = 'SUSPENDED'
			    
	def dict(self):
	
		return self.item
		
	def download(self, savePath):
	
		# Whilst we're not finished, haven't been told to stop and still have sources to try...
		while (
			self.item['currentStatus'] != "STOPPED"
			and self.item['currentStatus'] != "FINISHED"
			and self.item['currentStatus'] != "NO_SOURCE"
		):
		
			# Based on the given rate, time each block should take.
			self.blockTargetTime = 0
			if (self.item['curRateTarget'] > 0):
				self.blockTargetTime = 1.0 / (float(self.item['curRateTarget']) / BufferItem.BLOCK_SIZE)
		
			self.pickSource()
			self.lastDownloadTime = None
			Dict.Save()
			
			if not self.okToDownload():
				break
			
			if self.item['outputFile'] is None:
				self.item['outputFile'] = os.path.join(savePath, self.item['id'])
	
			outputPath = self.item['outputFile']
					
			if (self.item["currentSource"] is not None):
			
				source = self.item['sources'][self.item['currentSource']]
				
				self.item['currentStatus'] = "ACTIVE"
				
				# Opener for the file.
				opener = urllib2.build_opener()
				
				# Check if we're resuming a download.
				source["totalDownloaded"] = 0
				self.item['totalDownloaded'] = source["totalDownloaded"]
				
				fdOpenFlags = "w+"
				if (os.path.isfile(outputPath)):
				
					source["totalDownloaded"] = os.path.getsize(outputPath)
					self.item['totalDownloaded'] = source["totalDownloaded"]
					
					fdOpenFlags = "a+"
					opener.addheaders = [('Range','bytes=%s-' % source["totalDownloaded"])]
					
				fd = None
				outputObj = None
				
				try:
					stream = opener.open(source["finalUrl"])
					meta = stream.info()
					
					# If we already have a number of bytes downloaded, the returned size will
					# be the amount remaining and not the total file size. In that case, assume
					# the previously set size is correct.
					if (source["totalDownloaded"] == 0):
						source["size"] = int(meta.getheaders("Content-Length")[0])
							
					# Copy these from the source so they remain available for stats purposes after
					# we've finished dealing with the source.
					self.item['fileSize'] = source["size"]
					self.item['totalDownloaded'] = source["totalDownloaded"]
					
					# Long winded way to get a file handle since Plex doesn't trust us with open().
					fd = os.open(outputPath, os.O_RDWR|os.O_CREAT )
					outputObj = os.fdopen(fd, fdOpenFlags)
					
					while True:

						blockStart = Datetime.Now()
						
						buffer = stream.read(BufferItem.BLOCK_SIZE)
						
						blockDiff = Datetime.Now() - blockStart
						blockTime = blockDiff.seconds + blockDiff.microseconds / 1000000.0
						
						if not buffer:
							break
							
						outputObj.write(buffer)
						downloaded = len(buffer)
						
						self.calculateMetrics(downloaded)
						
						#Log("************************ Got some data for: " + self.item['id'])
						
						# See if we've received any threading events and process as appropriate.
						if (not Thread.Wait("CURRENT_SOURCE_OK",0)):
							Log("************************ Should be changing source...")
							source['used'] = True
							self.item['currentStatus'] = "ADDED"
							self.item['currentSource'] = None
							Thread.Unblock("CURRENT_SOURCE_OK")
							break
						
						if (not self.okToDownload()):
							break
						
						# Did our block hit its target time. If not, sleep the difference.
						if (self.blockTargetTime > 0 and self.blockTargetTime > blockTime):
							Log("************************ Wait Throttling....")
							Thread.Sleep(self.blockTargetTime - blockTime)
					
				except HTTPError, ex:
					Log("************************ Download Error...")
					Log(ex)
					self.item['currentStatus'] = "SOURCE_ERROR"
					self.item['currentSource'] = None
					source['used'] = True
					
				finally:
				
					if (outputObj is not None and not outputObj.closed):
						outputObj.close()
						
					if (stream is not None):
						stream.close()
						# Bug in Python means socket don't get closed straight away....
						Thread.Sleep(2)
						
				if (
					self.item['currentSource'] is not None and
					self.item['fileSize'] == self.item['totalDownloaded']
				):
					self.item['currentSource'] = None
					self.item['currentStatus'] = "FINISHED"
				
			else:
			
				self.item['currentStatus'] = "NO_SOURCE"
		
	def okToDownload(self):
	
		if (not Thread.Wait("DOWNLOAD_OK",0)):
			Log("************************ Stoping download... ")
			Thread.Unblock("DOWNLOAD_OK")
			self.item['currentStatus'] = "STOPPED"
			return False
		else:
			return True

	def calculateMetrics(self, downloadedLength):
	
		source = self.item['sources'][self.item['currentSource']]
		
		source['totalDownloaded'] = source['totalDownloaded'] + downloadedLength
		self.item['totalDownloaded'] = source['totalDownloaded']
		
		now =  Datetime.Now()
		timeDiff = timedelta()
		if self.lastDownloadTime:
			timeDiff = now - self.lastDownloadTime
		self.lastDownloadTime = now

		diff = timeDiff.seconds * 1000000 + timeDiff.microseconds 
		
		if diff:
		
			self.item['totalDownloadTime'] = self.item['totalDownloadTime'] + float(diff) / 1000000
			
			# Average rate of the buffer over the lifetime of the operation.
			self.item['avgRate'] = source['totalDownloaded'] / float(self.item['totalDownloadTime'])
						
			self.curDownloadTime = self.curDownloadTime + diff
			self.curDownloaded = self.curDownloaded + downloadedLength
			
			# Recalculate complete stats every 2 seconds to get a more stable average.
			if (self.curDownloadTime > 2 * 1000 * 1000):
			
				# The current rate averaged over the last 2 seconds.
				self.item['curRate'] = round(self.curDownloaded / (float(self.curDownloadTime) / 1000000),3)
				self.curDownloaded = 0
				self.curDownloadTime = 0
								
				# Esitmate time remaining by weighing average speed so far and current speed
				# inversely to the current percentage complete. So, has a file gets nearer to
				# completion, more weight will be put on the current download speed whilst at
				# the start more weight will be put on the average spped so far.
				self.item['percentComplete'] = source['totalDownloaded'] / float(source['size'])
				self.item['percentRemaining'] = 1 - self.item['percentComplete']
				self.item['bytesRemaining'] = source['size'] - source['totalDownloaded']
								
				self.item['timeRemainingAvgRate'] = self.item['bytesRemaining'] / self.item['avgRate']
				self.item['timeRemainingCurRate'] = self.item['bytesRemaining'] / self.item['curRate']
				
				# Weight time remaining based on percentComplete.
				self.item['timeRemaining'] = (
					(self.item['timeRemainingCurRate'] * self.item['percentRemaining']) +
					(self.item['timeRemainingAvgRate'] * self.item['percentComplete'])
				)
	
	
	def pickSource(self):
	
		Log("CCCCCCCCCCCCCCCCCCCCCCCCCCCCC %s" % self.item['currentStatus'])
		Log(self.item["currentSource"])
		
		if (
			(
				self.item['currentStatus'] == 'STOPPED' or
				self.item['currentStatus'] == 'SUSPENDED'
			)
			and self.item["currentSource"] is not None
		):
		
			Log("*** Picking buffer source based on previous run")
			
			self.item['currentStatus'] = "RESOLVING_SOURCE"
			
			source = self.item['sources'][self.item["currentSource"] ]
			self.getRealSource(source)
			
			if (source["finalUrl"] is not None):
			
				# Get the size of the current item and make sure it's the same.
				request = urllib2.urlopen(source["finalUrl"])
				request.get_method = lambda : 'HEAD'
				meta = request.info()
				
				size = int(meta.getheaders("Content-Length")[0])
				
				if (source["size"] != size):
					# Looks like the item is gone? What do we do?
					Log("*** File Size has changed since item was stopped from %s to %s. Dumping source and starting over." % (source['size'], size))
					source["size"] = 0
					source["totalDownloaded"] = 0
					self.item["currentSource"] = None
					
				else:
					Log("Source is still available and the same size. Continuing buffer")
					return self.item["currentSource"]
				
			else:
			
				# Looks like the item is gone? What do we do?
				Log("*** Source that was previously used is no longer available. Dumping source and starting over.")
				source["size"] = 0
				source["totalDownloaded"] = 0
				self.item["currentSource"] = None
				
		
		self.cleanData()
		self.item['currentStatus'] = "RESOLVING_SOURCE"
		
		source = None		
		for sourceKey in self.item['sources']:
		
			source = self.item['sources'][sourceKey]
			if (not 'used' in source):
				self.getRealSource(source)
				if (source["finalUrl"] is not None):
					self.item["currentSource"] = sourceKey
					break
		
		Log("Picked source: %s" % source)
		Log(self.item['sources'])
		return source
		
	def getRealSource(self, item):
				
		# Not all sources will sucessfully return a finalURL...
		try:
		
			mediaObjects = URLService.MediaObjectsForURL(item["url"])
			partUrl = mediaObjects[0].parts[0].key
	
			# Manually resolve any indirect URLs..
			if mediaObjects[0].parts[0].key.find("indirect=1") >= 0:

				# Get final url. Note the addition of the client platform...
				# That's so the Putlocker / Sockshare provider can do its magic.
				request = urllib2.Request(
					BufferItem.PLEX_URL + partUrl,
					None, 
					{ 'X-Plex-Client-Platform':Client.Platform }
				)
				response = urllib2.urlopen(request).read()

				responseObj = XML.ElementFromString(response)		
				partUrl = responseObj.xpath("//Part/@key")[0]
				
			item["finalUrl"] = str(partUrl)
						
		except Exception, ex:
			Log("*******************************")
			Log(str(ex))
			item["finalUrl"] = None
			item["size"] = 0
				
	def addSource(self, sources):
	
		for source in sources:
			source['size'] = 0
			source['finalUrl'] = None
			self.item['sources'][source['url']] = source
		
	def cleanData(self):
	
		self.item['fileSize'] = 0
		self.item['totalDownloaded'] = 0
		self.item['totalDownloadTime'] = 0
		
		if self.item['outputFile'] is not None and os.path.isfile(self.item['outputFile']):
			os.remove(self.item['outputFile'])
	
	def makeStartable(self):
	
		# All sources have been tried unsuccesfully previously. Try them again.
		if self.item['currentStatus'] == 'NO_SOURCE':
		
			for sourceKey in self.item['sources']:
				if ('used' in self.item['sources'][sourceKey]):
					del self.item['sources'][sourceKey]['used']
					
			self.item['currentStatus'] = 'ADDED'
			
		else:
			self.item['currentStatus'] = 'SUSPENDED'
		
	
	# Return whether this current BufferItem can currently start its download.
	def isStartable(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus != 'FINISHED'
			and currentStatus != 'RESOLVING_SOURCE'
			and currentStatus != 'ACTIVE'
			and currentStatus != 'NO_SOURCE'
			and currentStatus != 'STOPPED'
		)
		

	def isQueued(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus == 'ADDED'
			or currentStatus == 'SUSPENDED'
		)
		
	# Returns whether this BufferItem is currently trying to buffer something.
	def isActive(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus == 'RESOLVING_SOURCE'
			or currentStatus == 'ACTIVE'
		)
		
	def isStopped(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus == 'STOPPED'
		)
		
	def isFinished(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus == 'FINISHED'
		)
		
	def isNoSource(self):
	
		currentStatus = self.item['currentStatus']
		
		return (
			currentStatus == 'NO_SOURCE'
		)
	
	def __str__(self):
	
		return str(self.item)
		