import datetime
import cerealizer
from sets import Set

class BrowsedItems(object):

	def __init__(self):
	
		self.items = []
		pass
		
	def add(self, mediaInfo, providerURLs, path, caller=None):
	
		self.items.append([mediaInfo, providerURLs, path, caller])
		
		while (len(self.items) > 50):
			self.items.pop(0)
		
	def getCaller(self, url):
	
		# Look through each of our items and see if any of them has a URL
		# which matches the passed in URL.
		result = [elem for elem in self.items if url in elem[1]]

		if (len(result) > 0 and len(result[0]) >= 4):
			return result[0][3]
		else:
			return None
			
	def getByURL(self, url):
	
		# Look through each of our items and see if any of them has a URL
		# which matches the passed in URL.
		result = [elem for elem in self.items if url in elem[1]]

		if (len(result) > 0):
			return [result[-1][0], result[-1][2]]
		else:
			return None
			
	def getByID(self, id, season_num, ep_num):
	
		# Look through each of our items and see if any of them has a URL
		# which matches the passed in URL.
		result = None
		for item in self.items:
			if (item[0].id == id):
				if (season_num and ep_num):
					if (item[0].season == season_num and item[0].ep_num == ep_num):
						result = item
				else:
					result = item
					
			if (result):
				break
				
		if (result):
			return [result[0], result[2]]
		else:
			return None

	def __str__(self):
	
		return str(self.items)
	
		
class ViewedItems(object):

	def __init__(self):
	
		self.recent_items = []
		self.watched_items = []
		
	def add_recent(self, mediainfo, path, tv_mode=None, num_to_show=None):

		# The last element of the path will contain the URL actually played.
		played_url = path[-1]['url']
		
		#Log('Trying to add item :' + played_url + ' to recently played list.')
		
		result = [elem for elem in self.recent_items if played_url == elem[2]]
		
		if (len(result) <= 0):
			self.recent_items.insert(0,[mediainfo, path, played_url])
			
		elif (len(result) == 1):
					
				# We have a mediainfo, meaning we care about the ordering of this
				# item. So, remove the previous version and re-add it in.
				self.recent_items.remove(result[0])
				self.recent_items.insert(0,[mediainfo, path, played_url])
				
		while (len(self.get_recent(tv_mode, None)) > num_to_show):
			self.recent_items.pop()
		
	def remove_from_recent(self, mediainfo, tv_mode):
	
		""" Remove all items which match the given mediainfo.
		If the mediainfo is for a TV Show and a TV Mode is passed in this will
		also remove any other item which match the TV Mode
		
		So, for  example, if TV Mode is Show, then any other episode for the show
		in the media info will also be removed."""
		
		if (mediainfo.type == 'movies'):
			items = [elem for elem in self.recent_items if mediainfo.id == elem[0].id]
		else:
			if (tv_mode == 'Episode'):
				items = [elem for elem in self.recent_items if mediainfo.id == elem[0].id and mediainfo.season == elem[0].season and mediainfo.title == elem[0].title]
			elif (tv_mode == 'Season'):
				items = [elem for elem in self.recent_items if mediainfo.id == elem[0].id and mediainfo.season == elem[0].season]
			else:
				items = [elem for elem in self.recent_items if mediainfo.id == elem[0].id]
		
		for item in items:
			self.recent_items.remove(item)
			
		
	def clear_recent(self):
		""" Remove all recently watched items from this object """
		self.recent_items = []
			
	def get_recent(self, tv_mode=None, num_to_show=None):
	
		ret_items = []
		
		for item in self.recent_items:
		
			if (item[0] is None):
				continue
			
			if (item[0].type == 'movie'):
				ret_items.append(item)
				
			else:
			
				# Work out whether the item should be added to the list.
				if (tv_mode is None or tv_mode == 'Episode'):
					ret_items.append(item)
				elif (tv_mode == 'Season'):
				
					# See if we already have an entry for this show and season.
					#
					# First, do we have a show name and season to do comparison?
					if (item[0].show_name is None or item[0].season is None):
					
						# Don't have, can't compare, so add it in.
						ret_items.append(item)
						
					else:
					
						result = [elem for elem in ret_items if (elem[0].id == item[0].id and elem[0].season == item[0].season)]
						
						# If we don't have an existing item, add ourselves in. Otherwise, ignore it.
						if (len(result) <= 0):
							ret_items.append(item)
					
				elif (tv_mode == 'Show'):
			
					# See if we already have an entry for this show.
					#
					# First, do we have a show name to do comparison?
					if (item[0].show_name is None or item[0].season is None):
					
						# Don't have, can't compare, so add it in.
						ret_items.append(item)
						
					else:
					
						result = [elem for elem in ret_items if (elem[0].id == item[0].id)]
						
						# If we don't have an existing item, add ourselves in. Otherwise, ignore it.
						if (len(result) <= 0):
							ret_items.append(item)
							
			# Do we have enough entries?
			if (num_to_show and len(ret_items) >= num_to_show):
				break
			
		return ret_items
		
	def mark_watched(self, path):
	
		# The last element of the path will contain the URL actually played.
		played_url = path[-1]['url']
		
		#Log('Trying to add item :' + played_url + ' to  watched list.')
		
		if (not self.has_been_watched(played_url)):
			self.watched_items.append([path, played_url])
	
	def mark_unwatched(self, url):
	
		elems = [elem for elem in self.watched_items if url == elem[1]]
		
		for elem in elems:
			self.watched_items.remove(elem)
				
	def has_been_watched(self, url):

		if (isinstance(url, basestring)):
			url_set = set([url])
		else:
			url_set = set(url)

		return url_set.issubset([x[1] for x in self.watched_items])
	
	def __len__(self):
	
		return len(self.recent_items)


cerealizer.register(BrowsedItems)
cerealizer.register(ViewedItems)

