from search import GoogleSearch
import re

def GetSearchResults(query=None,type=None, exact=False):
	
	if (type=="movies"):
		# This a google search. The -tv will ommit all TV shows.
		search = 'intitle:%s -"Episode List" -"Series Rating"' % (query)
	else:
		search = 'allintitle:%s "Episode List"' % (query)
	
	gs = GoogleSearch(search)
	gs.results_per_page = 25
	gs.page = 0
	results = gs.get_results() +  gs.get_results()
	items = []
	
	for res in results:
	
		name = re.sub(
			'(<em>|</em>|<a>|</a>|DivX|-|icefilms(\.info)?|<b>\.\.\.</b>|Episode List|links)',
			'',
			res.title.encode('utf8')
		).strip()

		url=res.url
		video_url = re.search("icefilms\.info(/.*)", url).group(1)
		
		res = {}
		
		res['type'] = type
		res['title'] = name

		match = re.search("(.*)\((\d*)\)", res['title'])
		
		if (match):
			res['title'] = match.group(1).strip()
			res['year'] = int(match.group(2).strip())
			
		res['id'] = video_url
		
		items.append(res)
	
	return items
	
items = GetSearchResults("the", "tv")
print items
print len(items)
