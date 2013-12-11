import cerealizer
import uuid
import os
import socket
import shutil
import datetime

from HTTPBetterErrorProcessor import HTTPBetterErrorProcessor
from urllib2 import HTTPError, URLError


		
###################################################################################################
# BUFFER MANAGER
###################################################################################################

class BufferManager(object):

	ITEMS_KEY = 'BUFFER_ITEMS_KEY'
	RUN_KEY = 'BUFFER_RUN_KEY'
	DOWNLOAD_KEY = 'BUFFER_DOWNLOAD_KEY'
	KEEPALIVE_KEY = 'BUFFER_KEEPALIVE_KEY'
	DOWNLOAD_ACTIVE_KEY = 'BUFFER_DOWNLOAD_ACTIVE_KEY'
	
	INSTANCE = None
	
	@staticmethod
	def instance():
			
		# FIXME: Should be synchronised.
		if (BufferManager.INSTANCE is None):
			Log('XXX THREAD XXX: CREATING INSTANCE')
		
			BufferManager.INSTANCE = BufferManager(doNotManuallyInstantiate=False)
			
		return BufferManager.INSTANCE
	
	def __init__(self, doNotManuallyInstantiate=True):
	
		if (doNotManuallyInstantiate):
			raise Exception('Object should be treated as singleton. Use Buffer.instance() to get instance')
		
		Log('XXX THREAD XXX: INIT')
		Log(self.items())
		
		self.bufferItems = {}
		self.savePath = None
		self.keepAliveUrl = None
	
	def setPrefs(self, savePath, keepAliveUrl):
	
		self.savePath = savePath
		self.keepAliveUrl = keepAliveUrl
		
	def hasItem(self, url):
	
		return self.item(url) is not None
		
	def isReady(self, url):
	
		item = self.item(url)
		return item is not None and item['currentStatus'] == 'FINISHED'
		
	def isActive(self, url):
	
		return self.hasItem(url) and self.bufferItem(url).isActive()
		
	def isQueued(self, url):
	
		return self.hasItem(url) and self.bufferItem(url).isQueued()
		
	def partCount(self, url):
	
		item = self.item(url)
		
		sources = [source for source in item['sources'] if source['status'] == 'FINISHED']
		
		if len(sources) == 1:
			return len(sources[0]['parts'])
	
	def fileLoc(self, url, partIndex):
	
		item = self.item(url)
		
		if item is not None:
		
			sources = [source for source in item['sources'] if source['status'] == 'FINISHED']
			
			if len(sources) == 1:
			
				return sources[0]['parts'][partIndex]['file']
				
	def playURL(self, videoPrefix, url, partIndex):
	
		item = self.item(url)
		
		encodedURL = String.Encode(url)
		
		if item is not None:
		
			sources = [source for source in item['sources'] if source['status'] == 'FINISHED']
			
			if len(sources) == 1:
			
				part = sources[0]['parts'][partIndex]
				
				if ('info' in part):
					return "prebuffer://%s/%s/%s?%s" % (videoPrefix, encodedURL, partIndex, urllib.urlencode(part['info']))
				else:
					return "prebuffer://%s/%s/%s" % (videoPrefix, encodedURL , partIndex)
	
		return None
	
	def adtlInfo(self, url):
	
		if (self.hasItem(url) and 'adtlInfo' in self.item(url)):
			 return cerealizer.loads(self.item(url)['adtlInfo'])
		else:
			return None
		
	def create(self, url, adtlInfo):
	
		# Create the bufferItem which will do the work.
		self.bufferItems[url] = BufferItem({})
		
		# And also save its state to Plex's Dict() so that it can share state info
		# from the thread doing the downloading back to the rest of the system.
		self.items()[url] = self.bufferItems[url].dict()
		
		# And add a serialised version of any additional info caller wanted us to store.
		self.items()[url]['adtlInfo'] = cerealizer.dumps(adtlInfo)
		
	def addSources(self, url, sources):
	
		bufferItem = self.bufferItem(url)
		bufferItem.addSources(sources)
		return
	
	def resume(self, url):
	
		self.bufferItem(url).makeStartable()
		Dict.Save()
		self.launch()

	def stop(self, url):
	
		res = True
		item = self.bufferItem(url)
		
		if (item.isActive()):
		
			Thread.Block('DOWNLOAD_OK_%s' % item.id())
		
			# Wait up to 10 secs to see if the thread correctly picks up the signal.
			res = Thread.Wait('DOWNLOAD_OK_%s' % item.id(), 10)

		item.stop()
		
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
	
	def moveAndRemove(self, url, path):
		
		adtlInfo = self.adtlInfo(url)
		mediaInfo = adtlInfo['mediainfo']
		allOk = True
		item = self.item(url)
		
		sources = [source for source in item['sources'] if source['status'] == 'FINISHED']
			
		if len(sources) == 0:
			return False
			
		parts = sources[0]['parts']
		cnt = 1	
		for part in parts:
				
			src = part['file']
			
			fileName = mediaInfo.file_name
			
			if len(parts) > 1:
				fileName = "%s - part %s" % (fileName, cnt)
				
			# Add a file extension...
			if ('info' in part and 'container' in part['info'] and part['info']['container']):
				fileName = "%s.%s" % (fileName, part['info']['container'].lower())
			else:
				# Give file dummy extension so that Plex picks it up.
				fileName = "%s.%s" % (fileName, 'mov')
			
			# Come up with a pretty file name.
			dest = os.path.join(path, fileName)
		
			Log("*** Moving %s to %s" % (src, dest))
			shutil.move(src, dest)
			
			cnt = cnt + 1
			
		Log("*** Removing pre-buffer item after succesful file move.")
		self.remove(url)
		pass
		
		return
		
	def nextSource(self, url):
	
		itemId = self.item(url)['id']
		
		Thread.Block('CURRENT_SOURCE_OK_%s' % itemId)
		
		# Wait up to 10 secs to see if the thread correctly picks up the signal.
		return Thread.Wait('CURRENT_SOURCE_OK_%s' % itemId, 10)
		
		
	def stats(self, url, itemDuration=None):
	
		item = self.bufferItem(url).stats()
		
		stats = {}
		
		# Some defaults.
		stats['fileSize'] = '-'
		stats['downloaded'] = '-'
		stats['downloadRemaining'] = '-'
		stats['curRate'] = '-'
		stats['avgRate'] = '-'
		stats['percentComplete'] = '-'
		stats['timeElapsed'] = '-'
		stats['timeRemaining'] = '-'
		stats['timeRemainingShort'] = '-'
		stats['provider'] = '-'
		stats['partCount'] = 0
		stats['partCurrent'] = '-'
		
		stats['safeToPlay'] = False
		
		stats['status'] = item['status']
		
		if (item['totalDownloadSize'] is not None and item['totalDownloadSize'] > 0):
			stats['fileSize'] = self.humanizeFileSize(item['totalDownloadSize'])

		if (item['totalDownloaded'] is not None and item['totalDownloaded'] > 0):
			stats['downloaded'] = self.humanizeFileSize(item['totalDownloaded'])
			
		if (
			item['totalDownloadSize'] is not None and item['totalDownloadSize'] > 0 and
			item['totalDownloaded'] is not None and item['totalDownloaded'] > 0
		):
			stats['downloadRemaining'] = self.humanizeFileSize(item['totalDownloadSize'] - item['totalDownloaded'])
			
		if (item['percentComplete'] is not None and item['percentComplete'] > 0):
			stats['percentComplete'] = round(item['percentComplete'] * 100, 1)
					
		if (item['totalDownloadTime'] is not None and item['totalDownloadTime'] > 0):
			stats['timeElapsed'] = self.humanizeTimeLong(int(item['totalDownloadTime']), 'seconds', 3)
		
		if (item['avgRate'] is not None and item['avgRate'] > 0):
			stats['avgRate'] = self.humanizeFileSize(item['avgRate']) + '/s'

		if (item['status'] == 'ACTIVE'):
			
			stats['provider'] = item['provider']
			
			if (item['partCount'] is not None):
				stats['partCount'] = item['partCount']
				
			if (item['partCurrent'] is not None):
				stats['partCurrent'] = item['partCurrent']
			
			if (item['curRate'] is not None and item['curRate'] > 0):
				stats['curRate'] = self.humanizeFileSize(item['curRate']) + '/s'
			
			if (item['timeRemaining'] is not None and item['timeRemaining'] > 0):
				stats['timeRemaining'] = self.humanizeTimeLong(int(item['timeRemaining']), 'seconds', 3)
				stats['timeRemainingShort'] = self.humanizeTimeShort(int(item['timeRemaining']), 's', 2)
			
			if (
				itemDuration is not None and
				item['percentRemaining'] is not None and item['percentRemaining'] > 0
			):
				itemDurationRemaining = item['percentRemaining'] * itemDuration
				# See if item is safe to play (i.e: we've already buffered enough of the
				# item such that it will finish downloading before we catchup to it).
				# Note the majoration of timeRemaining by 5% to give ourselves a little more
				# safe room.
				stats['safeToPlay'] = itemDurationRemaining > (item['timeRemaining'] * 1.05)
		
		return stats
		
	def item(self, url):
	
		if url in self.items():
			return self.items()[url]
		else:
			return None
				
	def items(self):
	
		#Dict[BufferManager.ITEMS_KEY] = {}
		
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
				return '%3.1f%s' % (num, x)
			num = num / 1024.0
		return '%3.1f%s' % (num, 'TB')
	
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
		resStr = ''
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
		resStr = ''
		for item in result[0:precision]:
			resStr = resStr + str(item[0]) + ' ' + item[1] + ' '
		
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
	def launch(self):
	
		Dict.Save()
		semaphore = Thread.Semaphore(BufferManager.RUN_KEY)
		if (semaphore.acquire(False)):
			Log('XXX THREAD XXX: Launch buffering')
			Thread.Create(self.run, savePath=self.savePath, keepAliveUrl=self.keepAliveUrl)
		else:
			Log('XXX THREAD XXX: Did not Launch buffering as already running.')
				
	def run(self, savePath, keepAliveUrl):
	
		try:
						
			while (True):
			
				# Whilst we have items to download....
				items = self.items()
				itemToDownload = None
				
				for itemKey in self.items():
					itemToDownload = self.bufferItem(itemKey)
					if itemToDownload.isStartable():
						break
					else:
						itemToDownload = None
				
				if (itemToDownload):
					Log('XXX THREAD XXX: Allowed up to %s concurrent downloads.' % Prefs['max_concurrent_buffers'])
					semaphore = Thread.Semaphore(BufferManager.DOWNLOAD_KEY, int(Prefs['max_concurrent_buffers']))
					
					if (semaphore.acquire(False)):
					
						# Try to launch keep alive thread.
						if Thread.Semaphore(BufferManager.KEEPALIVE_KEY).acquire(False):
							Log('XXX THREAD XXX: Launching keep alive thread (%s).' % keepAliveUrl)
							Thread.Create(self.keepAlive, url=keepAliveUrl)

						Log('XXX THREAD XXX: Launching download thread....')
						Thread.Create(self.download, itemKey=itemKey, savePath=savePath)
						Thread.Sleep(5)
						
					else:
					
						# Looks like the queue is currently full.
						# Wait X seconds before trying again.
						Log('XXX THREAD XXX: Download queue is full. Sleeping.')
						Thread.Sleep(15)
						
				else:
				
					# We don't currently have any items to download.
					# Check again in X seconds.
					Log('XXX THREAD XXX: No more items to download. Sleeping.')
					break
			
		finally:
			Log('XXX THREAD XXX: Finished buffering.')
			semaphore = Thread.Semaphore(BufferManager.RUN_KEY)
			semaphore.release()
			
			
	def download(self, itemKey, savePath):
	
		try:
			item = self.bufferItem(itemKey)
			
			Log('*** Starting download for item: %s ' % item)
			Thread.Unblock('DOWNLOAD_OK_%s' % item.id())
			Thread.Unblock('CURRENT_SOURCE_OK_%s' % item.id())
			
			# Launch a thread to continually save the Dict in case the plugin gets
			# killed by plex and to poll the plugin to try and prevent the plugin
			# getting killed.
			try:
				item.download(savePath)
			finally:
				Thread.Unblock('DOWNLOAD_OK_%s' % item.id())
				Thread.Unblock('CURRENT_SOURCE_OK_%s' % item.id())
				
		finally:
			Log('*** Ending download for item: %s' % item)
			# Release our download slot.
			Thread.Semaphore(BufferManager.DOWNLOAD_KEY).release()
			
		Log("*** Working out whether to move item on completion.")
		if Prefs['move_finished_to_library'] and item.isFinished():
		
			Log("*** Item is good to be moved.")
			
			key = 'PREBUFFER_AUTO_LOC_MOVIE'
			if self.adtlInfo(itemKey)['mediainfo'].type == 'tv':
				key = 'PREBUFFER_AUTO_LOC_TV'
			
			if key in Dict and Dict[key]:
			
				Log("*** Moving and removing item to %s" % Dict[key])
				self.moveAndRemove(itemKey, Dict[key])

	
	'''
		Periodically save the Dict so that stats are more or less up-to-date should something
		bad happen to our python environment (like getting killed by the Plex server).
		
		Also try to make sure nothing bad happens to our Plex environment by polling a plugin
		provided URL which should keep it alive.
	'''
	def keepAlive(self, url):
		
		sleepCnt = 0
		
		try:
		
			while (True):
			
				# Sleep for 1 minute.
				sleepCnt = sleepCnt + 1
				Thread.Sleep(60)
				
				# Save Dict.
				Dict.Save()
				
				# Has it been more than 10 mins since we last pinged the plugin?
				if (sleepCnt >= 10):
				
					sleepCnt = 0
					
					# Is the signal set indicating download threads are active?
					if not Thread.Wait(BufferManager.DOWNLOAD_ACTIVE_KEY, 0):
					
						# Yup, clear it.
						Thread.Unblock(BufferManager.DOWNLOAD_ACTIVE_KEY)
						
						Log('*** Keep-Alive (%s)!' % url)
						
						# Request ping page from plugin.
						try:
							request = urllib2.Request(url)
							response = urllib2.urlopen(request).read()
						except Exception, ex:
							Log.Exception("*** Error keeping plugin alive.")
							pass
			
					else:
						# Nope. Looks like we're done for the time being.
						Log('*** Nothing to keep-alive. Terminating')
						break
					
		finally:
			Thread.Semaphore(BufferManager.KEEPALIVE_KEY).release()
		
		
###################################################################################################
# BUFFER ITEM
###################################################################################################

'''
Basic class that represents all the information for an item that needs to be buffered.
All information which needs to be persisted across thread relaunch needs to go in item dict which
will get saved in Plex's Dict().

Class / Dict structure:

	BufferItem:
		item: {
			id,
			currentStatus,
			sources: [
				{
					id,
					status,
					provider,
					parts: [
						{
							unresolvedUrl,
							finalUrl,
							size,
							file
						}
					]
				}
			],
			currentSource,
			outputDir,
			curRateTarger,
		},
		blockTargetTime,
		curDownloadStats,
		lastDownloadTime
'''
class BufferItem(object):

	PLEX_URL = 'http://127.0.0.1:32400'
	BLOCK_SIZE = 8192
	
	def __init__(self, item):
	
		self.blockTargetTime = 0
		self.curDownloadStats = []
		self.lastDownloadTime = 0
		self.currentPart = None
		
		# Item is a dictionary backed by Plex's Dict().
		# We're using it to share state back to other parts of the system.
		self.item = item
		
		if (len(item) == 0):
		
			item['id'] = str(uuid.uuid4())
			item['dateAdded'] = datetime.datetime.utcnow()
			item['currentStatus'] = 'ADDED'
			
			item['sources'] = []
			item['currentSource'] = None
			
			item['outputDir'] = None
			
			item['curRateTarget'] = -1
						
		elif self.isActive():
		
			# We've just been restored from stored state.
			# We can't be active yet.
			item['currentStatus'] = 'SUSPENDED'
	
	def id(self):
		
		return self.item['id']
		
	def dict(self):
	
		return self.item
	
	
	'''
		Add different sources for this item.
	'''
	def addSources(self, sources):
	
		Log('*** Adding sources...')
		
		# Create a new source dict for each given source.
		for source in sources:
		
			Log('*** Adding provider as source %s' % source['provider'])
			
			item = {
				'status': 'NEW',
				'id': str(uuid.uuid4()),
				'parts': [],
				'provider': source['provider']
			}
			
			# Each url for the given source gets its own little object.
			# This makes it easier to track multiple part sources.
			for url in source['parts']:
			
				part = {
					'unresolvedUrl': url,
					'finalUrl': None,
					'size': -1,
					'file': None,
					'downloaded': -1,
					'downloadTime': -1,
				}
				
				item['parts'].append(part)
				
			Log('*** Final source: %s' % item)
			self.item['sources'].append(item)
						
		
	'''
		Create the output directory for this bufferItem if it doesn't already exists.
		Will re-throw any exceptions it encounters.
	'''
	def setupOutputDir(self, savePath):
	
		if self.item['outputDir'] is None:
			self.item['outputDir'] = os.path.join(savePath, self.item['id'])
		
		if (not os.path.isdir(self.item['outputDir'])):
			try:
				os.mkdir(self.item['outputDir'])
				Log("*** Set source's outputDir to %s" % self.item['outputDir'])
			
			except Exception, ex:
				Log.Exception('*** Error whilst creating output folder. Aborting download.')
				self.item['outputDir'] = None
				raise ex

	
	'''
		Start downloading this item, or at least try to.
		
		This will loop through each source and each of it's part and tries to download it.
		This will catch thread events to either STOP the download or change source.
	'''
	def download(self, savePath):
	
		self.setupOutputDir(savePath)
		
		# Whilst we're not finished, haven't been told to stop and still have sources to try...
		while (
			self.item['currentStatus'] != 'STOPPED'
			and self.item['currentStatus'] != 'FINISHED'
			and self.item['currentStatus'] != 'NO_SOURCE'
		):
			
			#self.item['curRateTarget'] = 2 * 1024
			
			# Based on the given rate, time each block should take.
			self.blockTargetTime = 0
			if (self.item['curRateTarget'] > 0):
				self.blockTargetTime = 1.0 / (float(self.item['curRateTarget']) / BufferItem.BLOCK_SIZE)
		
			# Pick a source to download item from.
			source = self.pickSource()
			
			# Stop if user has asked to stop download.
			if not self.okToDownload():
				break
									
			if (source is not None):
			
				Log('*** Starting download of source: %s' % source)
				
				self.lastDownloadTime = None
				self.item['currentSource'] = source['id']
				self.item['currentStatus'] = 'ACTIVE'
				source['status'] = 'ACTIVE'
				
				Dict.Save()
													
				# Loop through each part in the source.
				for part in source['parts']:
				
					if (not self.downloadPart(part)):
						break
					
					if not self.okToDownload() or not self.okToUseSource():
						break
				
				if not self.okToUseSource():
					self.cleanSource(source)
					source['status'] = 'USED'
					self.item['currentStatus'] = 'ADDED'
					self.item['currentSource'] = None
				
				# We've jumped out of the loop that tries to download each part for the current
				# source. If anything bad happened, the currentSource should have been set to None.
				if (source['status'] == 'ACTIVE_ERROR'):
				
					# Download of part had succesfully started before encountering error.
					# Retry source.
					Log('*** Download of source %s encountered error whilst actively downloading.' % source)
					source['status'] = 'ACTIVE'
							
					localProblem = True
					cnt = 1
					
					# Check if the problem is local connectivity...
					while localProblem and cnt <= 20:
						cnt = cnt + 1
						try:
							response = urllib2.urlopen('http://www.google.com')
							localProblem = False
						except urllib2.URLError, ex:
							Log("*** Local connectivity broken. Sleeping for 30 secs till next check.")
							Thread.Block(BufferManager.DOWNLOAD_ACTIVE_KEY)
							Thread.Sleep(30)
							
					if (localProblem):
						# We waited for local connectivity to come back for the last 10 mins.
						# It still hasn't. Time to give up. Stop op.
						Log("*** Stopping download as local connectivity seems to be broken.")
						self.stop()
					else:
						# Problem may have been local connectivity issue which is now resolved
						# or a source problem. So, try again with the same source. If the problem
						# was local connectivity, we'll resume. If problem was with source, we'll
						# get a new source.
						Log("*** Local connectivity ok. Retrying source.")
						self.item['currentStatus'] = 'SUSPENDED'					
					
				elif (source['status'] == 'ACTIVE'):
				
					# Check each part has succesfully downloaded.
					allOk = True
					for part in source['parts']:
					
						if (part['size'] == part['downloaded']):
			
							# Store media info about file so that plugin can 
							# generate sane-ish media items.
							part['info'] = plexAnalyseFile(part['file'], "PreBuffer Stats")
							#Log(part['info'])
							
						else:
							allOk = False
							break
					
					if (allOk):
						Log('*** Finished Download...')
						source['status'] = 'FINISHED'
						self.item['currentSource'] = None
						self.item['currentStatus'] = 'FINISHED'
						self.item['dateFinished'] = datetime.datetime.utcnow()
					else:
						self.stop()
				
			else:
			
				Log('*** No more sources...')
				self.item['currentStatus'] = 'NO_SOURCE'
			
			# We've just finished dealing with a source (irrespective of how that turned out.)
			# Save current state back to disk.
			Dict.Save()
	

	'''
		Pick a source for this download. Try to re-pick the last source that was used if this item
		is currently stopped. 
		
		Source picking is done by looping through the sources and picking the first one which 
		hasn't already been used or had an error when previously trying to pick it.
	'''
	def pickSource(self):
	
		Thread.Unblock('CURRENT_SOURCE_OK_%s' % self.id())
		
		Log('*** Picking source. Current Status: %s, Current Source: %s' % (self.item['currentStatus'], self.item['currentSource']))
		
		source = self.getCurrentSource()
		
		if (
			(
				self.item['currentStatus'] == 'STOPPED' or
				self.item['currentStatus'] == 'SUSPENDED'
			)
			and source
		):
		
			Log('*** Picking buffer source based on previous run')
			
			self.item['currentStatus'] = 'RESOLVING_SOURCE'
			
			self.resolveParts(source)
			
			if (not self.okToDownload()):
				return
			
			if (source['status'] == 'READY'):
			
				# Get the size of the parts and make sure they're still the same.
				allOk = True
				
				try:
				
					for part in source['parts']:
						
						if (not self.okToDownload()):
							return
					
						request = urllib2.urlopen(part['finalUrl'])
						request.get_method = lambda : 'HEAD'
						meta = request.info()
						
						size = int(meta.getheaders('Content-Length')[0])
						
						if (part['size'] != size):
							# Looks like the item has changed? Abort.
							Log('*** File Size has changed since item was stopped from %s to %s. Dumping source and starting over.' % (part['size'], size))
							allOk = False
							break
				
				except:
					Log.Exception("*** Error encountered whilst trying to check if previously used source was still the same.")
					allOk = False

				# If we get here and allOk is still set, then we're good
				# to carry on with previous download.
				if (allOk):
					Log('Source is still available and the same size. Continuing buffer')
					return source
					
			else:
			
				# Looks like the item is no longer available. Pick another source.
				Log('*** Source that was previously used is no longer available. Dumping source and starting over.')
		
		# Quick check to see if user has asked us to stop....		
		if (not self.okToDownload()):
			return
				
		# We're either re-picking a source or starting for first time.
		# Either way, clean up object state and any previous download 
		# files we may have left lying around.
		if source:
			Log('*** Cleaning source and dumping it.')
			self.cleanSource(source)
			source = None
			
		self.item['currentStatus'] = 'RESOLVING_SOURCE'
		
		for source in self.item['sources']:
		
			# This can be a bit slooow. 
			# Check to see if user has asked for us to stop.
			if (not self.okToDownload()):
				return
			
			if source['status'] == 'NEW':
			
				self.resolveParts(source)
				
				if (not self.okToDownload()):
					return
				
				if source['status'] == 'READY':
				
					self.sizeParts(source)
				
					if (not self.okToDownload()):
						return
				
					self.item['currentSource'] = source['id']

					Log('*** Picked source: %s' % self.getCurrentSource())
					Log('*** Current Source State: %s' % self.item['sources'])
		
					Dict.Save()
		
					return source
	
	
	'''
		Each part will have been given a provider URL. Need to resolve those to a real video
		URL. Do that by using Plex's URL Services.
	'''
	def resolveParts(self, source):
				
		# Not all sources will sucessfully return a finalURL...
		try:
					
			for part in source['parts']:
			
				if (not self.okToDownload()):
					return

				Log("*** Resolving url for part: %s" % part)
				
				mediaObjects = URLService.MediaObjectsForURL(part['unresolvedUrl'] + "?markPlayed=0")
				partUrl = mediaObjects[0].parts[0].key
	
				# Manually resolve any indirect URLs..
				if mediaObjects[0].parts[0].key.find('indirect=1') >= 0:

					# Get final url. Note the addition of the client platform...
					# That's so the Putlocker / Sockshare provider can do its magic.
					request = urllib2.Request(
						BufferItem.PLEX_URL + partUrl,
						None, 
						{ 'X-Plex-Client-Platform':Client.Platform }
					)
					response = urllib2.urlopen(request).read()

					responseObj = XML.ElementFromString(response)		
					partUrl = responseObj.xpath('//Part/@key')[0]
				
				part['finalUrl'] = str(partUrl)
				
			source['status'] = 'READY'
						
		except Exception, ex:
		
			Log.Exception("*** Error whilst resolving part's final URL.")
			source['status'] = 'ERROR'
				
		
	'''
		Try to set up the size of each part. Can't do this when starting download of part as stats
		rely on knowing size of all parts beforehand.
	'''
	def sizeParts(self, source):
	
		for part in source['parts']:
		
			if (not self.okToDownload()):
				return
				
			try:
				request = urllib2.urlopen(part['finalUrl'])
				request.get_method = lambda : 'HEAD'
				meta = request.info()
					
				part['size'] = int(meta.getheaders('Content-Length')[0])
				Log("*** Set part size to %s" % part['size'])
				
			except Exception, ex:
				Log.Exception("*** Error encountered whilst trying to set part's size")
				part['size'] = -1
			
				
	'''
		Prepare to download a part.
	'''
	def downloadPart(self, part):
		
		Log('*** Starting download of part %s', part)

		startByte = 0
		
		# Create a file for this part.
		if part['file'] is None:
			part['file'] = os.path.join(self.item['outputDir'], "%s.mov" % str(uuid.uuid4()))
			Log('*** Set file loc to %s' % part['file'])
			
		if os.path.isfile(part['file']):
	
			Log('*** Part file already exists. Checking if part complete.')
			
			part['downloaded'] = os.path.getsize(part['file'])
			
			# If the source size equals the file size, then this part is finished.
			# Move onto next part (if any)
			if part['downloaded'] == part['size']:
				Log('*** Part downloaded size == to expected size. Skipping to next part')
				return
			else:
				Log('*** Part is partial download. Trying to resume...')
				startByte = part['downloaded']
			
		else:
			part['downloaded'] = 0
				
		# Save current state before trying risk operation of opening site...
		Dict.Save()
				
		# Make the current part easily accessible.
		# Note that we don't use an entry in the items Dict here like we do for 
		# currentSource as we don't need to preserve this across restarts unlike
		# the currentSource...		
		self.currentPart = part
	
		try:
			self.downloadURL(part['finalUrl'], part['file'], startByte)
			Log('*** Finished / Stopped downloading of part: %s' % part)
			
		except (URLError, HTTPError), ex:
			
			# Something went wrong trying to open URL....
			Log.Exception('*** Download Error...')
			self.getCurrentSource()['status'] = 'ERROR'
			self.item['currentStatus'] = 'SOURCE_ERROR'
			self.item['currentSource'] = None
			return False
			
		except socket.timeout, ex:
		
			# Something went wrong whilst downloading...
			Log.Exception('*** Download Error...')
			self.getCurrentSource()['status'] = 'ACTIVE_ERROR'
			self.item['currentStatus'] = 'SOURCE_ERROR'
			return False
			
		finally:
		
			self.currentPart = None
			
		return True

		
	'''
		Download a URL to a file. Most basic operation here.
	'''
	def downloadURL(self, url, outFile, startByte):
		
		if not self.okToDownload():
			return
		
		Log("*** Starting download of %s to %s" % (url, outFile))
		
		# Opener for the file.
		opener = urllib2.build_opener()
	
		fdOpenFlags = 'w+'

		if startByte > 0:
			opener.addheaders = [('Range','bytes=%s-' % startByte)]
			fdOpenFlags = 'a+'
		
		stream = opener.open(url)
		meta = stream.info()
		
		# Long winded way to get a file handle since Plex doesn't trust us with open().
		fdFlags = os.O_RDWR|os.O_CREAT
		if hasattr(os, 'O_BINARY'):
			Log('*** Setting binary flag.')
			fdFlags = fdFlags | os.O_BINARY
			
		fd = os.open(outFile, fdFlags)
		outputObj = os.fdopen(fd, fdOpenFlags)
	
		try:
		
			while True:
			
				if (not self.okToDownload() or not self.okToUseSource()):
					break
				
				# Let bufferManager know there's an active download and that it should be trying
				# to keep the plugin alive.
				Thread.Block(BufferManager.DOWNLOAD_ACTIVE_KEY)
				
				blockStart = Datetime.Now()
				
				buffer = stream.read(BufferItem.BLOCK_SIZE)
				
				blockDiff = Datetime.Now() - blockStart
				blockTime = blockDiff.seconds + blockDiff.microseconds / 1000000.0
				
				if not buffer:
					break
				
				outputObj.write(buffer)
				downloaded = len(buffer)
				
				self.updateStats(downloaded)
				
				#Log('*** Got some data for source: %s' % source['id'])
			
				# Did our block hit its target time. If not, sleep the difference.
				if (self.blockTargetTime > 0 and self.blockTargetTime > blockTime):
					Log('*** Wait Throttling for %s....' % (self.blockTargetTime - blockTime))
					Thread.Sleep(self.blockTargetTime - blockTime)
	
		finally:
		
			if (outputObj is not None and not outputObj.closed):
				outputObj.close()
				
			if (stream is not None):
				stream.close()
				# Bug in Python means socket don't get closed straight away....
				Thread.Sleep(2)
			
		Log('*** Finished / Stopped downloading of url: %s' % url)

	
	'''
		Are we still OK to download or should we stop as soon as possible?
	'''
	def okToDownload(self):
	
		#Log("*** Waiting on signal: DOWNLOAD_OK_%s" % self.id())
		if (not Thread.Wait('DOWNLOAD_OK_%s' % self.id(), 0)):
			Log('****** Received thread signal to stop download... ')
			self.item['currentStatus'] = 'STOPPED'
			return False
		else:
			return True
			
	'''
		Are we still OK with current source or do we need to switch?
	'''
	def okToUseSource(self):
	
		if (not Thread.Wait('CURRENT_SOURCE_OK_%s' % self.id(), 0)):
			Log('****** Received thread signal to change source...')
			return False
		else:
			return True
		
		
	'''
		Update some key stats for the download.
	'''
	def updateStats(self, bytesReceivedCount):
	
		now =  Datetime.Now()
		timeDiff = timedelta()
		if self.lastDownloadTime:
			timeDiff = now - self.lastDownloadTime
		self.lastDownloadTime = now
		
		diff = timeDiff.seconds * 1000000 + timeDiff.microseconds
		
		# Keep track of time it took to download last 10 chunks.
		while len(self.curDownloadStats) >= 100:
			self.curDownloadStats.pop(0)
				
		self.curDownloadStats.append({'size': bytesReceivedCount, 'time': float(diff) / 1000000  })
		
		self.currentPart['downloaded'] = self.currentPart['downloaded'] +  bytesReceivedCount
		self.currentPart['downloadTime'] = self.currentPart['downloadTime'] + float(diff) / 1000000

	
	'''
		Generate some stats for the current item.
	'''
	def stats(self):
	
		# Calculate download stats....
		source = self.getCurrentSource()
		
		stats = {
			'totalDownloadSize': -1,
			'totalDownloaded': -1,
			'totalDownloadTime': -1,
			'avgRate': -1,
			'percentComplete': -1,
			'percentRemaining': -1,
			'bytesRemaining': -1,
			'timeRemainingAvgRate': -1,
			'timeRemainingCurRate': -1,
			'timeRemaining': -1,
			'avgRate': -1,
			'curRate': -1,
			'partCount': -1,
			'partCurrent': -1,
		}
		
		stats['status'] = self.item['currentStatus']
		
		if (source is not None):
		
			stats['provider'] = source['provider']

			# Total file size to download and how many bytes downloaded so far. 
			# Annoyingly, Plex dosen't expose sum()		
			for part in source['parts']:
				if 'size' in part:
					stats['totalDownloadSize'] = stats['totalDownloadSize'] + part['size'] 
				if 'downloaded' in part:
					stats['totalDownloaded'] = stats['totalDownloaded'] + part['downloaded']
				if 'downloadTime' in part:
					stats['totalDownloadTime'] = stats['totalDownloadTime'] + part['downloadTime']	
			
			stats['partCount'] = len(source['parts'])
			
			if (self.currentPart):
				stats['partCurrent'] = source['parts'].index(self.currentPart) + 1
			
			# Average rate of the buffer over the lifetime of the operation.
			if stats['totalDownloadTime'] > 0:
				stats['avgRate'] = stats['totalDownloaded'] / float(stats['totalDownloadTime'])
			
			# The current rate averaged over the last 2 seconds.
			curBytes = 0
			curTime = 0
			for item in self.curDownloadStats:
				curBytes = curBytes + item['size']
				curTime = curTime +item['time']
			
			if (curTime > 0):
				stats['curRate'] = curBytes / float(curTime)
			
			# Don't care about errors here.
			try:
			
				if (stats['totalDownloadSize'] > 0 and stats['totalDownloaded'] > 0):
				
					# Esitmate time remaining by weighing average speed so far and current speed
					# inversely to the current percentage complete. So, has a file gets nearer to
					# completion, more weight will be put on the current download speed whilst at
					# the start more weight will be put on the average spped so far.
					stats['percentComplete'] = stats['totalDownloaded'] / float(stats['totalDownloadSize'])
					stats['percentRemaining'] = 1 - stats['percentComplete']
					stats['bytesRemaining'] = stats['totalDownloadSize'] - stats['totalDownloaded']
					
					stats['timeRemainingAvgRate'] = stats['bytesRemaining'] / stats['avgRate']
					stats['timeRemainingCurRate'] = stats['bytesRemaining'] / stats['curRate']
				
					# Weight time remaining based on percentComplete.
					stats['timeRemaining'] = (
						(stats['timeRemainingCurRate'] * stats['percentComplete']) +
						(stats['timeRemainingAvgRate'] * stats['percentRemaining'])
					)
			
			except Exception, ex:
				Log.Exception('*** Error whilst calculating stats.')
				pass
		
		return stats
	

	'''
		Helper method to return the Dict for the current source.
	'''
	def getCurrentSource(self):
	
		# We don't have a current source. Abort.
		if (not self.item['currentSource']):
			return None
			
		# Return first source with the same id as currentSource.
		for source in self.item['sources']:
			if (source['id'] == self.item['currentSource']):
				return source
		
		# No match found. Abort.
		return None


	'''
		Reset a source to be like new.
	'''
	def cleanSource(self, source):
	
		source['status'] = 'NEW'
		
		for part in source['parts']:
		
			part['size'] = -1
			
			if part['file'] and os.path.isfile(part['file']):
				# Delete the part's output file.
				os.remove(part['file'])
				
			part['file'] = None
			part['downloaded'] = -1
			part['downloadTime'] = -1
		
	
	'''
		Remove any files we've created.
	'''
	def cleanData(self):
	
		if (self.item['outputDir']):
			shutil.rmtree(self.item['outputDir'])
		
		
	'''
		Reset ourselves so that we get picked up by the main BufferManager thread.
	'''
	def makeStartable(self):
	
		# All sources have been tried unsuccesfully previously. Try them again.
		if self.item['currentStatus'] == 'NO_SOURCE':
		
			for source in self.item['sources']:
				self.cleanSource(source)
					
			self.item['currentStatus'] = 'ADDED'
			
		else:
			self.item['currentStatus'] = 'SUSPENDED'
		
	
	'''
		Helper method to return whether this current BufferItem can currently start its download.
	'''
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
		
	def stop(self):
	
		self.item['currentStatus'] = 'STOPPED'
		
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
		

###################################################################################################
# HELPER METHODS
###################################################################################################

'''
	Given a file, add it to a Plex library, let Plex scan and it and then extract out
	information about the file.

	This is used when a preBuffer item has finished downloading to retrieve meta info
	about the file so that it can be passed on to the PreBuffer URL service so that it
	may return a fully populated media item, which in turns should give clients a much
	better chance of working out whether they'll need to transcode.
'''
def plexAnalyseFile(filePath, libName):

	return plexQueryFile(
		filePath=filePath,
		libName=libName,
		wantPath=False,
		wantAnalysis=True,
		delFromLib=True
	)
	
'''
	Given a file, add it to a Plex library, let Plex scan and it and then extract out
	information about the file.
	
	This is used when a user chooses to actually play a file to add the item to a
	library and retrieve the item's URL to play.
'''
def plexPathForFile(filePath, libName):

	return plexQueryFile(
		filePath=filePath,
		libName=libName,
		wantPath=True,
		wantAnalysis=False,
		delFromLib=False
	)

'''
	Function that does the work of adding a file to a Plex lib and extracting info out.
'''
def plexQueryFile(filePath, libName, wantPath, wantAnalysis, delFromLib):

	libURL = addPathToLib(filePath, libName)
	
	cnt = 0
	info = {}
	
	haveAllData = False
	
	while (cnt <= 10 and not haveAllData):

		Thread.Sleep(2)
		haveAllData = True
		cnt = cnt + 1
		
		# Get the play ID of the item and send that to client.
		request = urllib2.Request("http://127.0.0.1:32400" + libURL + "/all")
		response = urllib2.urlopen(request)
		
		# Look for the one and only media item in there with our name.
		content = response.read()
		elem = XML.ElementFromString(content)
		partElems = elem.xpath("//Part[@file='%s']" % filePath)
		
		if (len(partElems) > 0):
		
			if wantPath:
				info['fileURL'] = partElems[0].get("key")
				
			if wantAnalysis:
				mediaElem = partElems[0].getparent()
				mediaElemAttribs = mediaElem.keys()
			
				if ('videoResolution' in mediaElemAttribs):
					for item in ['videoResolution', 'duration', 'bitrate', 'aspectRatio', 'audioCodec', 'videoCodec', 'container', 'videoFrameRate', 'height', 'width']:
						if (item in mediaElemAttribs):
							info[item] = mediaElem.get(item)
				
				else:
					Log("*** Got URL of part but no media info. Retrying.")
					haveAllData = False
				
		else:
			Log("*** Failed to get part for item %s. Retrying." % filePath)
			haveAllData = False
			
	if delFromLib:
		delPathFromLib(filePath, libName)
		
	Log(info)
	return info
	
'''
	Add the given path to the Pre-Buffer Plex Library, creating the latter if it doesn't 
	already exist.
	
	Returns the path to the library as a string.
'''
def addPathToLib(filePath, libName):

	semaphore = Thread.Semaphore("PRE_BUFFER_LIB_OP_" + libName)
	semaphore.acquire()
	
	try:
	
		filePath = os.path.dirname(filePath)
		
		# Check if we already have a pre-buffer library....
		request = urllib2.Request("http://127.0.0.1:32400/library/sections/")
		response = urllib2.urlopen(request)
		
		content = response.read()
		elem = XML.ElementFromString(content)
		dirElems = elem.xpath("//Directory[@title='%s']" % libName)
		
		if (len(dirElems) > 0):
		
			# We do... Get the section ID out.
			libURL = "/library/sections/%s" % dirElems[0].get('key')
			
			# Get the current paths out.
			alreadySet = False
			paths = []
			
			for pathElem in dirElems[0].xpath("./Location"):
			
				locPath = pathElem.get('path')
				if locPath == filePath or locPath == (filePath + os.sep):
					alreadySet = True
				
				paths.append(("location",locPath))
				
			if not alreadySet:
				paths.append(("location", filePath))
				Log("*** Trying to add %s to library %s" % (filePath, libURL))
				request = urllib2.Request("http://127.0.0.1:32400" + libURL + "?" + urllib.urlencode(paths))
				request.get_method = lambda: 'PUT'
				response = urllib2.urlopen(request)
			else:
				Log("*** Path %s already in library %s"  % (filePath, libURL))
			
		else:
		
			# We don't so Create a library for the folder above.
			#
			# Create an opener that understands 201 status codes returned by Plex.
			opener = urllib2.build_opener(HTTPBetterErrorProcessor)
			
			request = urllib2.Request(
				"http://127.0.0.1:32400/library/sections?" +
				urllib.urlencode({
					'type': 'movie',
					'agent': 'com.plexapp.agents.none',
					'scanner': 'Plex Video Files Scanner',
					'language': 'xn',
					'location': filePath,
					'name': libName,
				})
			)
			
			response = opener.open(request,"")
				
			# Pick up Location header which contains our Library ID.
			libURL = response.info()["Location"]
		
		# Refresh the library.
		opener = urllib2.build_opener(HTTPBetterErrorProcessor)
		request = urllib2.Request("http://127.0.0.1:32400" + libURL + "/refresh")
		response = opener.open(request)
		
		return libURL
		
	finally:
		semaphore.release()

'''
	Delete the given path to the Pre-Buffer Plex Library if the library exists and the
	path is set as a location for the library.
	
	Returns nothing.
'''
def delPathFromLib(filePath, libName):

	semaphore = Thread.Semaphore("PRE_BUFFER_LIB_OP_" + libName)
	semaphore.acquire()
	
	try:
	
		filePath = os.path.dirname(filePath)
		
		# Check if we already have a pre-buffer library....
		request = urllib2.Request("http://127.0.0.1:32400/library/sections/")
		response = urllib2.urlopen(request)
		
		content = response.read()
		elem = XML.ElementFromString(content)
		dirElems = elem.xpath("//Directory[@title='%s']" % libName)
		
		if (len(dirElems) > 0):
		
			# We do... Get the section ID out.
			libURL = "/library/sections/%s" % dirElems[0].get('key')
			
			# Get the current paths out.
			pathFound = False
			paths = []
			
			for pathElem in dirElems[0].xpath("./Location"):
			
				locPath = pathElem.get('path')
				if locPath == filePath or locPath == (filePath + os.sep):
					pathFound = True
				else:
					paths.append(("location",locPath))
				
			if pathFound:
			
				if (len(paths) <= 0):
					Log("*** Delete Library as only path left is one to be deleted.")
					request = urllib2.Request("http://127.0.0.1:32400" + libURL)
					request.get_method = lambda: 'DELETE'
					response = urllib2.urlopen(request)
				else:
					Log("*** Trying to del %s from library %s" % (filePath, libURL))
					request = urllib2.Request("http://127.0.0.1:32400" + libURL + "?" + urllib.urlencode(paths))
					request.get_method = lambda: 'PUT'
					response = urllib2.urlopen(request)
					
					# Refresh the library.
					opener = urllib2.build_opener(HTTPBetterErrorProcessor)
					request = urllib2.Request("http://127.0.0.1:32400" + libURL + "/refresh")
					response = opener.open(request)

			else:
				Log("*** Path %s not currentl in library %s"  % (filePath, libURL))
			
		else:
		
			# We don't. Nothing to do.
			Log("*** Couldn't delete path %s from pre-buffer library. Library dosen't exist." % filePath)
		
				
	finally:
		semaphore.release()
		
	return ""
	
def getLibraryList(type):

	libs = []
	
	if (type == 'tv'):
		dirType = 'show'
	else:
		dirType = 'movie'

	request = urllib2.Request("http://127.0.0.1:32400/library/sections/")
	response = urllib2.urlopen(request)
		
	content = response.read()
	elem = XML.ElementFromString(content)
	dirElems = elem.xpath("//Directory[@type='%s']" % dirType)
	
	for dirElem in dirElems:
	
		# Look for each path in dir.
		locs = [loc.get("path") for loc in dirElem.xpath("./Location")]
		
		libs.append(
			{
				'name': dirElem.get("title"),
				'id': dirElem.get("key"),
				'locations': locs,
			}
		)
		
	Log('*** Found the following %s libraries: %s' % (type, libs))
	
	return libs