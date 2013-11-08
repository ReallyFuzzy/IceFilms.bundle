""" 
Module to hold site specific config options.

Note that site specific parsing lives in Parsing.py
"""

VIDEO_PREFIX = "/video/icefilms"
NAME="IceFilms"

LATEST_VERSION_URL = 'http://bit.ly/xjrEcV'

# Plugin interest tracking.
VERSION = "13.11.08.1"
VERSION_URLS = {
	"13.11.08.1": "http://bit.ly/1beJy1t",
	"12.11.23.1": "http://bit.ly/Wnnzy7",
	"12.02.26.1": "http://bit.ly/z3wPud",
	"1.0" : "http://bit.ly/xGIrmH"
}

MOVIE_HD_ICON='icon-movie-hd.png'
GENRE_ICON='icon-genre.png'
AZ_ICON='icon-az.png'

ADDITIONAL_SOURCES = ['lmwt']

# When a provider uses CAPTCHAs, the back and forth needed to get the user to solve the CAPTCHA
# means that we eventually stop using the main site's (i.e: iceFilm) URL service. As a result,
# when it comes time to play the video, the main site's URL service is no longer called and
# can't mark the video has having been played. So, instead, we let the Captcha Play menu re-insert
# a reference to the main site's URL service.
def GetCaptchaPlayURL():

	return "play://icefilms.info/?browse_url=%s&final_url=%s"
	
def GetGenres():

	return [
		"Action", "Animation", "Comedy", "Documentary", "Drama", "Family", "Horror", "Romance",
		"Sci-Fi", "Thriller"
	]
	
def GetSections(type, genre):

	type_desc = "Movies"
	if (type == "tv"):
		type_desc = "TV Shows"
		
	sections =  [
		{ 
			'title': 'Popular',
			'summary': "List of most popular " + type_desc,
			'icon': R("Popular.png"),
			'sort': 'popular',
			'type': 'items',
		},
		{ 
			'title': 'Highly Rated',
			'summary': "List of highly rated " + type_desc,
			'icon': R("Favorite.png"),
			'sort': 'rating',
			'type': 'items',
		},
		{
			'title': 'Latest Releases',
			'summary': "List of latest releases",
			'icon': R("Recent.png"),
			'sort': 'release', 
			'type': 'items',
		},
		{
			'title': 'Recently Added',
			'summary': "List of recently added " + type_desc,
			'icon': R("History.png"),
			'sort': 'added',
			'type': 'items',
		},
	]
	
	if (not genre):
		
		if (type == 'movies'):
		
			sections.append(
				{
					'title': "HD Movies",
					'summary': "Complete list of movies made available in HD",
					'icon': R(MOVIE_HD_ICON),
					'genre': 'hd',
					'type': 'type',
				},
			)
		
		sections.append(
			{
				'title':"Genre",
				'summary':"Browse " + type_desc + " by genre.",
				'icon':R(GENRE_ICON),
				'type':'genre'
			}
		)
		
		sections.append(
			{
				'title': "A-Z List",
				'summary': "Browse " + type_desc + " in alphabetical order",
				'icon': R(AZ_ICON),
				'type': 'alphabet'
			}
		)
			
		sections.append(
			{
				'type': 'search'
			}
		)
	
	return sections