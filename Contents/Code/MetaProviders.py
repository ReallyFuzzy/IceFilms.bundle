import random
import time

from datetime import datetime
from urllib import quote_plus

from tvdb_api.tvdb_exceptions import tvdb_shownotfound, tvdb_attributenotfound
from tvdb_api.tvdb_api import Tvdb

MOVIEDB_URL = "http://api.themoviedb.org/2.1/Movie.imdbLookup/en/xml/e3dde0b795a9eca51531ce9f8e688ff6/"

class DBProvider(object):

	def __init__(self):
		pass

	def GetProvider(self, type=None):
		if (type=="movies"):
			return MovieDBProvider()
		elif (type=="tv"):
			return TVDBProvider()
		else:
			return None

###############################################################################
# Helper class to retrieve info from TheMovieDB.
class MovieDBProvider(object):

	def RetrieveItemFromProvider(self, **kwargs):
	
		#try:
		
			#Log("Fetching info for: " + imdb_id)
			imdb_id = kwargs['imdb_id']
			
			title = quote_plus(unicode(imdb_id).encode('utf-8'))
			url = MOVIEDB_URL + title

			#Log("Using URL: " + url)
			movie_page = XML.ElementFromURL(url,cacheTime=100000)
			resultsCount = movie_page.xpath("/OpenSearchDescription/opensearch:totalResults/text()",namespaces={"opensearch":"http://a9.com/-/spec/opensearch/1.1/"})[0]
			
			mediaInfo = MediaInfo()
			mediaInfo.type = "movies"
			mediaInfo.title = str(imdb_id)
			
			# Save the date we last tried to retrieve the info for this item.
			# This'll be used to know when to try to re-retrieve the info.
			mediaInfo.dt = datetime.utcnow()
			
			if(resultsCount <> '0') :
			
				mediaInfo.id = str(imdb_id)
			
				xpRes = movie_page.xpath("/OpenSearchDescription/movies/movie")
				if (len(xpRes) > 0):
					movie = xpRes[0]
				else:
					return
					
				xpRes = movie.xpath("./id/text()")
				if (len(xpRes) > 0):
					mediaInfo.tmdb_id = str(xpRes[0])
					
				xpRes = movie.xpath("./name/text()")
				if (len(xpRes) > 0):
					mediaInfo.title = xpRes[0]
					
				mediaInfo.background = self.MovieDBGetImage(movie, "backdrop", ["w1280", "poster", "original"],False)
				mediaInfo.poster = self.MovieDBGetImage(movie, "backdrop", ["w342", "original"],True)
				
				xpRes = movie.xpath("./overview/text()")
				if (len(xpRes) > 0):
					mediaInfo.summary = xpRes[0]
					
				xpRes = movie.xpath("./rating/text()")
				
				if (len(xpRes) > 0):
					mediaInfo.rating = int(float(xpRes[0]))
					
				xpRes = movie.xpath("./runtime/text()")
				
				if (len(xpRes) > 0):
					mediaInfo.duration = int(float(xpRes[0])) * 60 * 1000

						
			#Log("Saving object: " + imdb_id)
			#Log(str(mediaInfo))
			return mediaInfo
			
		#except Exception, ex:
			#Log("Exception")
			#Log(ex)
			
			
	def MovieDBGetImage(self, movie, type, sizes, rand):

		#Log("In get image")
		for size in sizes:
			#Log("Checking for...." + size)
			xpRes = movie.xpath("./images/image[@size='" + size + "' and @type='" + type + "']/@url")
			if (len(xpRes) > 0):
				#Log("Returning...." + xpRes[0])
				index = 0
				if rand:
					index = random.randint(0,len(xpRes) -1)
				return str(xpRes[index])
			
		Log("Image not found for any of the specified sizes.")
		return ""

###############################################################################
# Helper class that should retrieve info from somewhere.
# However, no easily queryable data source have been found, so just letting
# this return an empty mediaInfo object for the time being.
class TVDBProvider(object):

	def RetrieveItemFromProvider(self, **kwargs):
	
		#Log("In TVDBProvider.RetrieveItemFromProvider with args: " + str(kwargs))
		mediaInfo = MediaInfo()
		mediaInfo.type = "tv"
			
		try:
								
			t = Tvdb(banners=True)
			show = None
			
			if ('imdb_id' in kwargs and kwargs['imdb_id']):
				try:
					show = t[kwargs['imdb_id']]
				except tvdb_shownotfound, ex:
					pass
					
			if (not show and 'show_name' in kwargs and kwargs['show_name']):
				try:
					#Log(kwargs['show_name'])
					show = t[kwargs['show_name']]
					if (show['seriesname'].lower() != kwargs['show_name'].lower()):
						show = None
				except tvdb_shownotfound, ex:
					pass
					
			if (not show):
				raisetvdb_shownotfound()
			
			try:
				mediaInfo.id = show['imdb_id']
			except tvdb_attributenotfound, ex:
				pass
				
			mediaInfo.show_name = show['seriesname']
			mediaInfo.duration = int(show['runtime']) * 60 * 1000
			mediaInfo.background = show['fanart']
			mediaInfo.poster = show['poster']
			mediaInfo.summary = show['overview']
						
			if ('season' not in kwargs or kwargs['season'] is None):
			
				seasons = {}
				
				mediaInfo.title = mediaInfo.show_name
				
				for key in show.keys():
					try:
						#Log("Looking for poster for season:" + str(key))
						season_posters = [x for x in show['_banners']['season']['season'].values() if x['season'] == str(key)]
						season_posters = sorted(season_posters, key=lambda x: x['rating'] if 'rating' in x else '0')
						if len(season_posters) > 0:
							seasons[key] = season_posters[-1]['_bannerpath']
					except Exception,ex:
						Log.Exception('Error while getting poster for season: ' + str(key))
					
				#Log("Found Season Poster:" + str(seasons))
				mediaInfo.season_posters = seasons		
					
			else:
			
				# Deal with old mediainfo items were the season name and not number 
				# was stored.
				if isinstance(kwargs['season'], int):
					season = kwargs['season']
				else:
					season = int(re.search("(\d+)", kwargs['season']).group(0))
						
				mediaInfo.show_poster = mediaInfo.poster
				
				#Log("Looking for poster for season:" + str(season))
				try:
					season_posters = [x for x in show['_banners']['season']['season'].values() if x['season'] == str(season)]
					if (len(season_posters) > 0):
						mediaInfo.poster = sorted(season_posters, key=lambda x: x['rating'] if 'rating' in x else '0')[-1]['_bannerpath']
				except Exception, ex:
					Log.Exception("Couldn't find poster for season")
				
				if ('ep_num' not in kwargs or kwargs['ep_num'] is None):
					episodes = {}
					
					# Make sure season we've been passed exists at TVDB.
					if  season in show.keys():
						# Get a list of all the episodes in this season according to TVDB.
						for episode in show[season].values():
							episodes[int(episode['episodenumber'])] = {
								'summary': episode['overview'],
								'title': episode['episodename'],
								'rating': episode['rating'],
								'poster': episode['filename'],
							}
						
						
					mediaInfo.season_episodes = episodes
						
				else:
					episode = show[season][int(kwargs['ep_num'])]
					
					mediaInfo.title = "Episode " + episode['episodenumber'] + " - " + episode['episodename']
					mediaInfo.summary = episode['overview']
					if episode['firstaired']:
						mediaInfo.releasedate = Datetime.ParseDate(episode['firstaired'])
					mediaInfo.rating = float(episode['rating']) if (episode['rating']) else None
					mediaInfo.season = int(episode['seasonnumber'])
					mediaInfo.ep_num = int(episode['episodenumber'])
					mediaInfo.season_poster = mediaInfo.poster
					mediaInfo.poster = episode['filename']

		except Exception, ex:
			#Log.Exception("Error whilst retrieving meta data for TV Show")
			pass

		return mediaInfo
		

###############################################################################
# Meta Data class
class MediaInfo(object):

	def __init__(
		self, id = None, title = None, type = None, year = None, background = None,
		poster = None,  summary = None, rating = None, duration = None, releasedate = None,
		genres = [], dt = None, show_name = None, season = None, ep_num = None
	):
	
		self.id = id
		self.title = title
		self.type = type
		self.year = year
		self.background = background
		self.poster = poster
		self.summary = summary
		self.rating = rating
		self.duration = duration
		self.releasedate = releasedate
		self.genres = genres
		self.dt = dt
		self.show_name = show_name
		self.season = season
		self.ep_num = ep_num

		
	def __str__(self):
	
		str_ret = (
			"{ " +
			"id: " + str(self.id) + ", " +
			"title: " + str(self.title) + ", " +
			"type: " + str(self.type) + ", " +
			"year: " + str(self.year) + ", " +
			"background:" + str(self.background) + ", " +
			"poster: " + str(self.poster) + ", " +
			"summary: " + str(self.summary) + ", " +
			"rating:" + str(self.rating) + ", " +
			"duration:" + str(self.duration) + ", " +
			"genres:" + str(self.genres) + ", " +
			"release date:" + str(self.releasedate) + ", " +
			"show name:" + str(self.show_name) + ", " +
			"season:" + str(self.season) + ", "
		)
		
		if hasattr(self,"ep_num"):
			str_ret += "ep_num:" + str(self.ep_num) + ", "
			
		str_ret += "}"
		
		return str_ret
		
		
	def json_equivalent(self):
	
		return (
			{
				"id": self.id,
				"title": self.title,
				"type": self.type,
				"year": self.year,
				"background": self.background,
				"poster": self.poster,
				"summary": self.summary,
				"rating": self.rating,
				"duration": self.duration,
				"genres": self.genres,
				"release_date": self.releasedate.toordinal() if self.releasedate else None,
				"show_name": self.show_name,
				"season": self.season,
				"ep_num": self.ep_num,
			}
		)
