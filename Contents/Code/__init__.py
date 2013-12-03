import re
import cerealizer
import urllib
import urllib2
import urlparse
import copy
import sys
import base64
import os

from datetime       import date, datetime, timedelta
from dateutil       import tz
from sets           import Set

from BeautifulSoup  import BeautifulSoup

# Non-standard imports.
import Parsing

import demjson

import Notifier
import Site
import Utils
import Buffer

from NavExObject    import CaptchaBase, MultiplePartObject
from MetaProviders  import DBProvider, MediaInfo
from RecentItems    import BrowsedItems, ViewedItems
from Favourites     import FavouriteItems
from Buffer         import BufferManager

cerealizer.register(MediaInfo)

VIDEO_PREFIX = Site.VIDEO_PREFIX
NAME = Site.NAME

# Plugin interest tracking.
VERSION = Site.VERSION
VERSION_URLS = Site.VERSION_URLS

LATEST_VERSION_URL = Site.LATEST_VERSION_URL

LATEST_VERSION = 'LATEST_VERSION'
LATEST_VERSION_SUMMARY = 'LATEST_VERSION_SUMMARY'

# make sure to replace artwork with what you want
# these filenames reference the example files in
# the Contents/Resources/ folder in the bundle
ART	 = 'art-default.jpg'
APP_ICON = 'icon-default.png'

PREFS_ICON = 'icon-prefs.png'
SEARCH_ICON='icon-search.png'
MOVIE_ICON='icon-movie.png'
TV_ICON='icon-tv.png'
BUFFER_ICON='icon-buffer.png'
ADDITIONAL_SOURCES_ICON='icon-additional-sources.png'
STANDUP_ICON='icon-standup.png'
GENRE_BASE='icon-genre'
GENRE_ICON=GENRE_BASE + '.png'
TAG_ICON='icon-tag-%s.png'
TAG_ICON_COLOUR=['red','orange','yellow','green','cyan','blue','purple']

BROWSED_ITEMS_KEY = "RECENT_BROWSED_ITEMS"
WATCHED_ITEMS_KEY = "USER_VIEWING_HISTORY"
FAVOURITE_ITEMS_KEY = "FAVOURITE_ITEMS"
ADDITIONAL_SOURCES_KEY = "ADDITIONAL_SOURCES"
LAST_USAGE_TIME_KEY = "LAST_USAGE_TIME"

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_2) AppleWebKit/534.51.22 (KHTML, like Gecko) Version/5.1.1 Safari/534.51.22'

PLEX_URL = "http://127.0.0.1:32400"
PLUGIN_URL = PLEX_URL + VIDEO_PREFIX
KEEP_ALIVE_PATH = VIDEO_PREFIX + "/keepalive"

####################################################################################################

def Start():

	# Make this plugin show up in the 'Video' section
	Plugin.AddPrefixHandler(VIDEO_PREFIX, VideoMainMenu, NAME, APP_ICON, ART)

	Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
	Plugin.AddViewGroup("List", viewMode="List", mediaType="items")
	Plugin.AddViewGroup('PanelStream', viewMode='PanelStream', mediaType='items')
	Plugin.AddViewGroup('MediaPreview', viewMode='MediaPreview', mediaType='items')

	# Set some defaults
	MediaContainer.title1 = NAME
	MediaContainer.viewGroup = "InfoList"
	MediaContainer.art = R(ART)
	MediaContainer.userAgent = USER_AGENT
	
	ObjectContainer.art=R(ART)
	ObjectContainer.user_agent = USER_AGENT

	DirectoryItem.thumb = R(APP_ICON)
	VideoItem.thumb = R(APP_ICON)
	
	#DirectoryObject.thumb = R(APP_ICON)
	#VideoClipObject.thumb = R(APP_ICON)
	
	HTTP.CacheTime = CACHE_1HOUR
	HTTP.Headers['User-agent'] = USER_AGENT
	HTTP.Headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
	HTTP.Headers['Accept-Encoding'] = '*gzip, deflate'
	HTTP.Headers['Connection'] = 'keep-alive'

	if hasattr(Site, 'Init'):
		Site.Init()
	
	if hasattr(Parsing, 'Init'):
		Parsing.Init()
	
	# Assign default values for stuff we may need.
	if (not Dict[LAST_USAGE_TIME_KEY]):
		Dict[LAST_USAGE_TIME_KEY] = datetime(1900,1,1)
		
	# Migrate Favourites Lables to be persitent.
	if ('FAV_LABELS_PERSISTENT' not in Dict):
	
		Log("Migrating Favourite Labels to be persistent.")
		Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
		try:
			labels = []
			favs = load_favourite_items()
			
			for fav in favs.get():
				labels.extend(fav.labels)
			
			Log("Found the following labels: " + str(labels))
			for label in labels:
				favs.add_label(label)
				
			save_favourite_items(favs)
			Dict['FAV_LABELS_PERSISTENT'] = True
		except Exception, ex:
			Log.Exception("Error migrating labels")
			pass		
		finally:
			Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
	
	# Do a bit of housekeeping... See if any plugins that support our additional
	# sources functionality are present on this sytem and start a new item check in
	# favourites.
	Thread.Create(StartFavouritesCheck)
	Thread.Create(CheckAdditionalSources, sources=Site.ADDITIONAL_SOURCES)
	
	# Initialise Buffer manager and re-launch any suspended downloads...
	buffer = BufferManager.instance()
	buffer.setPrefs(Site.GetBufferPath(), PLEX_URL + KEEP_ALIVE_PATH)
	buffer.launch()


####################################################################################################
# see:
#  http://dev.plexapp.com/docs/Functions.html#ValidatePrefs

def ValidatePrefs():

	if (Prefs['favourite_notify_email']):
		# Enable cron if we have favourites which are already being checked.
		if (len([x for x in load_favourite_items().get() if x.new_item_check]) > 0):
			Utils.add_favourites_cron(Platform.OS, NAME, VIDEO_PREFIX)				
	else:
		Utils.del_favourites_cron(Platform.OS, NAME, VIDEO_PREFIX)

####################################################################################################
# Main navigtion menu

def VideoMainMenu():

	oc = ObjectContainer(no_cache=True, title1=L("Video Channels"), title2=NAME, view_group="InfoList")
	
	# Get latest version number of plugin.
	try:
	
		soup = BeautifulSoup(HTTP.Request(LATEST_VERSION_URL, cacheTime=3600).content)
		latest_version = soup.find('div',{'class':'markdown-body'}).p.string
		
		if (latest_version != VERSION):
		
			summary = soup.find('div',{'class':'markdown-body'}).pre.code.string
			summary += "\nClick to be taken to the Unsupported App Store"
			latest_version_summary = summary
			
			oc.add(
				DirectoryObject(
					key=Callback(UpdateMenu),
					title='--- Plugin Update Available ---',
					tagline="Version " + latest_version + " is now available. You have " + VERSION,
					summary=latest_version_summary,
					thumb=None,
					art=R(ART)
				)
			)
			
	except Exception, ex:
		Log.Exception("******** Error retrieving and processing latest version information. Exception is:\n" + str(ex))
		
	oc.add(
		DirectoryObject(
			key=Callback(TypeMenu, type="movies", parent_name=oc.title2),
			title=L('MoviesTitle'),
			tagline=L('MoviesSubtitle'),
			summary= L('MoviesSummary'),
			thumb = R(MOVIE_ICON),
			art = R(ART)	
		)
	)

	oc.add(
		DirectoryObject(
			key=Callback(TypeMenu, type="tv", parent_name=oc.title2),
			title=L("TVTitle"),
			tagline=L("TVSubtitle"),
			summary=L("TVSummary"),
			thumb=R(TV_ICON),
			art=R(ART)
		)
	)
	
	if (Prefs['watched_amount'] != 'Disabled'):
		oc.add(
			DirectoryObject(
				key=Callback(HistoryMenu,parent_name=oc.title2,),
				title=L("HistoryTitle"),
				tagline=L("HistorySubtitle"),
				summary=L("HistorySummary"),
				thumb=R("History.png"),
			)
		)
	
	title = str(L("Favourites"))

	if (len([x for x in load_favourite_items().get() if x.new_item]) > 0):
		title += " - New item(s) available"
		
	oc.add(
		DirectoryObject(
			key=Callback(FavouritesMenu,parent_name=oc.title2,),
			title=title,
			tagline=L("FavouritesSubtitle"),
			summary=L("FavouritesSummary"),
			thumb=R("Favorite.png"),
		)
	)
	
	if len(BufferManager.instance().items()) > 0:
		oc.add(
			DirectoryObject(
				key=Callback(BufferMenu,parent_name=oc.title2,),
				title=L("BufferTitle"),
				tagline=L("BufferSubtitle"),
				summary=L("BufferSummary"),
				thumb=R(BUFFER_ICON),
			)
		)

	oc.add(
		PrefsObject(
			title=L("PrefsTitle"),
			tagline=L("PrefsSubtitle"),
			summary=L("PrefsSummary"),
			thumb=R(PREFS_ICON)
		)
	)
	
	if (Prefs['favourite_notify_email_test']):
		oc.add(
		DirectoryObject(
			key=Callback(TestEmailMenu),
			title="Send Test Email ",
			summary="Send a test email to the email address specified in the preferences",
		)
	)
	
	# This is a user requested menu which the user must go through when using / launching
	# the plugin. If it's been more than 3 hours since we last saw the user, assume
	# it's a new session and add it to the stats if needed.
	if (datetime.utcnow() - Dict[LAST_USAGE_TIME_KEY]) > timedelta(hours=3):
		Thread.Create(VersionTrack)
	
	return oc
	

####################################################################################################
	
def TestEmailMenu():

	if (not Prefs[ "favourite_notify_email"]):
		return MessageContainer(
			"No email set.",
			"Please set an email in the preferences before using this functionality."
		)

	else:
		try:
			Notifier.notify(
				Prefs[ "favourite_notify_email"],
				str(NAME),
				"TEST",
				"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBhIQERUQEBAWEA8QEBQQEBAXFA8QGBAQFRAVFRUQEhQYGyYeFxkjGRIUHy8sJCcpLCwsFR4xNTAqNSYrLCkBCQoKBQUFDQUFDSkYEhgpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKSkpKf/AABEIAMIBAwMBIgACEQEDEQH/xAAbAAEAAwEBAQEAAAAAAAAAAAAABQYHBAMCAf/EAEgQAAIBAQIGDQoDBwMFAAAAAAABAgMEEQUWITFRkwYSMjRBU1RhcXSR0dIHEyJSgaGxs8HDQnKyIzOCkqLh8BVicxRDY8Li/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKMAa1gLAVmlZqEpWalKUqFJyk6VNtt04tttrKwMlBtGL1l5LR1VLuGL1l5LR1VLuAxcG0YvWXktHVUu4YvWXktHVUu4DFwbRi9ZeS0dVS7hi9ZeS0dVS7gMXBtGL1l5LR1VLuGL1l5LR1VLuAxcG0YvWXktHVUu4YvWXktHVUu4DFwbRi9ZeS0dVS7hi9ZeS0dVS7gMXBtGL1l5LR1VLuGL1l5LR1VLuAxcG0YvWXktHVUu4YvWXktHVUu4DFwbRi9ZeS0dVS7hi9ZeS0dVS7gMXBtGL1l5LR1VLuGL1l5LR1VLuAxcG0YvWXktHVUu4YvWXktHVUu4DFwbRi9ZeS0dVS7hi9ZeS0dVS7gMXBtGL1l5LR1VLuGL1l5LR1VLuAxcG0YvWXktHVUu4YvWXktHVUu4DFwbRi9ZeS0dVS7ig+UOxU6VenGlTjTi6F7UIxgm/OTV7SWe5ICqgAAbRsd3pZ+r0vlxMXNo2O70s/V6Xy4gSAAAAAAAAAAAAHJbcKQpZG75eqs/t0AdZ51rTGG7ko9LSK5asOVJ5E9pHQs/tkcDd+V5XpAstTD1JZm5dCf1uOeWyWPBTb6Wl3kFGLeZX+894YOqvNTl2NfECUxl/wDF/V/8npDZJDhhJfysiv8ASq3Fy93eeVSxVI56cl/CwLHSw1Rl+Pa/mTXvzHbCaavTTWlNMpJ90q8oO+MnF8zuAugICybIZLJUW2XrLI+zMyas9qjUV8JXr4dK4APUAAAAAAAAAADOPKdvil1f7szRzOPKdvil1f7swKcAABtGx3eln6vS+XExc2jY7vSz9XpfLiBIAAAAAAAAH43dleRLO9AbuyvIlnegreFcKuo9rHJTX9T0vmA98I4dbvjSyLhnwv8ALoIZs+6NFzajFXyeZFiwdgWNP0p3Tn7o9GkCJseBqlTLuI6XwrmRMWfAdKGdbd6Xm7CQAHzCmo5IpRWhJL4H0AAAAHlWssJ7qCl0pfEjbTseg8tN7V6HlXeiXAFPtVhnSd043LgedP2nxRryg9tFuL/zI9JcpwUlc1ennTy3kFhLAe1vnSyrO4cK/LpA7cG4YVX0ZejU90ujn5iRKQmWLA+Ftv8As5v0/wAL9ZaOkCVAAAAAAAAM48p2+KXV/uzNHM48p2+KXV/uzApwAAG0bHd6Wfq9L5cTFzaNju9LP1el8uIEgAAAAAAHLhO2eapuS3TyR6dPszgRmHcI3vzUXkW7el+qRFGk5yUYq9vIkfDenhzlkwLg/wA3HbyXpzX8seBAdGDsHRox0ze6lp5lzHWAAAAAA+J1oxzyS6WkB9g8P+up8ZH+ZHrCrGW5kpdDTA+gAAAAENhjBN99SmsueUdP+5c5BJ3ZVkaypl2K5hvB+0lt4r0JPKvVlo6GBK4Kwh52GXdxyS59EjuKhYbW6U1NZs0lpi86LdGSaTWVNXp6UB+gAAAABnHlO3xS6v8AdmaOZx5Tt8Uur/dmBTgAANo2O70s/V6Xy4mLm0bHd6Wfq9L5cQJAAAAAAK1h21baptVmhk/i4e72FirVdrFyeaKb7EUycm2287d76WB24HsfnKiv3MfSlz6F2lpI3ANn2tLbcM3f7FkX17SSAAAAfNSVyb0JvsR9HxW3Mvyy+DAqlbCVWe6m7tC9FdiOY97JYJ1dxG9cMsyXtJSlsb9ap7Er/ewIQJ3ZVkenMTdXY3k9Cpe9DV3vRD1aTg3GSuadzQEjYcOThknfOGn8S6HwlhhNSSad6avT0opRYNjlduEoP8LTXRK/J2r3gS4AAHlarOqkHB5pLsfA+09QBSqlNxbi8ji7n0osGx+1baDg88Hk/K83vvOHZBZ9rUU1mmv6lkfuuPLAlfa1lolfF+3N70gLQAAAAAGceU7fFLq/3ZmjmceU7fFLq/3ZgU4AADaNju9LP1el8uJi5tGx3eln6vS+XECQAAAAAcGHKl1GX+5qPvv+hV7iw7I5fs4rTP4RfeQljjfUgtM4/qQFuo09rFRX4YpdiPsAAAAAAAJAAAVnDzXnnd6sb+m7uuJW34ZhTV0Wpz0LKl0srdSo5Nybvbd7fOB8k7sahknLgbil7L39UQtKk5NRir5PMi2WCyKlBQ4c7emTzsDoAAAAARmyClfSv9WSfseT6ortOe1aks6afY7y1YVjfRn+W/saf0KmBd078unKDxscr6cHphH9KPYAAABnHlO3xS6v92Zo5nHlO3xS6v8AdmBTgAANo2O70s/V6Xy4mLm0bHd6Wfq9L5cQJAAAAABD7JF6EPzP9JEYPf7Wn/yR+KJvZFC+knomvemu4r9Ge1lF6JJ9jAugAAAAAAABWsN2iXnZR2z2quuje7tyuAspVsN/vpez9KA4TvsOB51UpZIwf4nlvy3ZEcF5asC/uIfxfrkB6WLB8KS9FXt55PO+5HSAAAAAAAc2En+xqfkl8Colqw1O6jLnuj2yX9yqgXCwL9lD/jj+lHufFCF0YrRFLsR9gAAAM48p2+KXV/uzNHM48p2+KXV/uzApwAAG0bHd6Wfq9L5cTFzaNju9LP1el8uIEgAAAAA5cKUdtSmuHa3rpWX6FSLuU62Wfzc5Q0PJ0cD7ALTg+tt6UZcO1ufSsj+B0EJsctW6pv8ANH6r4E2AAAAAADjq2uhe1KUNsnc71e71k0HYVDCH72p/yS/UwLB/1dm00+z+x1WatCS/ZtOKd2TMnnu95TSxbHP3b/O/0oCVAAAAAAABDbJK3oxhpbk+hZF8fcQ9io7epGOmSv6L8vuPbCtq85Vk1uV6MehcPbedWx2z3zc+CKuXS/7X9oFhAAAAADOPKdvil1f7szRzOPKdvil1f7swKcAABtGx3eln6vS+XExc2jY7vSz9XpfLiBIAAAAABCbIrJmqrg9GX0f0Js+atJSi4yyqSuYFPs1d05Kazxd/SuFFvoVlOKlHKpK9dxUrZZXSm4PgzPSuBnZgbCXm3tJP0JPP6stPQBZAAAAAA4qmBqUm5OLvk236TztnaAI//QqPqv8AmZ1WWyRpLawVybvzt5f8R7AAAAAAAHBhm2+bhct3PIuZcLOu0WiNOLlJ3Je/QlzlTtlrdWbm/YtC4EB4XFtwZZPNU1H8T9KXS/8ALvYQ+ArBt5eckvRg8nPL+xYgAAAAAAZx5Tt8Uur/AHZmjmceU7fFLq/3ZgU4AADaNju9LP1el8uJi5tGx3eln6vS+XECQAAAAAAABxYUweq0cmScdy//AFfMVecHFtNXNZGtBdSPwpgpVVto5Ki4fW5mBwYJwxtbqdR+jmjL1eZ8xPplKqUnFuMlc1nR2WDC06WTdQ9V8H5XwAWkHNZMIQqr0Xl4YvI17OE6QAAAAAAAAB5Wm0xpx203cvi9C5zjtuG4U8kfTlzZl0vuK/arXKo9tN36FwLmSA9cI4RlWle8kVuY6Od8582CxSqy2qzZ5S0LvFhsEqsro5Et1LgX9y0WSyRpR2sV0vhb0sD7o0VCKjFXRSuR9gAAAAAAAzjynb4pdX+7M0czjynb4pdX+7MCnAAAbRsd3pZ+r0vlxMXNo2O70s/V6Xy4gSAAAAAAAAAAA5rbg+FVXSWVZpLOu9FdtuCp0srW2j6y+q4C1gCkJnfZ8N1YZG9utEsvvzkza8C055btpLTHJ2rMRdfY/UjuWpr+V9j7wOulski91BroakvfcdMMOUX+JrpjIrtWx1I7qEl7H8TxAtX+s0eMXZPuPOeH6KzNy6I95Wbz9UW8yv8AeBNVtknqU/bJ/Rd5G2nCNSpupZPVWRdizn7SwZVlmpvpfo/E77Pscf8A3Jpc0cr7WBDJaCWsOAZS9Kp6MfV4X06CZstghS3Ebn6zyt+06APilRUFtYq5LMkfYAAAAAAAAAAzjynb4pdX+7M0czjynb4pdX+7MCnAAAbRsd3pZ+r0vlxMXJ2zbNrZThGnCpFQhFQivN0ndGKuSvay5EBrYMpx+tvGx1VHwjH628bHVUfCBqwMpx+tvGx1VHwjH628bHVUfCBqwMpx+tvGx1VHwjH628bHVUfCBqwMpx+tvGx1VHwjH628bHVUfCBqwMpx+tvGx1VHwjH628bHVUfCBqwMpx+tvGx1VHwjH628bHVUfCBqx+OCedJ9KTMqx+tvGx1VHwjH628bHVUfCBqfmI+rHsifSV2bJ7jKsfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasDKcfrbxsdVR8Ix+tvGx1VHwgasZx5Tt8Uur/dmcGP1t42Oqo+Ei8LYZq2qSnWkpSjHaJqMYeje3ddFaWwOEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH//Z"
			)
			
			return MessageContainer(
				"A test email has been sent to: " + Prefs[ "favourite_notify_email"],
				"This will most probably fail to arrive in your inbox.\nCheck the wiki for troubleshooting information"
			)
			
		except Exception, ex:
			return MessageContainer(
				"An error occurred whilst trying to send the test email",
				"The system encountered the following error: " + str(ex)
			)
			
		
####################################################################################################
# Menu users seen when they select Update in main menu.

def UpdateMenu():

	# Force an update to the UAS' version info.
	try:
		# This will throw a 404 as it returns no data and Plex doesn't like that.
		HTTP.Request(
			"http://" + Request.Headers['Host'] + "/applications/unsupportedappstore/updatecheck",
			cacheTime=0,
			immediate=True
		)
	except Exception,ex:
		pass
	
	# Go to the UAS.
	return Redirect('/applications/unsupportedappstore/installed')
	
####################################################################################################
# Menu users seen when they select TV shows in Main menu

def TypeMenu(type=None, genre=None, path=[], parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	type_desc = "Movies"
	if (type == "tv"):
		type_desc = "TV Shows"
	
	mcTitle2 = type_desc
	if genre is not None:
		mcTitle2 = mcTitle2 + " (" + genre + ")"

	path = path + [{'elem': mcTitle2, 'type': type, 'genre': genre}]

	oc = ObjectContainer(no_cache=True, title1=parent_name, title2=mcTitle2, view_group="InfoList")
	
	for section in Site.GetSections(type, genre):
	
		if (section['type'] == 'items'):
		
			oc.add(
				DirectoryObject(
					key=Callback(
						ItemsMenu,type=type,
						genre=genre,
						sort=section['sort'],
						section_name=section['title'],
						path=path,
						parent_name=oc.title2,
					),
					title=section['title'],
					tagline="",
					summary=section['summary'],
					thumb=section['icon'],
					art=R(ART)	
				)
			)
		
		elif (section['type'] == 'type'):
				
			oc.add(
				DirectoryObject(
					key=Callback(
						TypeMenu,
						type=type,
						genre=section['genre'],
						path=path,
						parent_name=oc.title2,
					),
					title=section['title'],
					summary=section['summary'],
					thumb=section['icon'],
					art=R(ART),
				)
			)
			
		elif (section['type'] == 'genre'):
		
			oc.add(
				DirectoryObject(
					key=Callback(
						GenreMenu,
						type=type,
						path=path,
						parent_name=oc.title2,
					),
					title=section['title'],
					summary=section['summary'],
					thumb=section['icon'],
					art=R(ART),
				)
			)
			
		elif (section['type'] == 'alphabet'):
		
			oc.add(
				DirectoryObject(
					key=Callback(
						AZListMenu,
						type=type,
						genre=genre,
						path=path,
						parent_name=oc.title2,
						thumb=section['icon']
					),
					title=section['title'],
					summary=section['summary'],
					thumb=section['icon'],
					art=R(ART)
				)
			)
			
		elif (section['type'] == 'search'):
		
			oc.add(
				InputDirectoryObject(
					key=Callback(
						SearchResultsMenu,
						type=type,
						parent_name=oc.title2,
					),
					title="Search",
					tagline="Search for a title using this feature",
					summary="Search for a title using this feature",
					prompt="Search for items containing...",
					thumb=R(SEARCH_ICON),
					art=R(ART)				
				)
			)
		
	return oc


####################################################################################################

def AZListMenu(type=None, genre=None, path=None, parent_name=None, thumb=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	oc = ObjectContainer(view_group="InfoList", title1=parent_name, title2="A-Z")
	azList = ['123','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']
	
	for value in azList:
		oc.add(
			DirectoryObject(
				key=Callback(
					ItemsMenu,
					type=type,
					genre=genre,
					sort=None,
					alpha=value,
					section_name=value,
					path=path,
					parent_name=oc.title2,
				),
				title=value,
				tagline="Complete collection arranged alphabetically",
				summary="Browse items starting with " + value,
				thumb=thumb,
				art=R(ART),
			)
		)
		
	return oc

####################################################################################################

def GenreMenu(type=None, path=None, parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	oc = ObjectContainer(no_cache=True, title1=parent_name,title2="Genre", view_group="InfoList")
		
	for genre in Site.GetGenres():
	
		icon = R(GENRE_BASE + "-" + genre.lower() + ".png")
		if icon is None:
			("Couldn't find icon for genre: " + genre.lower())
			icon = R(GENRE_ICON)
			
		oc.add(
			DirectoryObject(
				key=Callback(
					TypeMenu,
					type=type,
					genre=genre,
					path=path,
					parent_name=oc.title2,
				),
				title=genre,
				tagline="",
				summary="Browse all : " + genre + ".",
				thumb=icon,
				art=R(ART),
			)
		)
		
	return oc


####################################################################################################

def ItemsMenu(
	type=None, genre=None, sort=None, alpha=None,
	section_name="", start_page=0, path=[], parent_name=None
):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	num_pages = 2
	replace_parent = False
	title2 = section_name
	
	oc = ObjectContainer(no_cache=False, view_group="InfoList", title1=parent_name, title2=title2, replace_parent=replace_parent)
	
	path = path + [{'elem': title2, 'type':type, 'genre':genre, 'sort':sort, 'alpha':alpha, 'section_name':section_name}]
	
	items = Parsing.GetItems(type, genre, sort, alpha, num_pages, start_page)
	
	func_name = TVShowMenu
	
	hist = None
	
	if (type=="movies"):
		func_name = SourcesMenu
		if (need_watched_indicator(type)):
			hist = load_watched_items()
			# Don't cache ourselves in case the user watches a new item.
			# If that happens, we need to rebuild the whole list.
			oc.no_cache = True
		
	if (start_page > 0):
		oc.add(
			DirectoryObject(
				key=Callback(
					ItemsMenu,
					type=type,
					genre=genre,
					sort=sort,
					alpha=alpha,
					section_name=section_name,
					start_page=start_page - num_pages,
					parent_name=oc.title2,
				),
				title="<< Previous",
				tagline="",
				summary= "",
				thumb= "",
				art="",
			)				
		)
	
	for item in items:
	
		#Log(item)
		indicator = ''
		if (hist is not None):
			if (hist.has_been_watched(item.id)):
				indicator = '    '
			else:
				indicator =  u"\u00F8" + "  "
		
		title = item.title
		if (item.year):
			title = title + " (" + str(item.year) + ")"
			
		oc.add(
			DirectoryObject(
				key=Callback(
					func_name,
					mediainfo=item,
					url=item.id,
					path=path,
					parent_name=oc.title2,
				),
				title=indicator + title,
				tagline="",
				summary="",
				thumb=item.poster,
				art="",
			)
		)
			
	oc.add(
		DirectoryObject(
			key=Callback(
				ItemsMenu,
				type=type,
				genre=genre,
				sort=sort,
				alpha=alpha,
				section_name=section_name,
				start_page=start_page + num_pages,
				parent_name=oc.title2,
			),
			title="More >>",
			tagline="",
			summary= "",
			thumb= "",
			art="",
		)
	)
	
	return oc
	
####################################################################################################
# TV SEASONS MENUS
####################################################################################################

def TVShowMenu(mediainfo=None, url=None, item_name=None, path=[], parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	# Clean up mediainfo that's been passed in from favourites as it will be
	# keyed for a specifc ep and not a show.
	mediainfo.season = None
	mediainfo.ep_num = None
	
	if (item_name is not None):
		mediainfo.show_name = item_name
		
	if (mediainfo.show_name is None and mediainfo.title is not None):
		mediainfo.show_name = mediainfo.title
	
	title = mediainfo.show_name
	if (mediainfo.year):
		title = title + " (" + str(mediainfo.year) + ")"
		
	# Get Viewing history if we need an indicator.
	hist = load_watched_items() if (need_watched_indicator('tv')) else None
	no_cache = hist is not None
	
	oc = ObjectContainer(no_cache=no_cache, view_group = "InfoList", title1=parent_name, title2=title)
	
	path = path + [{'elem':mediainfo.show_name, 'show_url':url}]
	
	# Try to retrieve the imdb id and use that as our ID. As this is what favourites are keyed on
	# and this is the first level where an item can be added to favourites it's important to make
	# sure we have the same ID as will be used when navigating lower levels.
	mediainfo_meta = Parsing.GetMediaInfo(url, mediainfo, need_meta_retrieve(mediainfo.type))

	# Did we manage to retrieve any meaningful info?
	if (mediainfo_meta):
		if mediainfo_meta.id:
			mediainfo.id = mediainfo_meta.id
		if mediainfo_meta.summary:
			mediainfo.summary = mediainfo_meta.summary
		if mediainfo_meta.show_name:
			mediainfo.show_name = mediainfo_meta.show_name
		if mediainfo_meta.background:
			mediainfo.background = mediainfo_meta.background
		if mediainfo_meta.poster:
			mediainfo.poster = mediainfo_meta.poster
	
	# When the passed in from favourites or Recently Watched, the mediainfo is for
	# the episode actually watched. So, the poster will be for the ep, not the show.
	# However, show info may have previously been retrieved. So use that if available.
	if hasattr(mediainfo,'show_poster'):
		mediainfo.poster = mediainfo.show_poster

	oc.add(
		PopupDirectoryObject(
			key=Callback(TVShowActionMenu, mediainfo=mediainfo, path=path, parent_name=oc.title2),
			title=L("TVSeasonActionTitle"),
			art=mediainfo.background,
			thumb=mediainfo.poster,
			summary=mediainfo.summary,
		)
	)
	
	items = Parsing.GetTVSeasons("/" + url)
	
	for item in items:
	
		# Grab a copy of the current mediainfo and customise it to the current
		# season, ready to be passed through to season show list.
		mediainfo_season = copy.copy(mediainfo)
		
		season = item['season_number'] if 'season_number' in item else None
		mediainfo_season.season = season
		
		# Does the meta provider have a poster for this season?
		if (
			mediainfo_meta and mediainfo_meta.id and
			hasattr(mediainfo_meta,"season_posters") and
			season in mediainfo_meta.season_posters
		):
			# Yup. Use that.
			mediainfo_season.poster = mediainfo_meta.season_posters[season]
		
		# Do we have episode information for this information. If so, try to work out
		# whether we have any unplayed items.
		indicator = ''
		if (hist and 'season_episodes' in item):
			if hist.has_been_watched([x['ep_url'] for x in item['season_episodes']]):
				indicator = '    '
			else:
				indicator =  u"\u00F8" + "  "
		
		oc.add(
			DirectoryObject(
				key=Callback(
					TVSeasonMenu,
					mediainfo=mediainfo_season,
					item_name=item['season_name'],
					season_url=item['season_url'],
					path=path,
					parent_name=oc.title2,
				),
				title=indicator + item['season_name'],
				tagline="",
				summary="",
				thumb=mediainfo_season.poster,
				art=mediainfo_season.background,
			)
		)

	return oc

####################################################################################################

def TVShowActionMenu(mediainfo, path, parent_name=None):

	oc = ObjectContainer(view_group="InfoList", title1=parent_name, title2="TV Show Actions")
	
	if (Prefs['watched_indicator'] != 'Disabled'):
		oc.add(
			DirectoryObject(
				key=Callback(TVShowActionWatch, item_name=path[-1]['elem'], mediainfo=mediainfo, path=path, action="watch"),
				title="Mark Show as Watched",
			)
		)
	
		oc.add(
			DirectoryObject(
				key=Callback(TVShowActionWatch, item_name=path[-1]['elem'], mediainfo=mediainfo, path=path, action="unwatch"),
				title="Mark Show as Unwatched",
			)
		)
	
	# These won't get used and are keyed to a specific episode, so reset them.
	mediainfo.url = None
	mediainfo.summary = None
	mediainfo.season = None
	
	# Come up with a nice easy title for later.
	mediainfo.title = mediainfo.show_name
	
	fav_path = [item for item in path if ('show_url' in item)]
	
	oc.add(
		DirectoryObject(
			key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo, path=[fav_path[0]], parent_name="Add Show to Favourites"),
			title="Add Show to Favourites",
		)
	)
	
	return oc
	
####################################################################################################

def TVShowActionWatch(item_name=None, mediainfo=None, path=None, action="watch"):

	items = []
	base_path = [item for item in path if ('show_url' in item)]
	show_url = base_path[0]['show_url']
	
	# Get a list of all seasons for this show.
	for item in Parsing.GetTVSeasons("/" + show_url):
	
		item_path = copy.copy(base_path)
		item_mediainfo = copy.copy(mediainfo)
		item_mediainfo.season = item['season_name']
		item_path.append({ 'elem': item['season_name'], 'season_url': item['season_url'] })
		items.append([item_mediainfo, item_path])
		
	# Mark them as watched / unwatched.
	return TVSeasonActionWatch(item_name=item_name, items=items, action=action)


####################################################################################################
# TV SEASON EPISODES MENUS
####################################################################################################

def TVSeasonMenu(mediainfo=None, season_url=None,item_name=None, path=[], parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	# We may have gotten here after client stopped playing a pre-buffered item. Clean up time...
	BufferPlayClean()
	
	# Clean up media info that's been passed in from favourites / recently watched.
	mediainfo.ep_num = None
	
	path = path + [{'elem':item_name,'season_url':season_url}]

	need_indicator = need_watched_indicator('tv')
	
	# Is this in the user's favourites
	
	oc = ObjectContainer(no_cache=need_indicator, view_group="InfoList", title1=parent_name, title2=item_name)
	
	# Get Viewing history if we need an indicator.
	hist = None
	if (need_indicator):
		hist = load_watched_items()
		
	indicator = ""
	if (hist is not None):
		indicator = "    "
		
	if (need_meta_retrieve(mediainfo.type)):
		mediainfo_meta = Parsing.GetMediaInfo(season_url, mediainfo, True)
	else:
		mediainfo_meta = None
		
	# When the passed in from favourites or Recently Watched, the mediainfo is for
	# the episode actually watched. So, the poster will be for the ep, not the season.
	# Since, we've retrieved info about the season, use that as our opportunity to use
	# the correct poster.
	if hasattr(mediainfo,'season_poster'):
		mediainfo.poster = mediainfo.season_poster
	elif mediainfo_meta and mediainfo_meta.poster:
		mediainfo.poster = mediainfo_meta.poster
		
	if (mediainfo_meta and not mediainfo.background and mediainfo_meta.background):
		mediainfo.background = mediainfo_meta.background
	
	oc.add(
		PopupDirectoryObject(
			key=Callback(TVSeasonActionMenu, mediainfo=mediainfo, path=path, parent_name=oc.title2),
			title=indicator + str(L("TVSeasonEpsActionTitle")),
			thumb=mediainfo.poster,
			art=mediainfo.background,
		)
	)
	
	buffer = BufferManager.instance()
	pre_buffer_items = buffer.items()

	for item in Parsing.GetTVSeasonEps("/" + season_url):
	
		mediainfo_ep = copy.copy(mediainfo)
		
		# Do we have a sane episode number extracted out?
		ep_num = item['ep_num'] if ('ep_num' in item) else None
		mediainfo_ep.ep_num = ep_num
				
		# Does this episode actually exist according to meta provider?
		if (
			mediainfo_meta and
			hasattr(mediainfo_meta,'season_episodes') and 
			ep_num in mediainfo_meta.season_episodes
		):
			mediainfo_ep.summary = mediainfo_meta.season_episodes[ep_num]['summary']
			mediainfo_ep.title = "Episode " + str(ep_num) + " - " + mediainfo_meta.season_episodes[ep_num]['title']
			if mediainfo_meta.season_episodes[ep_num]['poster']:
				mediainfo_ep.poster = mediainfo_meta.season_episodes[ep_num]['poster']
		else:
			mediainfo_ep.summary = ""
			mediainfo_ep.title = item['ep_name']
		
		indicator = ''
		if (hist is not None):
			watched = hist.has_been_watched(item['ep_url'])
			indicator = '    ' if (watched) else u"\u00F8" + "  "
		
		# Is the item in the pref-buffer list and finished?
		if item['ep_url'] in pre_buffer_items and buffer.bufferItem(item['ep_url']).isFinished():

			# Then, let the user choosed between seeing regular menu or just
			# playing buffered item.
			oc.add(
				PopupDirectoryObject(
					key=Callback(
						SourcesOrBufferMenu,
						mediainfo=mediainfo_ep,
						url=item['ep_url'],
						item_name=item['ep_name'],
						path=path,
						parent_name=oc.title2,
					),
					title=indicator + mediainfo_ep.title,
					tagline=mediainfo_ep.title,
					summary=mediainfo_ep.summary,
					thumb=mediainfo_ep.poster,
					art=mediainfo_ep.background,
				)
			)
		
		else:
			oc.add(
				DirectoryObject(
					key=Callback(
						SourcesMenu,
						mediainfo=mediainfo_ep,
						url=item['ep_url'],
						item_name=item['ep_name'],
						path=path,
						parent_name=oc.title2,
					),
					title=indicator + mediainfo_ep.title,
					tagline=mediainfo_ep.title,
					summary=mediainfo_ep.summary,
					thumb=mediainfo_ep.poster,
					art=mediainfo_ep.background,
				)
			)
			
	return oc

####################################################################################################

def TVSeasonActionMenu(mediainfo, path, parent_name=None):

	oc = ObjectContainer(view_group="InfoList", title1=parent_name, title2="Season Actions")
	
	oc.add(
		DirectoryObject(
			key=Callback(TVSeasonActionBuffer),
			title="Pre-Buffer All Episodes",
		)
	)

	if (Prefs['watched_indicator'] != 'Disabled'):
		oc.add(
			DirectoryObject(
				key=Callback(TVSeasonActionWatch, item_name=path[-1]['elem'], items=[[mediainfo, path]], action="watch"),
				title="Mark All Episodes as Watched",
			)
		)
	
		oc.add(
			DirectoryObject(
				key=Callback(TVSeasonActionWatch, item_name=path[-1]['elem'], items=[[mediainfo, path]], action="unwatch"),
				title="Mark All Episodes as Unwatched",
			)
		)
	
	# These won't get used and are keyed to a specific episode, so reset them.
	mediainfo.url = None
	mediainfo.summary = None

	# Come up with a nice easy title for later.
	mediainfo.title = mediainfo.show_name + " - Season " + str(mediainfo.season)

	fav_path = [item for item in path if ('season_url' in item or 'show_url' in item)]
	oc.add(
		DirectoryObject(
			key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo, path=fav_path, parent_name=oc.title2),
			title="Add Season to Favourites"
		)
	)
	
	return oc

####################################################################################################

def TVSeasonActionBuffer():


	oc = ObjectContainer()
	oc.header = "Not Yet Implemented."
	oc.message = ""
	
	return oc

####################################################################################################

def TVSeasonActionWatch(item_name=None, items=None, action="watch"):

	episode_items = []
	
	for item in items:
	
		mediainfo = item[0]
		path = item[1]

		base_path = [item for item in path if ('season_url' in item or 'show_url' in item)]
		season_url = [item for item in path if ('season_url' in item)][0]['season_url']
		
		episode_paths = []
		
		# Get a list of all the episodes for this season.
		for ep in Parsing.GetTVSeasonEps("/" + season_url):
		
			ep_path = copy.copy(base_path)
			ep_path.append({ 'elem': ep['ep_name'], 'url': ep['ep_url'] })
			episode_paths.append(ep_path)
		
		episode_items.append([mediainfo, episode_paths])
		
	# Mark them as watched / unwatched.
	return SourcesActionWatch(item_name=item_name, items=episode_items, action=action)


####################################################################################################
# SOURCES MENUS
####################################################################################################

def SourcesOrBufferMenu(mediainfo=None, url=None, item_name=None, path=[], parent_name=None, external_caller=None, replace_parent=False):

	oc = ObjectContainer(no_cache=True, view_group="List", title1=parent_name, title2="")

	buffer = BufferManager.instance()
	
	part_count = buffer.partCount(url)
		
	for cnt in range(0, part_count):
	
		title = "Play Pre-Bufferred Item"
		
		# Store the fact that this client maybe ready to play this video.
		# This will be used to cleanup the libraries we use.
		DictDefault("BUFFER_CLIENT_PLAY", {})[Request.Headers['X-Plex-Client-Identifier']] = buffer.fileLoc(url, 0)
		Dict.Save()
		
		if (part_count > 1):
			title = "Play Pre-Bufferred Part %s of %s" % (cnt + 1, part_count)
			
		oc.add(
			MovieObject(
				url="prebuffer://" + buffer.fileLoc(url, cnt),
				title=title
			)
		)
	
	oc.add(
		DirectoryObject(
			key=Callback(
				SourcesMenu,
				mediainfo=mediainfo,
				url=url,
				item_name=item_name,
				path=path,
				parent_name=oc.title2,
			),
			title="View Sources and Item Options",
		)
	)
	
	return oc

####################################################################################################

def SourcesMenu(mediainfo=None, url=None, item_name=None, path=[], parent_name=None, external_caller=None, replace_parent=False):
	
	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	# We may have gotten here after client stopped playing a pre-buffered item. Clean up time...
	BufferPlayClean()
	
	if (item_name is None):
		item_name = mediainfo.title
		if (mediainfo.year):
			item_name = item_name + " (" + str(mediainfo.year) + ") "
	
	path = path + [ { 'elem': item_name, 'url': url } ]
	
	oc = ObjectContainer(no_cache=False, view_group="List", title1=parent_name, title2=item_name)
	
	# Get as much meta data as possible about this item.
	mediainfo2 = Parsing.GetMediaInfo(url, mediainfo, need_meta_retrieve(mediainfo.type))
		
	# Did we get get any metadata back from meta data providers?
	if (mediainfo2 is None or mediainfo2.id is None):
		# If not, use the information we've collected along the way.
		mediainfo2 = mediainfo
	else:
		# We did, but do we know more than the meta data provider?
		# Copy some values across from what we've been passed from provider / have built up
		# as we're navigating if meta provider couldn't find data.
		if mediainfo2.poster is None:
			mediainfo2.poster = mediainfo.poster
		
		if mediainfo2.show_name is None:
			mediainfo2.show_name = mediainfo.show_name
			
		if mediainfo2.season is None:
			mediainfo2.season = mediainfo.season
			
		if mediainfo2.title is None:
			mediainfo2.title = item_name
	
	if (not external_caller):
		oc.add(
			PopupDirectoryObject(
				key=Callback(SourcesActionMenu, url=url, mediainfo=mediainfo2, path=path, parent_name=oc.title2),
				title=L("ItemSourceActionTitle"),
				summary=mediainfo2.summary,
				art=mediainfo2.background,
				thumb= mediainfo2.poster,
				duration=mediainfo2.duration,
			)
		)
	
	providerURLs = []
	mediaItems = []
	
	# Get a list of media items for each available source.
	for source_item in Parsing.GetSources(url):
	
		mediaItem = GetItemForSource(mediainfo=mediainfo2, source_item=source_item, parent_name=oc.title2)
		
		if mediaItem is not None and 'item' in mediaItem and mediaItem['item'] is not None:
			mediaItems.append(mediaItem['item'])
			if ('url' in mediaItem and mediaItem['url'] is not None):
				providerURLs.append(mediaItem['url'])
	
	for mediaItem in mediaItems:
		oc.add(mediaItem)
		
	if (not external_caller and len(Dict[ADDITIONAL_SOURCES_KEY]) > 0):
		oc.add(
			DirectoryObject(
				key=Callback(SourcesAdditionalMenu, mediainfo=mediainfo2),
				title="Additional Sources...",
				#art=mediainfo2.background,
				thumb=R(ADDITIONAL_SOURCES_ICON),
			)
		)
		
	if len(providerURLs) == 0:
		oc.header = "No Enabled Sources Found"
		oc.message = ""
	else:
		# Add this to the recent items list so we can cross reference that
		# with any playback events.
		if (Data.Exists(BROWSED_ITEMS_KEY)):
			browsedItems =  cerealizer.loads(Data.Load(BROWSED_ITEMS_KEY))
		else:
			browsedItems = BrowsedItems()
		
		browsedItems.add(mediainfo2, providerURLs, path, external_caller)
		Data.Save(BROWSED_ITEMS_KEY, cerealizer.dumps(browsedItems))
		
		#Log("Browsed items: " + str(browsedItems))
		
	return oc

####################################################################################################

def SourcesPartMenu(mediainfo, source_item, part_count, parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	oc = ObjectContainer(view_group="List", title1=parent_name, title2="Parts")
	providerURLs = []
	
	for cnt in range(0, part_count):
	
		item = GetItemForSource(
			mediainfo=mediainfo,
			source_item=source_item, 
			parent_name=oc.title2,
			part_index=cnt
		)
			
		if item is not None and 'item' in item and item['item'] is not None:
		
			item['item'].title = "Part %s" % (cnt + 1)
			oc.add(item['item'])
			
			if ('url' in item and item['url'] is not None):
			
				providerURLs.append(item['url'])
				
	# Add our providerURLs to existing list.
	if (Data.Exists(BROWSED_ITEMS_KEY)):
	
		browsedItems =  cerealizer.loads(Data.Load(BROWSED_ITEMS_KEY))
		browsedItems.append(mediainfo, providerURLs)
		Data.Save(BROWSED_ITEMS_KEY, cerealizer.dumps(browsedItems))
		
	return oc
	
####################################################################################################

def SourcesAdditionalMenu(mediainfo):

	# FIXME: This assumes only 1 additional source is available.

	# See which additional sources are available.	
	url = "http://localhost:32400/video/" + Site.ADDITIONAL_SOURCES[0] + "/sources/" + mediainfo.id
	
	if (mediainfo.type == 'movies'):
		url += "/" + urllib.quote(mediainfo.title)
	else:
		url += "/" + urllib.quote(mediainfo.show_name) + "/" + str(mediainfo.season) + "/" + str(mediainfo.ep_num)
	
	#Log(url)
	
	# Can't use Redirect as it doesn't seem to be supported by some clients <sigh>
	# So get the data for them instead by manually doing the redirect ourselves.
	request = urllib2.Request(url)
	request.add_header('Referer', PLUGIN_URL)
	return urllib2.urlopen(request).read()


####################################################################################################

def SourcesActionMenu(mediainfo, path, url, parent_name):

	oc = BufferActionMenu(url=url, mediainfo=mediainfo, path=path, parent_name=parent_name)
	oc.no_cache = True
	
	if (len(oc.objects) > 1):
		oc.add(
			DirectoryObject(
				key=Callback(NoOpMenu),
				title=L("NoOpTitle")
			)
		)

	if (mediainfo.type == "movies"):
	
		oc.add(
			DirectoryObject(
				key=Callback(SourcesActionTrailerMenu, mediainfo=mediainfo, path=path),
				title="View Trailer",
			)
	)

	if (
		Prefs['watched_indicator'] == 'All' 
		or ( mediainfo.type == 'tv' and Prefs['watched_indicator'] != 'Disabled')
	):
		title = "Mark as Watched"
		action = "watch"
		hist = load_watched_items()
		
		if (hist.has_been_watched(path[-1]['url'])):
			title = "Mark as Unwatched"
			action = "unwatch"
			
		oc.add(
			DirectoryObject(
				key=Callback(SourcesActionWatch, item_name=path[-1]['elem'], items=[[mediainfo, [path]]], action=action),
				title=title,
			)
		)
	
	if (mediainfo.type == "movies"):
		oc.add(
			DirectoryObject(
				key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo, path=[path[-1]], parent_name=oc.title2),
				title="Add to Favourites",
			)
		)
		
	if (len(oc.objects) == 0):
		oc.add(
			DirectoryObject(
				key=Callback(NoOpMenu),
				title="No Options Available",
			)
		)

		oc.header="No Options Available"
		oc.message="No options currently available for this item. Enable Watched indicators to get options."
		
	return oc

####################################################################################################

def SourcesActionTrailerMenu(mediainfo, path):

	try:
		result = SearchService.Query(str(mediainfo.title), "com.plexapp.plugins.amt", None)
	except KeyError, ex:
		return MessageContainer(
			"'Apple Movie Trailers' plugin not found.",
			"Please install the 'Apple Movie Trailers' plugin from the Channel Directory to view trailers."
		)
	except Exception, ex:
		return MessageContainer(
			"No Trailers Found",
			"Couldn't find any trailers for this movie.\nMovie Name: " + str(mediainfo.title)
		)
		
	objects = []
	for object in result.objects:
		
		title = object.title
		match = re.match("(.*) \(.*\)",title)
		
		if match:
			title = match.group(1)
		
		if (String.LevenshteinDistance(str(mediainfo.title).lower(), title.lower()) <= 3):
			objects.append(object)
			
	
	if (len(objects) == 0):
		return MessageContainer(
			"No Trailers Found",
			"Couldn't find any trailers for this movie.\nMovie Name: " + str(mediainfo.title)
		)
	else:
	
		# Resort objects so that trailers appear first in the list.
		objects = sorted(
			objects, 
			key=lambda x: "AA" + x.title.replace(" ","") if x.title.lower().find("(trailer") != -1 else x.title
		)
			
		return ObjectContainer(
			no_cache=True,
			title1=str(mediainfo.title),
			title2="Trailers",
			objects = objects,
			art=mediainfo.background,
		)
		
	return oc
	
	
####################################################################################################

def SourcesActionWatch(item_name=None, items=None, action="watch"):

	oc = ObjectContainer(title1="", title2="")
	
	watched_favs = []
	hist = load_watched_items()

	for item in items:
	
		mediainfo = item[0]
		paths = item[1]
		
		for path in paths:
			if (action == "watch"):
				hist.mark_watched(path)
			else:
				hist.mark_unwatched(path[-1]['url'])
				
	save_watched_items(hist)
	
	# Deal with Favourites.
	if (action == "watch"):
		
		# Favourites keep their own list of what shows they consider to have been watched
		Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
		
		try:
			favs = load_favourite_items()
			for item in items:
				mediainfo = item[0]
				paths = item[1]
				for path in paths:
					watched_favs.extend(favs.watch(mediainfo, path[-1]['url']))
			save_favourite_items(favs)
		except Exception, ex:
			Log.Exception("Error marking favourite as watched")
			pass		
		finally:
			Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
		
		for fav in set(watched_favs):
			Thread.Create(CheckForNewItemsInFavourite, favourite=fav, force=True)


	# Normal processing.
	if (action == "watch"):
		oc.header = L("ItemSourceActionMarkAsWatchedHeader")
		oc.message = str(L("ItemSourceActionMarkAsWatchedMessage")) % item_name	
	else:
		oc.header = L("ItemSourceActionMarkAsUnwatchedHeader")
		oc.message = str(L("ItemSourceActionMarkAsUnwatchedMessage")) % item_name

	return oc
	
####################################################################################################

def CaptchaRequiredMenu(mediainfo, source_item, url, parent_name=None, replace_parent=False):

	# Cache required as some clients will re-request menu after looking at captcha image.
	oc = ObjectContainer(no_cache=False, view_group="InfoList", user_agent=USER_AGENT, no_history=True, title1=parent_name, title2="Captcha", replace_parent=replace_parent)
		
	# Get the media sources for the passed in URL.
	# This should be made up of two Media Objects:
	#  1) URL of the CAPTCHA
	#  2) New URL of the video to play
	
	media_objects = URLService.MediaObjectsForURL(url)
	
	captcha_img_URL = media_objects[0].parts[0].key
	solve_captcha_URL = media_objects[1].parts[0].key
	
	#Log("In captchaRequiredMenu, url: " + url + ", captcha_img_URL:" + captcha_img_URL + ", solve_captcha_URL: " + solve_captcha_URL)
	
	oc.add(
		InputDirectoryObject(
			key=Callback(CaptchaProcessMenu, mediainfo=mediainfo, source_item=source_item, url=url, solve_captcha_url=solve_captcha_URL, parent_name=oc.title1),
			title="Enter Captcha...",
			prompt="Enter Captcha to view item.",
			tagline="This provider requires that you solve this Captcha.",
			summary="This provider requires that you solve this Captcha.",
			thumb=PLUGIN_URL + "/proxy?" + urllib.urlencode({'url':captcha_img_URL}),
			art=mediainfo.background,
		)
	)
	
	return oc

####################################################################################################

def CaptchaProcessMenu(query, mediainfo, source_item, url, solve_captcha_url, parent_name=None):

	oc = ObjectContainer(
			view_group="InfoList", user_agent=USER_AGENT, no_history=True, replace_parent=True,
			title1=parent_name, title2="Succesful Captcha"
	)
	
	#Log("In captchaProcessMenu, url: " + url + ", solveCaptchaURL:" + solve_captcha_url)

	# Some clients (I'm looking at you here iOS) seem to ignore the URLService resolved parts that
	# get added when this is returned to it and instead re-request the main video clip object's URL
	# to get it resolved again when the user chooses to play the video. Because Captcha's are a
	# one go only affair, the second call fails and the URL dosen't end up being resolved. And
	# then we have a sad client with no videos :( So, instead, manually resolve the post-Captcha
	# URL here so we can set that in the VideoClipObject.
	try:
		video_media = URLService.MediaObjectsForURL(solve_captcha_url + "&" + urllib.urlencode({"captcha":query}))
	except Exception, ex:
		# Something went wrong. Chances are the Captcha is wrong. Go back and load a new one.
		# FIXME: Need tighter error checking.
		return CaptchaRequiredMenu(mediainfo=mediainfo, source_item=source_item, url=url, parent_name=parent_name, replace_parent=True)
			
	video_url = video_media[0].parts[0].key
	
	# The url arg is still the original URL returned by GetItemForSource and will be the one that
	# was used to store all the different possible URLs for the current item. Pass that along to
	# the current site's playURL so that it can mark the video has played when the user selects
	# the VideoClipObjecy.
	if (hasattr(Site,"GetCaptchaPlayURL")):
		video_url = Site.GetCaptchaPlayURL() % (urllib.quote_plus(url), urllib.quote_plus(video_url))

	vc = VideoClipObject(
		url=video_url,
		title="Play Now",
		summary=mediainfo.summary,
		art=mediainfo.background,
		thumb= mediainfo.poster,
		rating = float(mediainfo.rating) if mediainfo.rating else None,
		duration=mediainfo.duration,
		year=mediainfo.year,
		originally_available_at=mediainfo.releasedate,
		genres=mediainfo.genres,
	)
				
	oc.add(vc)
	
	return oc
	
# Utility methods for captchas. All requests in the Captcha cycle must come from the same User-Agent
# If just let the clients load the Captcha image, we get different User-Agents. Some us libcurl and
# it'd be possible to force a specific user agent using the "url|extraparams" notation, however some
# clients use the transcoder which does it's own separate thing and doesn't understand libcurl params.
# So, instead, we rewrite the Captcha's image URL to pass through this, so we can forcibly set
# the user-agent.
#
# Yup.... This is all rubbish.
@route(VIDEO_PREFIX + '/proxy')
def Proxy(url):

	#Log(url)
	return HTTP.Request(url,headers={'User-Agent':USER_AGENT}).content
	
####################################################################################################

def SearchResultsMenu(query, type, parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	oc = ObjectContainer(no_cache=True, view_group = "InfoList", title1=parent_name, title2="Search (" + query + ")")

	path = [ { 'elem':'Search (' + query + ')', 'query': query }]
	
	func_name = TVShowMenu
	if (type=="movies"):
		func_name = SourcesMenu
		
	exact = False
	
	# Strip out the year out of the given search term if one is found.
	# This helps auto-complete work on the Roku client which runs searches
	# as users are entering data  and then lets users select those results
	# as a new search term.
	
	if (re.search("\s*\(\d*\)", query)):
		query = re.sub("\s*\(\d*\)\s*","",query)
		exact = True
		
	for item in Parsing.GetSearchResults(query=query, type=type, exact=exact):
		title = item.title + " (" + str(item.year) + ")" if item.year else item.title
		oc.add(
			DirectoryObject(
				key=Callback(func_name, mediainfo=item, url=item.id, path=path, parent_name=oc.title2),
				title=title,
				tagline="",
				summary="",
				thumb=item.poster,
				art="",
			)
		)
		
	if (len(oc) <= 0):
		oc.header = "Zero Matches"
		oc.message = "No results found for your query \"" + query + "\""

	return oc


####################################################################################################
# BUFFERING MENU
####################################################################################################

def BufferMenu(parent_name=None, replace_parent=False):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	# We may have gotten here after client stopped playing a pre-buffered item. Clean up time...
	BufferPlayClean()
	
	oc = ObjectContainer(no_cache=True, view_group="InfoList", title1=parent_name, title2=L("BufferTitle"), replace_parent=replace_parent)
	
	buffer = BufferManager.instance()
	items = buffer.items()
	
	if (len(items) == 0):
		oc.add(
			DirectoryObject(
				key=Callback(NoOpMenu),
				title= "No Pre-Buffering items found.",
			)
		)
		
		return oc
	
	itemsGroups = { 'Ready':[], 'Active':[], 'Queued': [], 'Stopped':[], 'No Source':[] }
	summaries = {
		'Ready': 'The items below are fully buffered and ready to play.',
		'Active': 'The items below are currently buffering. Click on an item for more options.',
		'Queued': 'The items below are currently queued to be buffered. They will begin buffering shortly after a buffering slot becomes available.',
		'Stopped': 'The items below are currently stopped. They will not be buffered until manually resumed. Click on an item for options.',
		'No Source': 'The items below have tried all the sources they know about and found none with a valid file. You can try again by clicking an item and selecting "Resume"',
	}
	# Group items into Ready, Active, Stopped and No Source groups.
	for itemKey in items:
	
		item = buffer.bufferItem(itemKey)
		if (item.isFinished()):
			itemsGroups['Ready'].append(itemKey)
		elif (item.isActive()):
			itemsGroups['Active'].append(itemKey)
		elif (item.isQueued()):
			itemsGroups['Queued'].append(itemKey)
		elif (item.isStopped()):
			itemsGroups['Stopped'].append(itemKey)
		elif (item.isNoSource()):
			itemsGroups['No Source'].append(itemKey)
	
	
	for groupKey in ['Ready', 'Active', 'Queued', 'Stopped', 'No Source']:
	
		if (len(itemsGroups[groupKey]) >= 1):
		
			oc.add(
				DirectoryObject(
					key=Callback(BufferMenu, parent_name=parent_name, replace_parent=True),
					title= "-- " + groupKey + ' --',
					summary = summaries[groupKey] + "\n\n" + "Click to refresh list",
				)
			)
			
			for itemKey in itemsGroups[groupKey]:
			
				adtlInfo = buffer.adtlInfo(itemKey)
				mediainfo = MediaInfo()
				path = []
				
				if (adtlInfo is not None):
					if ('mediainfo' in adtlInfo):
						mediainfo = adtlInfo['mediainfo']
					if ('path' in adtlInfo):
						path = adtlInfo['path']
				
				title = mediainfo.title
				
				if (groupKey == 'Active'):
					# Show basic stats...
					stats = buffer.stats(itemKey)
					title = title + (" (%s@%s)" % (stats["timeRemainingShort"], stats["curRate"]))
				
				oc.add(
					PopupDirectoryObject(
						key=Callback(BufferActionMenu, mediainfo=mediainfo, path=path, parent_name=oc.title2, url=itemKey, show_path=True),
						title=title,
						summary= mediainfo.summary,
						art=mediainfo.background,
						thumb= mediainfo.poster,
					)
				)

	return oc
	
####################################################################################################
	
def BufferActionMenu(url, mediainfo=None, path=None, parent_name=None, caller=None, show_path=False):

	oc = ObjectContainer(no_cache=True, view_group="InfoList", title1=parent_name, title2=L("BufferTitle") + " Actions")
	
	buffer = BufferManager.instance()
	
	# If we've been given a path, add navigation back to the item.		
	if (buffer.hasItem(url)):
	
		if (buffer.isReady(url)):

			part_count = buffer.partCount(url)

			# Store the fact that this client maybe ready to play this video.
			# This will be used to cleanup the libraries we use.
			DictDefault("BUFFER_CLIENT_PLAY",{})[Request.Headers['X-Plex-Client-Identifier']] = buffer.fileLoc(url, 0)
			Dict.Save()
			
			for cnt in range(0, part_count):
			
				title = "Play Pre-Bufferred Item"
				
				if (part_count > 1):
					title = "Play Pre-Bufferred Part %s of %s" % (cnt + 1, part_count)
					
				oc.add(
					MovieObject(
						url="prebuffer://" + buffer.fileLoc(url, cnt),
						title=title
					)
				)

			oc.add(
				DirectoryObject(
					key=Callback(BufferMoveToLibMenu, url=url),
					title="Move Item to Library",
				)
			)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferDelMenu, url=url),
					title="Delete Item",
				)
			)
					
		elif buffer.isActive(url):
		
			if (caller != "stats"):
				stats = BufferManager.instance().stats(url)
				title = "View Stats "
				if (stats["fileSize"] == "-"):
					title = title + "(%s)" % stats['status']
				else:
					title = title + ("(%s@%s)" % (stats["timeRemainingShort"], stats["curRate"]))
				oc.add(
					DirectoryObject(
						key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url),
						title=title,
					)
				)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferNextSourceMenu, url=url),
					title="Try Another Source",
				)
			)

			oc.add(
				DirectoryObject(
					key=Callback(BufferStopMenu, url=url),
					title="Stop",
				)
			)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferStopAndDelMenu, url=url),
					title="Stop and Delete",
				)
			)
			
		elif buffer.isQueued(url):
		
			if (caller != "stats"):
				stats = BufferManager.instance().stats(url)
				title = "View Stats "
				if (stats["fileSize"] == "-"):
					title = title + "(%s)" % stats['status']
				else:
					title = title + ("(%s@%s)" % (stats["timeRemainingShort"], stats["curRate"]))
				oc.add(
					DirectoryObject(
						key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url),
						title=title,
					)
				)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferStopMenu, url=url),
					title="Stop",
				)
			)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferStopAndDelMenu, url=url),
					title="Stop and Delete",
				)
			)
		
		else:
		
			if (caller != "stats"):
				stats = BufferManager.instance().stats(url)
				title = "View Stats "
				if (stats["fileSize"] == "-"):
					title = title + "(%s)" % stats['status']
				else:
					title = title + ("(%s/%s)" % (stats["downloaded"], stats["fileSize"]))
				oc.add(
					DirectoryObject(
						key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url),
						title=title,
					)
				)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferResumeMenu, url=url),
					title="Resume",
				)
			)
			
			oc.add(
				DirectoryObject(
					key=Callback(BufferDelMenu, url=url),
					title="Delete",
				)
			)
			
	else:
		# This is here purely for when called from SourceActionMenu
		oc.add(
			DirectoryObject(
				key=Callback(BufferStartMenu, url=url, mediainfo=mediainfo, path=path),
				title="Start Pre-Buffering",
			)
		)
	
	# Add path navigation back to item if requested and we have a valid path.
	if (path is not None and len(path) >= 1 and show_path):
		
		oc.add(
			DirectoryObject(
				key=Callback(NoOpMenu),
				title=L("NoOpTitle")
			)
		)
		
		# Grab a copy of the path we can update as we're iterating through it.
		cur_path = list(path)
		
		# The path as stored in the system is top down. However, we're going to
		# display it in reverse order (bottom up), so match that.
		cur_path.reverse()
			
		for item in reversed(path):
		
			# When the users select this option, the selected option will automatically
			# be re-added to the path by the called menu function. So, remove it now so
			# we don't get duplicates.
			if (len(cur_path) > 0):
				cur_path.pop(0)
						
			# The order in which we're processing the path (bottom up) isn't the 
			# same as how it was navigated (top down). So, reverse it to
			# put in the right order to pass on to the normal navigation functions.
			ordered_path = list(cur_path)
			ordered_path.reverse()
		
			# Depending on the types of args present, we may end up calling different methods.
			#
			# If we have an item URL, take user to provider list for that URL
			if ("url" in item):
				callback = Callback(
					SourcesMenu, mediainfo=mediainfo, url=item['url'], item_name=None, path=ordered_path, parent_name=oc.title2)
				
			# If we have a show URL, take user to season listing for that show
			elif ("show_url" in item):
				callback = Callback(TVShowMenu, mediainfo=mediainfo, url=item['show_url'], item_name=mediainfo.show_name, path=ordered_path, parent_name=oc.title2)
			
			# If we have a season URL, take user to episode listing for that season.
			elif ("season_url" in item):
				callback = Callback(TVSeasonMenu, mediainfo=mediainfo, season_url=item['season_url'], item_name="Season " + str(mediainfo.season), path=ordered_path, parent_name=oc.title2)
			
			oc.add(
				DirectoryObject(
					key=callback,
					title=item['elem']
				)
			)
	
	return oc

####################################################################################################

def BufferStartMenu(url, mediainfo, path):

	oc = ObjectContainer()
	buffer = BufferManager.instance()
	providers = []
	
	# Loop through each source...
	for source_item in Parsing.GetSources(url):
	
		items = []
		
		# Get the media items for the current source.
		item =  Parsing.GetItemForSource(mediainfo, source_item, None)
		items.append(item)
		
		if item and isinstance(item, MultiplePartObject):
		
			Log("*** Found multi-part object with %s parts." % item.part_count)
			# Retrieve the media item for each part.
			for cnt in range(0, item.part_count):
				items.append(Parsing.GetItemForSource(mediainfo, source_item, cnt))
		
		# Grab valid URLs out of all the media items we've seen for this source.
		itemUrls = []
		
		# Process all the media items we got and look for VideoItems to add to the list of
		# parts for this source.
		for item in items:
			if item and isinstance(item, VideoClipObject):
				itemUrls.append(item.url)
		
		if len(itemUrls) > 0:
			providers.append(
				{ 'provider': source_item['provider_name'], 'parts': itemUrls }
			)	

	if (len(providers) > 0):
	
		buffer.create(url, adtlInfo={'mediainfo': mediainfo, 'path': path})
		buffer.addSources(url, providers)
		buffer.launch()
		
		oc.header = "Pre-Buffering Launched"
		oc.message = "Pre-Buffering for this items has started with %s possible sources." % str(len(providers))
		
	else:
	
		oc.header = "No suitable sources found"
		oc.message = "Can not pre-buffer this item as no suitable sources have been found."
		
	return oc
	

####################################################################################################

def BufferResumeMenu(url):

	oc = ObjectContainer()
	
	BufferManager.instance().resume(url)
	oc.header = "Pre-Buffering resumed for this item."
	oc.message = "Item has been added to end of pre-buffering queue."
	
	return oc

####################################################################################################

def BufferStopMenu(url):

	oc = ObjectContainer()
	
	if (BufferManager.instance().stop(url)):
		oc.header = "Pre-Buffering paused for this item."
		oc.message = ""
	else:
		oc.header = "Stopping failed."
		oc.message = "Download thread failed to pickup stop event.\nRestarting PMS will ensure the thread is killed."
	
	return oc

####################################################################################################

def BufferMoveToLibMenu(url):

	oc = ObjectContainer()
	oc.header = "Not Yet Implemented."
	oc.message = ""
	
	return oc


####################################################################################################

def BufferDelMenu(url):

	BufferManager.instance().remove(url)
	
	oc = ObjectContainer()
	oc.header = "Pre-Buffered item deleted"
	oc.message = ""
	
	return oc
	
####################################################################################################

def BufferStopAndDelMenu(url):

	BufferManager.instance().stopAndRemove(url)
	
	oc = ObjectContainer()
	oc.header = "Pre-Buffered item deleted"
	oc.message = ""
	
	return oc
	
####################################################################################################

def BufferNextSourceMenu(url):

	oc = ObjectContainer()
	
	if (BufferManager.instance().nextSource(url)):
		oc.header = "Switching to new pre-buffering source."
		oc.message = ""
	else:
		oc.header = "Source Switch Failed"
		oc.message = "Thread failed to pickup source switch event within allocated time.\nYou may need to wait a little while for thread to pickup signal."
		
	return oc
	
####################################################################################################

def BufferStatsMenu(mediainfo, parent_name, url, replace_parent=False):

	oc = ObjectContainer(no_cache=True,title1=parent_name, title2="Pre-Buffering Progress",replace_parent=replace_parent)
	
	buffer = BufferManager.instance()
	stats = buffer.stats(url)
	
	# We may have gotten here after client stopped playing a pre-buffered item. Clean up time...
	BufferPlayClean()
	
	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Status: %s" % stats["status"],
			summary="Click on any item to update stats with current values.",
			art=mediainfo.background,
			thumb= mediainfo.poster,
		)
	)
	
	oc.add(
		PopupDirectoryObject(
			key=Callback(BufferActionMenu, url=url, caller="stats"),
			title="Pre-Buffer Actions...",
			summary="Manage pre-buffer item.",
			art=mediainfo.background,
			thumb= mediainfo.poster,
		)
	)
			
	title = "Source Name: %s" % stats['provider']
	if stats['partCount'] > 1:
		title = title + " - %s part(s)" % stats['partCount']
		
	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title=title,
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)

	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Downloaded: %s of %s (%s%%)" % (stats["downloaded"], stats["fileSize"], stats["percentComplete"]),
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)
	
	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Time Remaining: %s" % stats["timeRemaining"],
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)

	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Current Rate: %s" % stats["curRate"],
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)
	
	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Average Rate: %s" % stats["avgRate"],
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)

	
	oc.add(
		DirectoryObject(
			key=Callback(BufferStatsMenu, mediainfo=mediainfo, parent_name=parent_name, url=url, replace_parent=True),
			title="Active for: %s" % stats["timeElapsed"],
			summary=mediainfo.summary,
			art=mediainfo.background,
			thumb= mediainfo.poster,

		)
	)
	
	return oc

####################################################################################################

def BufferPlayClean():

	clients = DictDefault("BUFFER_CLIENT_PLAY", {})
	Log("*** Current clients play list: %s" % clients)
	
	if (Request.Headers['X-Plex-Client-Identifier'] in clients):
	
		path = clients[Request.Headers['X-Plex-Client-Identifier']]
		Log("*** Should be trying to remove %s from Pre-Play library" % path)
		del clients[Request.Headers['X-Plex-Client-Identifier']]
		
		# Remove path from library.
		# FIXME: Need to check no-one else is also playing this item.
		BufferDelPathFromLib(String.Encode(path))

		
####################################################################################################
# HISTORY MENU
####################################################################################################

def HistoryMenu(parent_name=None):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()

	oc = ObjectContainer(no_cache=True, view_group="InfoList", title1=parent_name, title2=L("HistoryTitle"))
	
	history = load_watched_items().get_recent(Prefs['watched_grouping'], int(Prefs['watched_amount']))
	
	# For each viewed video. 
	for item in history:
		
		mediainfo = item[0]
		navpath = item[1]
			
		title = ''
		poster = mediainfo.poster
		
		if (mediainfo.type == 'tv'):
			
			# If the item is a TV show, come up with sensible display info
			# that matches the requested grouping.
			summary = None

			if hasattr(mediainfo,"show_poster"):
				poster = mediainfo.show_poster
			
			if (mediainfo.show_name is not None):
				title = mediainfo.show_name
				
			if (
				(Prefs['watched_grouping'] == 'Season' or Prefs['watched_grouping'] == 'Episode') and
				mediainfo.season is not None
			):
				title += ' - Season ' + str(mediainfo.season)
				
				# If we have a season poster available, use that rather than show's poster.
				#Log("Checking for season poster.....")
				if hasattr(mediainfo,"season_poster") and mediainfo.season_poster:
					poster = mediainfo.season_poster
				
			if (Prefs['watched_grouping'] == 'Episode'):
				title = title + ' - ' + str(mediainfo.title)
				poster = mediainfo.poster
				summary = mediainfo.summary
				
		else:
			title = str(mediainfo.title)
			summary = mediainfo.summary
			
		oc.add(
			PopupDirectoryObject(
				key=Callback(HistoryNavPathMenu,mediainfo=mediainfo,navpath=navpath,parent_name=oc.title1),
				title=title,
				summary=summary,
				art=mediainfo.background,
				thumb=poster,
				duration=mediainfo.duration,
				
			)
		)
			
	oc.add(
		PopupDirectoryObject(
			key=Callback(HistoryClearMenu, parent_name=parent_name),
			title=L("HistoryClearTitle"),
			summary=L("HistoryClearSummary"),
			thumb=None,
		)
	)
	
	return oc

####################################################################################################

def HistoryClearMenu(parent_name=None):

	oc = ObjectContainer(no_cache=True, title1="", title2="")
	
	oc.add(
		DirectoryObject(
			key=Callback(HistoryClearRecent, parent_name=parent_name),
			title=L("HistoryClearRecentTitle"),
			summary=L("HistoryClearRecentSummary"),
		)
	)
	
	oc.add(
		DirectoryObject(
			key=Callback(HistoryClearAll, parent_name=parent_name),
			title=L("HistoryClearAllTitle"),
			summary=L("HistoryClearAllSummary"),
		)
	)
	
	return oc
	
####################################################################################################

def HistoryClearRecent(parent_name=None):

	hist = load_watched_items()
	hist.clear_recent()
	save_watched_items(hist)
	
	oc = HistoryMenu(parent_name=parent_name)
	oc.replace_parent = True
	return oc
	
####################################################################################################

def HistoryClearAll(parent_name=None):

	Data.Remove(WATCHED_ITEMS_KEY)
	Data.Remove(BROWSED_ITEMS_KEY)
	
	oc = HistoryMenu(parent_name=parent_name)
	oc.replace_parent = True
	return oc

####################################################################################################

def HistoryNavPathMenu(mediainfo, navpath, parent_name):

	oc = ObjectContainer(title1=parent_name, title2=L("HistoryTitle"))
	
	# Grab a copy of the path we can update as we're iterating through it.
	path = list(navpath)
	
	# The path as stored in the system is top down. However, we're going to
	# display it in reverse order (bottom up), so match that.
	path.reverse()
		
	for item in reversed(navpath):
	
		# When the users select this option, the selected option will automatically
		# be re-added to the path by the called menu function. So, remove it now so
		# we don't get duplicates.
		if (len(path) > 0):
			path.pop(0)		
	
		# The order in which we're processing the path (bottom up) isn't the 
		# same as how it was navigated (top down). So, reverse it to
		# put in the right order to pass on to the normal navigation functions.
		ordered_path = list(path)
		ordered_path.reverse()
	
		# Depending on the types of args present, we may end up calling different methods.
		#
		# If we have a query term, take user to search results.
		if ("query" in item):
			callback = Callback(
				SearchResultsMenu, query=item['query'], type=mediainfo.type, parent_name=oc.title2
			)
		# If we have an item URL, take user to provider list for that URL
		elif ("url" in item):
			if (mediainfo.type == 'tv' and Prefs['watched_grouping'] != 'Episode'):
				continue
			else:
				callback = Callback(
					SourcesMenu, mediainfo=mediainfo, url=item['url'], item_name=None, path=ordered_path, parent_name=oc.title2)
			
		# If we have a show URL, take user to season listing for that show
		elif ("show_url" in item):
			callback = Callback(TVShowMenu, mediainfo=mediainfo, url=item['show_url'], item_name=mediainfo.show_name, path=ordered_path, parent_name=oc.title2)
		
		# If we have a season URL, take user to episode listing for that season.
		elif ("season_url" in item):
			if (Prefs['watched_grouping'] == 'Season' or Prefs['watched_grouping'] == 'Episode'):
				callback = Callback(TVSeasonMenu, mediainfo=mediainfo, season_url=item['season_url'], item_name="Season " + str(mediainfo.season), path=ordered_path, parent_name=oc.title2)
			else:
				continue
		
		# If we have a type but no sort, this is first level menu
		elif ("type" in item and "sort" not in item):
			callback = Callback(TypeMenu, type=item['type'], genre=item['genre'], path=ordered_path, parent_name=oc.title2)

		# Must be item list.
		else:
			callback = Callback(ItemsMenu, type=item['type'], genre=item['genre'], sort=item['sort'], alpha=item['alpha'], section_name=item['section_name'], start_page=0, path=ordered_path, parent_name=oc.title2)
		
		oc.add(
			DirectoryObject(
				key=callback,
				title=item['elem']
			)
		)
	
	oc.add(
		DirectoryObject(
			key=Callback(NoOpMenu),
			title=L("NoOpTitle")
		)
	)
	
	# Remove from recently watched list.
	oc.add(
		DirectoryObject(
			key=Callback(HistoryRemoveFromRecent, mediainfo=mediainfo, path=path, parent_name=oc.title2),
			title=L("HistoryRemove")
		)
	)
			
	
	# Add to Favourites menu options.
	# Deal with the fact that the path to be added to favourites is different
	# based on type of item this is.
	if (mediainfo.type == 'tv'):
	
		# These won't get used and are keyed to a specific episode, so reset them.
		mediainfo.url = None
		mediainfo.summary = None
				
		# Come up with a nice easy title for later.
	
		if (Prefs['watched_grouping'] != 'Show'):
		
			mediainfo_season = copy.copy(mediainfo)
			mediainfo_season.title = mediainfo.show_name + ' - Season ' + str(mediainfo.season)
			if hasattr(mediainfo_season,"season_poster") and mediainfo_season.season_poster:
				mediainfo_season.poster = mediainfo_season.season_poster
				
			path = [item for item in navpath if ('season_url' in item or 'show_url' in item)]
			oc.add(
				DirectoryObject(
					key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo_season, path=path, parent_name=oc.title2),
					title=str(L("HistoryAddToFavouritesItem")) % path[-1]['elem']
				)
			)
			
		mediainfo.title = mediainfo.show_name
		mediainfo.season = None
		
		if hasattr(mediainfo,"show_poster") and mediainfo.show_poster:
				mediainfo.poster = mediainfo.show_poster
		
		path = [item for item in navpath if ('show_url' in item)]
		
		if (Prefs['watched_grouping'] == 'Show'):
			title = L("HistoryAddToFavourites")
		else:
			title=str(L("HistoryAddToFavouritesItem")) % path[0]['elem']
			
		oc.add(
			DirectoryObject(
				key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo, path=[path[0]], parent_name=oc.title2),
				title=title
			)
		)
		
	else:
		oc.add(
			DirectoryObject(
				key=Callback(HistoryAddToFavouritesMenu, mediainfo=mediainfo, path=[navpath[-1]], parent_name=oc.title2),
				title=L("HistoryAddToFavourites")
			)
		)
		
	return oc

####################################################################################################

def HistoryRemoveFromRecent(mediainfo, path, parent_name):

	hist = load_watched_items()
	hist.remove_from_recent(mediainfo, Prefs['watched_grouping'])
	save_watched_items(hist)
	
	oc = HistoryMenu(parent_name=parent_name)
	oc.replace_parent = True
	return oc
	
####################################################################################################

def HistoryAddToFavouritesMenu(mediainfo, path, parent_name):

	# Keep it simple. Add given item and path to favourites.
	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	try:
		favs = load_favourite_items()
		favs.add(mediainfo, path)
		save_favourite_items(favs)
	except Exception, ex:
		Log.Exception("Error adding watched item to favourites")
		pass		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
		
	# If we have any labels for favourites, allow user to add labels now.
	if (Prefs['favourite_add_labels']):
		return FavouritesLabelsItemMenu(mediainfo, parent_name)
	else:	
		# Otherwise, just show them a message.
		oc = ObjectContainer(title1=parent_name, title2=L("HistoryAddToFavourites"))
		oc.header = L("HistoryFavouriteAddedTitle")
		oc.message = str(L("HistoryFavouriteAddedMsg")) % path[-1]['elem']
		
		return oc


####################################################################################################
# FAVOURITES MENUS
####################################################################################################

def FavouritesMenu(parent_name=None,label=None, new_items_only=None, replace_parent=False):

	Dict[LAST_USAGE_TIME_KEY] = datetime.utcnow()
	
	oc = ObjectContainer(
		no_cache=True, view_group="InfoList", replace_parent=replace_parent,
		title1=parent_name, title2=L("FavouritesTitle")
	)
	
	if label:
		oc.title2 = label
		if new_items_only:
			oc.title2 =  label + " (New Items)"
	else:
		if new_items_only:
			oc.title2 =  L("FavouritesTitleNewOnly")
	
	sort_order = FavouriteItems.SORT_DEFAULT
	if (Prefs['favourite_sort'] == 'Alphabetical'):
		sort_order = FavouriteItems.SORT_ALPHABETICAL
	elif (Prefs['favourite_sort'] == 'Most Recently Used'):
		sort_order = FavouriteItems.SORT_MRU
		
	oc.add(
		PopupDirectoryObject(
			key=Callback(
				FavouritesActionMenu,
				parent_name=parent_name,
				new_items_only=new_items_only,
				label=label,
			),
			title=L("FavouritesActionTitle"),
			thumb="",
		)
	)
		
	favs = load_favourite_items()
	
	if (not label):
	
		cnt = 0
		
		for existing_label in favs.get_labels():
		
			new_item = len([x for x in favs.get_favourites_for_label(existing_label) if x.new_item]) > 0
			
			if (not new_item and new_items_only):
				continue

			new_item_label = u"\u00F8" + "  " if (new_item) else '    '
			
			oc.add(
				DirectoryObject(
					key=Callback(
						FavouritesMenu,
						parent_name=oc.title2,
						new_items_only=new_items_only,
						label=existing_label
					),
					title=new_item_label + existing_label + " >",
					thumb=R(TAG_ICON % TAG_ICON_COLOUR[cnt])
				)
			)
			
			cnt = (cnt + 1) % len(TAG_ICON_COLOUR)
	
	# For each favourite item....
	for item in favs.get(sort=sort_order):
	
		try:
			#Log(item.mediainfo.title)
			
			# If a label has been given, see if the item has the current label. 
			if (label and label not in item.labels):
				continue
				
			# If no label has been given, check that the item also has no label
			if (not label and len(item.labels) > 0):
				continue
				
			mediainfo = item.mediainfo
			navpath = item.path
			
			title = str(mediainfo.title)
			if (item.new_item):
				title =  u"\u00F8" + "  " + title
			else:
				title =  '    ' + title
				if (new_items_only):
					continue
					
			# If the item is a TV show, come up with sensible display name.
			summary = ""
			if (mediainfo.type == 'movies'):
				summary = mediainfo.summary
			else:
				if (item.new_item_check):
					if (item.new_item):
						local = item.date_last_item_check.replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())
						summary += str(L("FavouritesNewItemNotifySummaryNew")) % local.strftime("%Y-%m-%d %H:%M")
					else:
						last_check = item.date_last_item_check.replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())
						next_check = item.next_check_date().replace(tzinfo=tz.tzutc()).astimezone(tz.tzlocal())
						summary += str(L("FavouritesNewItemNotifySummaryNoNew")) % (last_check.strftime("%Y-%m-%d %H:%M"), next_check.strftime("%Y-%m-%d %H:%M"))
			
			oc.add(
				PopupDirectoryObject(
					key=Callback(
						FavouritesNavPathMenu,
						mediainfo=item.mediainfo,
						path=item.path,
						new_item_check=item.new_item_check,
						parent_name=oc.title2
					),
					title= title,
					summary=summary,
					art=mediainfo.background,
					thumb= mediainfo.poster,
					duration=mediainfo.duration,
					
				)
			)

		except Exception, ex:
			Log.Exception("Error whilst dispaying a favourite. MediaInfo was: " + str(item.mediainfo))
		
	return oc

####################################################################################################

def FavouritesActionMenu(parent_name=None, new_items_only=False, label=None):

	oc = ObjectContainer(no_history=True, view_group="InfoList", title1=parent_name, title2="Favourite Actions")

	if new_items_only:
		oc.add(
			DirectoryObject(
				key=Callback(
					FavouritesMenu,
					parent_name=parent_name,
					new_items_only=False,
					replace_parent=True,
					label=label),
				title=L("FavouritesShowAll")
			)
		)
	else:
		oc.add(
			DirectoryObject(
				key=Callback(
					FavouritesMenu,
					parent_name=parent_name,
					new_items_only=True,
					replace_parent=True,
					label=label),
				title=L("FavouritesShowNew")
			)
		)

	if (label):
		oc.add(
			DirectoryObject(
				key=Callback(
					FavouritesLabelRemove,
					parent_name=parent_name,
					new_items_only=True,
					label=label
				),
				title="Remove Label"
			)
		)
	
	oc.add(
		DirectoryObject(
			key=Callback(NoOpMenu),
			title=L("NoOpTitle")
		)
	)

	oc.add(
		DirectoryObject(
			key=Callback(FavouritesClearMenu, parent_name=parent_name),
			title=L("FavouritesClearTitle")
		)
	)
		
	return oc

####################################################################################################

def FavouritesClearMenu(parent_name=None):
	
	Data.Remove(FAVOURITE_ITEMS_KEY)
	
	oc = FavouritesMenu(parent_name=parent_name)
	oc.replace_parent = True
		
	return oc

####################################################################################################

def FavouritesNavPathMenu(mediainfo=None, path=None, new_item_check=None, parent_name=None):

	oc = ObjectContainer(title1=parent_name, title2="Favourites")
	
	# Grab a copy of the path we can update as we're iterating through it.
	cur_path = list(path)
	
	# The path as stored in the system is top down. However, we're going to
	# display it in reverse order (bottom up), so match that.
	cur_path.reverse()
		
	for item in reversed(path):
	
		# When the users select this option, the selected option will automatically
		# be re-added to the path by the called menu function. So, remove it now so
		# we don't get duplicates.
		if (len(cur_path) > 0):
			cur_path.pop(0)
			
	
		# The order in which we're processing the path (bottom up) isn't the 
		# same as how it was navigated (top down). So, reverse it to
		# put in the right order to pass on to the normal navigation functions.
		ordered_path = list(cur_path)
		ordered_path.reverse()
	
		# Depending on the types of args present, we may end up calling different methods.
		#
		# If we have an item URL, take user to provider list for that URL
		if ("url" in item):
			callback = Callback(
				SourcesMenu, mediainfo=mediainfo, url=item['url'], item_name=None, path=ordered_path, parent_name=oc.title2)
			
		# If we have a show URL, take user to season listing for that show
		elif ("show_url" in item):
			callback = Callback(TVShowMenu, mediainfo=mediainfo, url=item['show_url'], item_name=mediainfo.show_name, path=ordered_path, parent_name=oc.title2)
		
		# If we have a season URL, take user to episode listing for that season.
		elif ("season_url" in item):
			callback = Callback(TVSeasonMenu, mediainfo=mediainfo, season_url=item['season_url'], item_name="Season " + str(mediainfo.season), path=ordered_path, parent_name=oc.title2)
		
		oc.add(
			DirectoryObject(
				key=callback,
				title=item['elem']
			)
		)
		
	oc.add(
		DirectoryObject(
			key=Callback(NoOpMenu),
			title=L("NoOpTitle")
		)
	)
	
	oc.add(
		DirectoryObject(
			key=Callback(FavouritesLabelsItemMenu, parent_name=oc.title2, mediainfo=mediainfo),
			title="Labels...",
		)
	)
	
	oc.add(
		DirectoryObject(
			key=Callback(FavouritesRemoveItemMenu, mediainfo=mediainfo),
			title=L("FavouritesRemove"),
		)
	)
	
	if (mediainfo.type == 'tv'):
		title = L("FavouritesNewItemNotifyTurnOn")
		if (new_item_check):
			title = L("FavouritesNewItemNotifyTurnOff")
			
		oc.add(
			DirectoryObject(
				key=Callback(FavouritesNotifyMenu, mediainfo=mediainfo),
				title=title
			)
		)
	
	
	return oc
	
####################################################################################################

def FavouritesLabelRemove(parent_name=None, new_items_only=False, label=None):

	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	try:
		favs = load_favourite_items()
		favs.del_label(label)
		save_favourite_items(favs)
	except Exception, ex:
		Log.Exception("Error deleting label")
		pass		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)

	msg = "Label %s has been removed." % label
	
	return MessageContainer("Label Removed", msg)

####################################################################################################

def FavouritesLabelsItemMenu(mediainfo, parent_name, replace_parent=False):

	# Load up Favourites.
	favs = load_favourite_items() 
		
	oc = ObjectContainer(no_cache=True, replace_parent=replace_parent, title1=parent_name, title2="Labels for " + str(mediainfo.title))
	
	oc.add(
		InputDirectoryObject(
			key=Callback(FavouritesLabelAddMenu, mediainfo=mediainfo, parent_name=parent_name),
			title="Add New Label...",
			prompt="Enter new label name"
		)
	)
	
	fav = favs.get(mediainfo)[0]
	
	for label in favs.get_labels():
				
		# Check if the passed in favourite already has this label.
		prefix = "    " if (not label in fav.labels) else u"\u00F8  "
			
		oc.add(
			DirectoryObject(
				key=Callback(FavouritesLabelToggle, label=label, mediainfo=mediainfo, parent_name=parent_name),
				title= prefix + label
			)
		)
		
	return oc

####################################################################################################
	
def FavouritesLabelAddMenu(query, mediainfo, parent_name):

	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	try:
		favs = load_favourite_items()
		favs.add_label(query)
		fav = favs.get(mediainfo)[0]
		
		#Log("Adding label to: " + str(fav))
		#Log("Current labels: " + str(fav.labels))

		if (query not in fav.labels):
			#Log("Adding label" + query)
			fav.labels.append(query)
			
		save_favourite_items(favs)
	except Exception, ex:
		Log.Exception("Error adding label")
		pass		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)

	return FavouritesLabelsItemMenu(mediainfo, parent_name, True)

####################################################################################################
	
def FavouritesLabelToggle(label, mediainfo, parent_name):
	
	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	
	try:
	
		# Load up Favourites.
		favs = load_favourite_items() 
		fav = favs.get(mediainfo)[0]
	
		if (label not in fav.labels):
			fav.labels.append(label)
		else:
			fav.labels.remove(label)
			
		save_favourite_items(favs)
		
	except Exception, ex:
		Log.Exception("Error toggling label")
		pass		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
		
	return FavouritesLabelsItemMenu(mediainfo, parent_name, True)
	
####################################################################################################

def FavouritesRemoveItemMenu(mediainfo):

	# Keep it simple. Remove item from favourites.
	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	try:
		favs = load_favourite_items()
		favs.remove(mediainfo)
		save_favourite_items(favs)
	except Exception, ex:
		Log.Exception("Error removing favourite ")
		pass		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)

	
	oc = FavouritesMenu()
	oc.replace_parent = True
	return oc

####################################################################################################

def FavouritesNotifyMenu(mediainfo=None):

	oc = ObjectContainer(title1="", title2="")
	oc.header = "New Item Notification"
	
	cron_op = None
	
	Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
	
	try:
		# Load up favourites and get reference to stored favourite rather than
		# dissociated favourite that's been passed in.
		favs = load_favourite_items()
		fav = favs.get(mediainfo=mediainfo)[0]
		
		# Are we turning it on or off?
		if (fav.new_item_check):
		
			
			# Turning it off.
			fav.new_item_check = False
			fav.new_item = None
			fav.items = None
			fav.date_last_item_check = None
			oc.message = "Plugin will no longer check for new items."
			
			# If no other favourites are getting checked, remove cron.
			if (
				Prefs['favourite_notify_email'] and
				len([x for x in favs.get() if x.new_item_check]) == 0
			):
				cron_op = 'del'
		
		else:
		
			# Turning it on.
			fav.new_item_check = True
			fav.new_item = False
			
			# Get page URL
			url = [v for k,v in fav.path[-1].items() if (k == 'show_url' or k == 'season_url')][0]
			
			# Get URLs of all the shows for the current favourite.
			fav.items = [show['ep_url'] for show in Parsing.GetTVSeasonEps(url)]
			
			fav.date_last_item_check = datetime.utcnow()
			fav.date_last_item_found = fav.date_last_item_check
			
			oc.message = "Plugin will check for new items and notify you when one is available.\nNote that this may slow down the plugin at startup."
			
			# If we're the first favourite and user has chosen email notifications,
			# add cron / scheduled task.
			if (
				Prefs['favourite_notify_email'] and
				len([x for x in favs.get() if x.new_item_check]) == 1
			):
				cron_op = 'add'
			
		save_favourite_items(favs)
		
	finally:
		Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
		
	# Do this here to 
	# a) minimise risk of someting going wrong in favs manipulation and
	# b) minimise lock length.
	if (cron_op == 'add'):
		Utils.add_favourites_cron(Platform.OS, NAME, VIDEO_PREFIX)
	elif (cron_op == 'del'):
		Utils.del_favourites_cron(Platform.OS, NAME, VIDEO_PREFIX)
		
	return oc
	
	
def NoOpMenu():

	return ""

####################################################################################################
# FAVOURITE UTILS
####################################################################################################

@route(VIDEO_PREFIX + '/favourites/check')
def StartFavouritesCheck():

	# Only launch a singe instance of this.
	#
	# This is important as when this get called via cron it's possible that the plugin
	# will need to be started. If that happens then a call to this will be launched on a 
	# a separate thread from the plugin's start method. This will then get processed at the
	# same time as the cron's call on the main thread leading to potentially doubled up emails.
	lock = Thread.Lock("FAVS_CHECK" + VIDEO_PREFIX)
	
	if (lock.acquire(False)):
		try:
			Log("Checking for favorites.")
			CheckForNewItemsInFavourites()
		finally:
			lock.release()
	else:
		Log("Not checking for favourites as someone else already is.")
	
	Log("Done")
	return ""


####################################################################################################

def CheckForNewItemsInFavourites():

	favs = load_favourite_items().get()
		
	for fav in favs:
		try:
			CheckForNewItemsInFavourite(fav)
		except Exception, ex:
			# If a favourite fails to process, still try to process any other.
			Log.Exception("Error whilst checking favourite for new items.")
			pass
		

####################################################################################################

def CheckForNewItemsInFavourite(favourite, force=False):
	
	#Log("Processing favourite: " + str(favourite.mediainfo))
	#Log("Favourite Last Checktime: " + str(favourite.date_last_item_check))
	
	# Do we want to check this favourite for updates?
	# If so, only bother if it's not already marked as having updates.
	# and hasn't been checked in the last 12 hours.
	if (favourite.ready_for_check(force)):
	
		#Log("Checking for new item in favourite")
		
		# Get page URL
		url = [v for k,v in favourite.path[-1].items() if (k == 'show_url' or k == 'season_url')][0]
	
		# Get up-to-date list of shows available for the current favourite.
		items = [show['ep_url'] for show in Parsing.GetTVSeasonEps(url,no_cache=True)]
		has_new_items = False
		
		Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
		try:
			favs_disk = load_favourite_items()
			has_new_items = favs_disk.check_for_new_items(favourite.mediainfo, items)
			save_favourite_items(favs_disk)
		except Exception, ex:
			Log.Exception("Error saving favourites after new item check.")
			pass
		finally:
			Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
		
		# If user has requested email to be sent, do it now, but only if check wasn't
		# forced (i.e: happened as part of regular checks rather than a force recalculation
		# of whether any new eps are still available because the user has watched one).
		try:
			if (has_new_items and Prefs['favourite_notify_email'] and not force):
				Log('Notifying about new item for title: ' + str(favourite.mediainfo.title))
				Notifier.notify(
					Prefs['favourite_notify_email'],
					str(NAME),
					favourite.mediainfo.title,
					favourite.mediainfo.poster
				)
		except Exception, ex:
			Log.Exception("ERROR Whilst sending email notification about " + str(favourite.mediainfo.title))
			pass
			
			
####################################################################################################
# Params:
#   mediainfo: A MediaInfo item for the current item being viewed (either a movie or single episode).
#   item:  A dictionary containing information for the selected source for the item being viewed.
def GetItemForSource(mediainfo, source_item, parent_name, part_index=None):
	
	media_item = Parsing.GetItemForSource(mediainfo, source_item, part_index)
	
	if media_item is not None:
	
		if (isinstance(media_item, MultiplePartObject)):
		
			title = media_item.title + " (Multi-part"
			if (isinstance(media_item, CaptchaBase)):
				title = title + ", Captcha"
			title = title + ")"
			
			return {
				'item':
					PopupDirectoryObject(
						key = Callback(SourcesPartMenu, mediainfo=mediainfo, source_item=source_item, part_count=media_item.part_count, parent_name=parent_name),
						title = title,
						summary= mediainfo.summary,
						art=mediainfo.background,
						thumb= mediainfo.poster,
					),
			}
	
		elif (isinstance(media_item, CaptchaBase)):
		
			return {
				'item':
					DirectoryObject(
						key = Callback(CaptchaRequiredMenu, mediainfo=mediainfo, source_item=source_item, url=media_item.url, parent_name=parent_name),
						title = media_item.title + " (Captcha)",
						summary= mediainfo.summary,
						art=mediainfo.background,
						thumb= mediainfo.poster,
					),
				'url': media_item.url
			}
		else:
			return { 'item': media_item, 'url': media_item.url }
		
	# The only way we can get down here is if the provider wasn't supported or
	# the provider was supported but not visible. Maybe user still wants to see them?
	elif (Prefs['show_unsupported']):
	
		return {
			'item': 
				DirectoryObject(
					key = Callback(PlayVideoNotSupported, mediainfo = mediainfo),
					title = source_item['name'] + " - " + source_item['provider_name'] + " (Not playable)",
					summary= mediainfo.summary,
					art=mediainfo.background,
					thumb= mediainfo.poster,
				)
		}
		
	else:
		return {}

	
####################################################################################################
	
def PlayVideoNotSupported(mediainfo):

	return ObjectContainer(
		header='Provider is either not currently supported or has been disabled in preferences...',
		message='',
	)


####################################################################################################
#
@route(VIDEO_PREFIX + '/sources/isCompatible')
def GetAdditionalSourcesIsCompatible():

	""" 
	Quick and dirty method external plugins can call to see if we're present or not on a user's
	machine.
	
	If we're not deployed / present on the user's machine, then a 404 will be returned by the
	PMS and the external plugin will know not to use us. If we are present, this will return
	a 200 with no data, letting the external plugin know it can call us to get additional sources
	for an item.
	"""
	return True


####################################################################################################
#
@route(VIDEO_PREFIX + '/sources/{imdb_id}/{title}')
@route(VIDEO_PREFIX + '/sources/{imdb_id}/{title}/{year}')
@route(VIDEO_PREFIX + '/sources/{imdb_id}/{title}/{season_num}/{ep_num}')
def GetAdditionalSources(imdb_id, title, year=None, season_num=None, ep_num=None):

	"""
	Publicly accessible way to retrieve a list of sources from the site we support
	for the passed in title. As we may not be deployed on a user's machine, it's recommended
	that whoevever is thinking of calling this, should first call 
	GetAdditionalSourcesIsCompatible() above.
	"""
	
	caller = None

	# Keep track of who requested we generate these additional sources. This will be used
	# to let the original plugin know when the user decides to play one of our sources.
	if ('Referer' in Request.Headers):
	
		match = re.search("/video/([^/]+)/", Request.Headers['Referer'])
		caller = match.group(1) if match else None
	
	# Work out what type of search to carry out.
	type = 'tv' if season_num else 'movies'
	
	# Search for the passed in information using the site specific parser linked to this.
	search_results = Parsing.GetSearchResults(query=title, type=type, imdb_id=imdb_id)
	
	# Did we get any results?
	if (len(search_results) > 0):
	
		# Sort results based on how close they are to the passed in title.
		search_results = sorted(
			search_results,
			key=lambda x: String.LevenshteinDistance(x.title.lower(), title.lower())
		)
		
		# If the closest title is pretty close to the passed in title, assume it's a match
		# and generate our source menu for it and return that to the caller.
		if (String.LevenshteinDistance(search_results[0].title.lower(), title.lower()) < 3):
	
			if (type == 'movies'):
				# FIXME: Need to check imdb_id.
				oc =  SourcesMenu(search_results[0], search_results[0].id, external_caller=caller)
				oc.title1 = oc.title2
				oc.title2 = "Additional Sources (" + NAME + ")"
				return oc
				
			else:
			
				# Get a listing of seasons for this show.
				seasons = Parsing.GetTVSeasons(search_results[0].id)
				season = [season for season in seasons if 'season_number' in season and season['season_number'] == int(season_num)]
				
				if (len(season) == 1):
				
					# Get a listing of episodes for this shows's season.
					eps = Parsing.GetTVSeasonEps(season[0]['season_url'])
					ep = [ep for ep in eps if 'ep_num' in ep and ep['ep_num'] == int(ep_num)]
					
					if (len(ep) == 1):
					
						mediainfo = Parsing.GetMediaInfo(
							search_results[0].id,
							MediaInfo(
								type='tv',
								show_name=title,
								season=season_num,
								ep_num=ep_num
							),
							need_meta_retrieve(type)
						)
						
						oc =  SourcesMenu(mediainfo, ep[0]['ep_url'], external_caller=caller)
						oc.title1 = oc.title2
						oc.title2 = "Additional Sources (" + NAME + ")"
						return oc


	# No matches or close enough match if we get here....
	return ObjectContainer(header="No Additional Sources Found", message="Couldn't match item name at other providers")
	

####################################################################################################
#
@route(VIDEO_PREFIX + '/mediainfo/{url}')
def MediaInfoLookup(url):

	"""
	Returns the media info stored in the recently browsed item list
	for the given provider URL or None if the item isn't found in the
	recently browsed item list.
	"""
	
	# Get clean copy of URL user has played.
	decoded_url = String.Decode(str(url))
	#Log(decoded_url)
	
	# See if the URL being played is on our recently browsed list.
	item = cerealizer.loads(Data.Load(BROWSED_ITEMS_KEY)).getByURL(decoded_url)

	if (item is None):
		Log("****** ERROR: Watching Item which hasn't been browsed to (" + decoded_url + ")")
		return ""
	
	# Return the media info that was stored in the recently browsed item.
	return demjson.encode(item[0])


####################################################################################################
# LMWT Plugin specific helper methods.

@route(VIDEO_PREFIX + '/playback/{url}')
def PlaybackStarted(url):

	"""
	Method that gets called by our URL Services to let us know playback has started
	"""
	
	# Many bad things can happen here...
	try:

		# Get clean copy of URL user has played.
		decoded_url = String.Decode(str(url))
		#Log(decoded_url)

		# Get our recently browsed items and try to find the item the user has just played.	
		browsed_items =  cerealizer.loads(Data.Load(BROWSED_ITEMS_KEY))
		item = browsed_items.getByURL(decoded_url)
		
		if (item is None):
			Log("****** ERROR: Watching Item which hasn't been browsed to (" + decoded_url + ")")
			return ""
		
		# We may just be an additional source and we're playing this on behalf of another
		# plugin. In that case, let that plugin know playback has started.
		caller = browsed_items.getCaller(decoded_url)
		
		if (not caller):
		
			# We've started playback for ourselves. Do normal processing.
			#
			# Nothing to do. User doesn't want any tracking.
			if (Prefs['watched_indicator'] == 'Disabled' and Prefs['watched_amount'] == 'Disabled'):
				return ""
				
			# Process and mark as watched.
			PlaybackMarkWatched(item[0], item[1])

		else:
		
			# We've started playback on behald of someone else. Call their playbackStarted
			# method.
			
			mediainfo = item[0]
				
			# Use the information from the mediainfo to call the PlaybackStarted method of
			# whatever plugin requested this.
			url = PLEX_URL + '/video/%s/playback/external/%s' % (caller, mediainfo['id'])
			if (mediainfo['ep_num']):
				url += "/%s/%s" % (str(mediainfo['season']), str(mediainfo['ep_num']))
			
			request = urllib2.Request(url)
			response = urllib2.urlopen(request)
		
	except Exception, ex:
		Log.Exception("Error whilst trying to mark item as played")
		pass
		
	return ""
		
####################################################################################################

@route(VIDEO_PREFIX + '/playback/external/{id}')
@route(VIDEO_PREFIX + '/playback/external/{id}/{season_num}/{ep_num}')
def PlaybackStartedExternal(id, season_num=None, ep_num=None):

	"""
	Handle the fact that playback of a source has been started by an Additonal Sources
	plugin.
	"""
	
	season_num = int(season_num) if season_num else None
	ep_num = int(ep_num) if ep_num else None
	
	# Nothing to do. User doesn't want any tracking.
	if (Prefs['watched_indicator'] == 'Disabled' and Prefs['watched_amount'] == 'Disabled'):
		return ""
	
	# Get list of items user has recently looked at.
	browsedItems =  cerealizer.loads(Data.Load(BROWSED_ITEMS_KEY))
	
	# See if the URL being played is on our recently browsed list.
	info = browsedItems.getByID(id, season_num, ep_num)
	
	if (info is None):
		Log("****** ERROR: Watching Item which hasn't been browsed to")
		return ""
	
	# Process and mark as watched.
	PlaybackMarkWatched(item[0], item[2])

####################################################################################################

def PlaybackMarkWatched(mediainfo, path):
	
	# Does user want to keep track of watched items?
	if (Prefs['watched_indicator'] != 'Disabled'):
		# Load up viewing history, and add item to it.
		hist = load_watched_items()
		hist.mark_watched(path)
		save_watched_items(hist)
	
	# Does user also want to keep track of Recently Watched Items?
	if (Prefs['watched_amount'] != 'Disabled' and Data.Exists(BROWSED_ITEMS_KEY)):
						
		# Load up viewing history, and add item to it.
		hist = load_watched_items()
		hist.add_recent(mediainfo, path, Prefs['watched_grouping'], int(Prefs['watched_amount']))
		save_watched_items(hist)
	
	# Favourites keep their own list of what shows they consider to have been watched to make
	# sure their new unwatched show functionality works as expected.
	if (mediainfo.type == 'tv'):
	
		Thread.AcquireLock(FAVOURITE_ITEMS_KEY)
		watched_favs = []
		try:
			favs = load_favourite_items()
			watched_favs = favs.watch(mediainfo, path[-1]['url'])
			save_favourite_items(favs)
		except Exception, ex:
			Log.Exception("Erorr marking item as watched for favourite.")
			pass
		finally:
			Thread.ReleaseLock(FAVOURITE_ITEMS_KEY)
			
		# Even though this specific item has now been played, we can't just set the favourites
		# new_item to false as there might have been multiple new items. So, check if this
		# favourite still has new items or not.
		for fav in watched_favs:
			#Log(str(fav))
			Thread.Create(CheckForNewItemsInFavourite, favourite=fav, force=True)

	#Log("Playback started on item:" + str(mediainfo))
	#Log("Viewing history: " + str(hist))
	
	return ""

####################################################################################################

def VersionTrack():

	if (Prefs['versiontracking']):
		try:
			# Has there been a 3 hour idle window since we were last called?
			# If so, assume this is a new user session and count it towards stats.
			request = urllib2.Request(VERSION_URLS[VERSION])
			request.add_header('User-agent', '-')	
			response = urllib2.urlopen(request)
		except:
			pass

####################################################################################################
def CheckAdditionalSources(sources):

	"""
	Check which of the additional sources this plugin knows about are
	actually available on this machine.
	"""

	Dict[ADDITIONAL_SOURCES_KEY] = []
	
	for source in sources:
		try:
			# Create the dummy URL that services register themselves under.
			pluginURL = "http://providerinfo.%s/" % source
			
			# Query plex to see if there is a service to handle the URL.
			if (
				URLService.ServiceIdentifierForURL(pluginURL) is not None and
				'sources=true' in URLService.NormalizeURL(pluginURL)
			):
				Dict[ADDITIONAL_SOURCES_KEY].append(source)
		except Exception, ex:
			Log.Exception("Error working out what additional sources are available.")
			pass


####################################################################################################
#
@route(KEEP_ALIVE_PATH)
def KeepAlive():

	# A simple method which can be called to make sure the plugin stays within Plex's inactivity 
	# timeout period and doesn't get killed. Especially useful for long running threads....
	Log(KEEP_ALIVE_PATH)
	
	return "ALIVE"

####################################################################################################
	
@route(VIDEO_PREFIX + "/prebuffer/addPathToLib/{path}")
def BufferAddPathToLib(path):

	return Buffer.addPathToLib(String.Decode(path))
	
####################################################################################################

@route(VIDEO_PREFIX + "/prebuffer/delPathFromLib/{path}")
def BufferDelPathFromLib(path):

	return Buffer.delPathFromLib(String.Decode(path))	


###############################################################################
# UTIL METHODS
###############################################################################

def DictDefault(key, default):

	if not key in Dict:
		Dict[key] = default
		
	return Dict[key]
	
###############################################################################
# 
def need_watched_indicator(type):

	if (type == 'tv' and Prefs['watched_indicator'] != 'Disabled'):
		return True
		
	if (type == 'movies' and Prefs['watched_indicator'] == 'All'):
		return True
	
	return False

###############################################################################
# 	
def need_meta_retrieve(type):

	"""
	Returns a bool indicating whether the user has set preferences to
	query a 3rd party metadata provider for the given media info type.
	"""
	if (Prefs['meta_retrieve'] == 'Disabled'):
		return False
	elif (Prefs['meta_retrieve'] == 'All'):
		return True
	elif (type == 'tv' and Prefs['meta_retrieve'] == 'TV Shows'):
		return True
	elif (type == 'movies' and Prefs['meta_retrieve'] == 'Movies'):
		return True
	else:
		return False
		

###############################################################################
#
def load_watched_items():

	if (Data.Exists(WATCHED_ITEMS_KEY)):
		hist = cerealizer.loads(Data.Load(WATCHED_ITEMS_KEY))
	else:
		hist = ViewedItems()
		
	return hist

###############################################################################
#	
def save_watched_items(hist):

	Data.Save(WATCHED_ITEMS_KEY, cerealizer.dumps(hist))
	
###############################################################################
#
def load_favourite_items():

	if (Data.Exists(FAVOURITE_ITEMS_KEY)):
		favs = cerealizer.loads(Data.Load(FAVOURITE_ITEMS_KEY))
	else:
		favs = FavouriteItems()
		
	return favs

###############################################################################
#
def save_favourite_items(favs):
	
	Data.Save(FAVOURITE_ITEMS_KEY, cerealizer.dumps(favs))
	
	
def DoCaptcha(url):

	return Parsing.DoCaptcha(url)