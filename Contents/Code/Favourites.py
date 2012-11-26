import datetime
import cerealizer

class FavouriteItems(object):

	SORT_DEFAULT = 1
	SORT_MRU = 2
	SORT_ALPHABETICAL = 3
	
	def __init__(self):
	
		self.items = []
		
	def add(self, mediainfo, path):

		#Log('Trying to add item :' + str(mediainfo) + ' to favourites.')
		
		result = self.get_items_for_mediainfo(mediainfo)
	
		if (len(result) <= 0):
			self.items.insert(0, FavouriteItem(mediainfo, path))
		else:
			# FIXME: Update last accessed time.
			pass
	
	def watch(self, mediainfo, url):
	
		"""Add another URL to list of items considered as having been watched for
		the favourite with the given mediainfo.
		
		As a result of adding this item, it will no longer be considered as a new 
		item when working out whether the favourite has any new items or not.
		"""
		if (mediainfo.type != 'tv'):
			return
		
		# The mediainfo being passed in will be for a specific episode in a specific season.
		# However, both the season and the show may be in the system as favourites. Look for both.
		favs = [
			elem for elem in self.items
			if elem.mediainfo.id == mediainfo.id and (elem.mediainfo.season == mediainfo.season or elem.mediainfo.season is None)
		]
		
		for fav in favs:
		
			# New item tracking has not been requested for this favourite.
			# Do nothing.
			if (fav.new_item_check == False):
				#Log("New item checking off")
				continue
		
			# Add URL to list of items considered to have been watched if not already in list.
			if (not url in fav.items):
				#Log("Adding " + url + " to favourite.")
				fav.items.append(url)
			
		return favs
	
	def get(self, mediainfo=None, sort=None):
	
		if (mediainfo is not None):
			items = self.get_items_for_mediainfo(mediainfo)
		else:
			items = self.items
		
		if (sort is None or sort == FavouriteItems.SORT_DEFAULT):
			return items
		elif (sort == FavouriteItems.SORT_ALPHABETICAL):
			return sorted(items, key=lambda x: x.mediainfo.title)
		elif (sort == FavouriteItems.SORT_ALPHABETICAL):
			return sorted(items, key=lambda x: x.mediainfo.title)
		else:
			return items
	
	def remove(self, mediainfo):
	
		items_to_remove = self.get_items_for_mediainfo(mediainfo)
		
		for item in items_to_remove:
			self.items.remove(item)
	
	def get_items_for_mediainfo(self, mediainfo):
		if (mediainfo.type == 'tv' and mediainfo.season is not None):
			items = [elem for elem in self.items if elem.mediainfo.id == mediainfo.id and elem.mediainfo.season == mediainfo.season]
		else:
			items = [elem for elem in self.items if (elem.mediainfo.id == mediainfo.id) and elem.mediainfo.season is None]
			
		return items
	
	def get_favourites_for_label(self, label):
	
		return [x for x in self.items if label in x.labels]
		
	def get_labels(self):
	
		labels = Set()
		for fav in self.items:
			labels = labels.union(fav.labels)
			
		labels = sorted(labels)	
		
		return labels
		
	def __len__(self):
	
		return len(self.items)
		
class FavouriteItem(Object):

	def __init__(self, mediainfo, path):
	
		self.mediainfo = mediainfo
		self.path = path
		self.date_added = datetime.datetime.utcnow()
		self.date_last_used = self.date_added
		self.new_item_check = False
		self.items = None
		self.date_last_item_check = None
		self.new_item = None
		self.labels = []
				

	def __getattr__(self, name):
	
		# Old favourites won't have a labels attribute. Manually add it in now.
		if (name == 'labels'):
			object.__setattr__(self, 'labels', [])
			return object.__getattribute__(self,name)
		
		raise AttributeError
		
cerealizer.register(FavouriteItems)
cerealizer.register(FavouriteItem)