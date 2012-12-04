import datetime
import cerealizer

class FavouriteItems(object):

	SORT_DEFAULT = 1
	SORT_MRU = 2
	SORT_ALPHABETICAL = 3
	
	def __init__(self):
	
		self.items = []
		self.labels = []
		
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
	
	def check_for_new_items(self, mediainfo, items):
	
		favourite = self.get(mediainfo)[0]
		
		# Are there any items in the current show list which aren't in the fav's show list?
		# Note that all of these should automatically be unwatched since as items are watched,
		# the favourites are updated with the url of the watched item. So, even if the 
		# favourite wasn't aware of the watched item (i.e: new item since last check),
		# it will still have been added to its list of watched items.
		items_set = set(items)
		new_items = items_set.difference(set(favourite.items))
		
		#Log("Found new items: " + str(new_items))
			
		# Items list is different.
		favourite.new_item = len(new_items) > 0
		if (len(new_items) > 0):
			favourite.date_last_item_found = datetime.datetime.utcnow()
		
		favourite.date_last_item_check = datetime.datetime.utcnow()
		
		return favourite.new_item
		
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
	
		return sorted(self.labels)	
		
	def del_label(self, label):

		for item in self.items:
			if (label in item.labels):
				item.labels.remove(label)
				
		if (label in self.labels):
			self.labels.remove(label)
		
	def add_label(self, label):
	
		if (label not in self.labels):
			self.labels.append(label)
		
	def __len__(self):
	
		return len(self.items)
		
	def __getattr__(self, name):
	
		# Old favourites won't have a labels attribute. Manually add it in now.
		if (name == 'labels'):
			object.__setattr__(self, 'labels', [])
			return object.__getattribute__(self,name)
			
		
class FavouriteItem(Object):

	def __init__(self, mediainfo, path):
	
		self.mediainfo = mediainfo
		self.path = path
		self.date_added = datetime.datetime.utcnow()
		self.date_last_used = self.date_added
		self.new_item_check = False
		self.items = None
		self.date_last_item_check = None
		self.date_last_item_found = None
		self.new_item = False
		self.labels = []
				

	def __getattr__(self, name):
	
		# Old favourites won't have a labels attribute. Manually add it in now.
		if (name == 'labels'):
			object.__setattr__(self, 'labels', [])
			return object.__getattribute__(self,name)
		elif (name == 'date_last_item_found'):
			object.__setattr__(self, 'date_last_item_found', self.date_last_item_check)
			return object.__getattribute__(self,name)
			
		raise AttributeError
		
	def ready_for_check(self, force):
	
		# Return true if:
		# * We're marked as needing checks
		# * And either -
		#     * we want to force a check
		#     * or we're not already marked as having a new item and we're overdue a check.
		return (
			self.new_item_check and
			(
				force or
				(
					(not self.new_item) and
					datetime.datetime.utcnow() > self.next_check_date()
				)
			)
		)
		
	def next_check_date(self):

		last_found_delta =  self.date_last_item_check - self.date_last_item_found
		
		# If it's been less than 8 days since we found a new item, check every 3 hours at the most.
		if (last_found_delta.days <= 8):
			check_delta = 3
			
		# If it's been more than 8 days, but less than 16, check every 8 hours at the most.
		elif (last_found_delta.days > 8 and last_found_delta.days <= 16):
			check_delta = 8
			
		# If it's been more than 16 days, but less than 32, check every 12 hours at the most.
		elif (last_found_delta.days > 16 and last_found_delta.days <= 32):
			check_delta = 12
			
		# If it's been more than 32 days, check once every 24 hours at the most.
		elif (last_found_delta.days > 32):
			check_delta = 24
			
		return self.date_last_item_check + timedelta(minutes=check_delta * 60 - 0.5)
		
cerealizer.register(FavouriteItems)
cerealizer.register(FavouriteItem)