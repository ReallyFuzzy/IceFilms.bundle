import re
import urllib
import copy
import sys

from datetime import datetime

from BeautifulSoup import BeautifulSoup
from xgoogle.search import GoogleSearch

import Utils

from NavExObject import CaptchaRequiredObject, MultiplePartObject, MultiplePartCaptchaObject
from MetaProviders import DBProvider, MediaInfo

ICEFILMS_URL = "http://www.icefilms.info"
ICEFILMS_VIDEO_URL = ICEFILMS_URL + "/ip.php?v=%s"
ICEFILMS_SOURCES_URL = ICEFILMS_URL + "/membersonly/components/com_iceplayer/video.php?h=374&w=631&vid=%s"
ICEFILMS_AJAX = ICEFILMS_URL+'membersonly/components/com_iceplayer/video.phpAjaxResp.php'
ICEFILMS_REFERRER = ICEFILMS_URL

####################################################################################################
# ICEFILMS PAGE PARSING
####################################################################################################

####################################################################################################

def GetItems(type, genre = None, sort = None, alpha = None, pages = 5, start_page = 0):

	items = []
	url = ICEFILMS_URL + "/" + type
	
	if (genre):
		genre = genre.lower()
		
	if (alpha):
		sort = "a-z"
		genre = "1" if alpha == "123" else alpha.upper()
		
	if (sort is not None):
		url = url + "/" + sort
		
	if (genre is not None):
		url = url + "/" + genre
	else:
		url = url + "/1"
	
	soup = BeautifulSoup(HTTP.Request(url).content)
	
	# RegEx to extract out item id.
	id_reg_ex = re.compile("/ip.php\?v=(\d+)&?")
	
	for item in soup.findAll("a", { 'name': 'i' }):
	
		res = MediaInfo()
			
		res.type = type

		title_elem = item.nextSibling.nextSibling
		
		# Pick out next element 
		# Extract out title
		res.title = Utils.decode_htmlentities(str(title_elem.string))
		
		match = re.search("(.*)\((\d*)\)", res.title)
		
		if (match):
			res.title = match.group(1).strip()
			res.year = int(match.group(2).strip())
		
		# Extract out id if available, otherwise, just store the item's URL.
		match = id_reg_ex.search(title_elem['href'])
		#Log(match)
		if (match):
			res.id = match.group(0)
		else:
			res.id = title_elem['href']
		#Log(res.id)
		
		# Add to item list.
		#Log("Adding item: " + str(res))
		items.append(res)
	
	return items

####################################################################################################

def GetTVSeasons(url):

	seasons = []
	
	soup = BeautifulSoup(HTTP.Request(ICEFILMS_URL + url).content)

	for item in soup.find("span", { 'class' : 'list' }).findAll('h3'):
		
		season = {}
		season['season_name'] = str(item.find(text=True))
		season['season_url'] = url + "#" + season['season_name']
		
		match = re.search("(\d+)", season['season_name'])
		
		if match:
			season['season_number'] = int(match.group(1))
		
		seasons.append(season)
	
	return seasons

####################################################################################################

def GetTVSeasonEps(url, no_cache=False):

	cacheTime = 0 if no_cache else HTTP.CacheTime
	
	eps = []
	soup = BeautifulSoup(HTTP.Request(ICEFILMS_URL + url, cacheTime=cacheTime).content)
	
	# Extract out the season name from the URL if present.
	seasonName = None
	match = re.search("\#(.*)", url)
	if (match):
		seasonName = match.group(1)
	
	for item in soup.find("span", { 'class' : 'list' }).findAll('h3'):
	
		if (not seasonName or item.find(text=True) ==  seasonName):
		
			tag = item.findNextSibling()
			
			while (tag is not None and tag.name != 'h3'):
				
				if (tag.name == 'a'):
					ep = {}
					ep['ep_name'] = Utils.decode_htmlentities(str(tag.string))
					ep['ep_url'] = tag['href']
					
					match = re.search("(\d+)x(\d+)", ep['ep_name'])
					if match:
						ep['season_num'] = int(match.group(1))
						ep['ep_num'] = int(match.group(2))
					
					
					eps.append(ep)

				tag = tag.findNextSibling()
	
	return eps

####################################################################################################

def GetSources(url):

	"""
	Return a list of dictionary containing info for each provider / source for the given
	video URL.
	"""

	sources = []
	
	id_reg_ex = re.compile("/ip.php\?v=(\d+)")
	id = match = id_reg_ex.search(url).group(1)
	
	# Load up sources.
	soup = BeautifulSoup(HTTP.Request(ICEFILMS_SOURCES_URL % id, cacheTime=300).content)
	
	for qualityElem in soup.findAll('div','ripdiv'):
	
		quality = str(qualityElem.b.string);
		
		for providerElem in qualityElem.findAll('p'):
		
			if (providerElem.i is None): continue
			
			num = providerElem.i["id"]
			
			# Extract out provider name from source. 
			if (providerElem.span):
				provider = providerElem.span["title"][len("Hosted By "):]
			else:
				provider = providerElem.img["title"][len("Hosted By "):]
							
			source = {}
			source['name'] = "Source " + num
			source['provider_name'] = provider
			source['id'] = id
			source['quality'] = quality
			source['parts'] = []
		
			for partElem in providerElem.findAll('a'):
				partName = "Part 1"
				if (partElem.string):
					partName = str(partElem.string)
					
				source['parts'].append(
					{'part_name': partName, 'id':partElem['onclick'][3:-1]}
				)
				
			sources.append(source)

	return sources


####################################################################################################

def GetItemForSource(mediainfo, source_item, part_index):
	"""
	For a given provider source for an item, return the appropriate VideoClipObject.
		
	Params:
	  mediainfo:
	    A MediaInfo item for the current item being viewed (either a movie or single episode).
	  item:
	    A dictionary containing information for the selected source for the item being viewed.
	    This will be the dictionary that was generated in GetSources().
	"""

	# See is the provider is one directly supported by this plugin.
	#
	# This is a hack that depends on the URL Services included as part of this plugin
	# adhering to the special providerinfo.provider_name URL that we generate. If the URL Service
	# registers itself as supporting this URL Structure, then we assume it it will support
	# the given provider.
	#
	# The idea beind this crazy scheme is to allow the URL Service to be used as a normal 
	# URL Service (i.e: give it a normal URL it supports and it does the right thing), as well
	# as supporting a few additional options for this plugin (such as enabling / disabling 
	# themselves, callbacks to let the plugin know that playback of an item has started....)
	providerInfoURL = "providerinfo://" + source_item['provider_name'].lower() + "/?plugin=icefilms"
	providerSupported = URLService.ServiceIdentifierForURL(providerInfoURL) is not None
	
	if (providerSupported):
	
		# See if we need to hide provider by asking the URL service to normalise it's special
		# providerinfo URL. This should return a URL where the query string is made up of
		# all the options that URL Service supports in this plugin's little world. 
		normalisedProviderInfoURL = URLService.NormalizeURL(providerInfoURL)
		providerVisible =  'visible=true' in normalisedProviderInfoURL
		captcha = 'captcha=true' in normalisedProviderInfoURL

		if (providerVisible):
		
			if (len(source_item['parts']) > 1 and part_index is None):
			
				if (captcha):
					return MultiplePartCaptchaObject(
						part_count=len(source_item['parts']),
						title=source_item['name'] + " - " + source_item['provider_name'] + " - " + source_item['quality'],
					)
				else:
					return MultiplePartObject(
						part_count=len(source_item['parts']),
						title=source_item['name'] + " - " + source_item['provider_name'] + " - " + source_item['quality'],
					)
					
			elif (captcha):
				
				if (part_index is None):
					part_index = 0
				
				return CaptchaRequiredObject(
					url="captcha://icefilms.info/" + source_item['id'] + "/" + source_item['parts'][part_index]['id'],
					title=source_item['name'] + " - " + source_item['provider_name'] + " - " + source_item['quality'],
				)
				
			else:
			
				if (part_index is None):
					part_index = 0
				
			
				# Note the special URL we return here. This a made up URL which doesn't exist in the
				# real world, but which will be caught by a URL Service included with this plugin,
				# which will return a MediaObject with an indrect callback as it's key.
				#
				# This allows us to delay looking up the provider's URL until the user actually 
				# selects the video and prevents us from hammering IceFilms every time an item's
				# source are shown.

				return VideoClipObject(
					url="external://icefilms.info/" + source_item['id'] + "/" + source_item['parts'][part_index]['id'],
					title=source_item['name'] + " - " + source_item['provider_name'] + " - " + source_item['quality'],
					summary=mediainfo.summary,
					art=mediainfo.background,
					thumb= mediainfo.poster,
					rating = float(mediainfo.rating) if mediainfo.rating else None,
					duration=mediainfo.duration,
					source_title = source_item['provider_name'] ,
					year=mediainfo.year,
					originally_available_at=mediainfo.releasedate,
					genres=mediainfo.genres
				)
			
	return None
	

	
####################################################################################################

def GetSearchResults(query=None,type=None,imdb_id=None, exact=False):
	
	if (type=="movies"):
		# This a google search. The -tv will ommit all TV shows.
		search = 'intitle:"%s" -"Episode List" -"Series Rating"' % (query)
	else:
		search = '"Episode List" intitle:"%s"' % (query)
	
	gs = GoogleSearch(search)
	gs.results_per_page = 10
	gs.page = 0
	results = gs.get_results()
	items = []
	
	for res in results:
	
		name = re.sub(
			'(<em>|</em>|<a>|</a>|DivX|-|icefilms(\.info)?|<b>\.\.\.</b>|Episode List|links)',
			'',
			res.title.encode('utf8')
		).strip()

		url=res.url
		video_url = re.search("icefilms\.info(/.*)", url).group(1)
		
		res = MediaInfo()
		
		res.type = type
		res.title = name

		match = re.search("(.*)\((\d*)\)", res.title)
		
		if (match):
			res.title = unicode(match.group(1).strip(), 'UTF-8')
			res.year = int(match.group(2).strip())
			
		res.id = video_url
		
		items.append(res)
	
	return items

####################################################################################################

def GetMediaInfo(url, mediainfo, query_external=False):

	"""
	Retrieve meta data about the passed in IceFilms item from a meta provider.
	Additionally, for any info not returned by the meta provider, try to
	collect the info directly from the IceFilms item page.
	"""
	
	try:
		
		if (mediainfo.id and re.match("tt\d+", mediainfo.id)):
			imdb_id = mediainfo.id
		else:
			soup = BeautifulSoup(HTTP.Request(ICEFILMS_URL + url).content)
			imdb_link = soup.find('a','iframe')['href']
			imdb_id = re.search("(tt\d+)", str(imdb_link)).group()
		
		if (query_external):
		
			# Construct kwargs.
			kwargs = {}
			kwargs['imdb_id'] = imdb_id
			kwargs['season'] = mediainfo.season
			if hasattr(mediainfo, 'show_name'):
				kwargs['show_name'] = mediainfo.show_name
			if hasattr(mediainfo, 'ep_num'):
				kwargs['ep_num'] = mediainfo.ep_num
			
			#Log("Query-ing External Provider. Args:" + str(kwargs))
			mediainfo = DBProvider().GetProvider(mediainfo.type).RetrieveItemFromProvider(**kwargs)
			#Log(str(mediainfo))
		else:
			mediainfo.id = imdb_id
		
		return mediainfo

	except Exception, ex:
		Log.Exception("Error whilst retrieveing media info")
		return None

	