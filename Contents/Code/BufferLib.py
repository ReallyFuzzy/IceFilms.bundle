class HTTPBetterErrorProcessor(urllib2.HTTPErrorProcessor):

	def http_response(self, request, response):
	
		code, msg, hdrs = response.code, response.msg, response.info()
	
		# was: if code not in (200, 206):
		if not (200 <= code < 300):
			response = self.parent.error('http', request, response, code, msg, hdrs)
	
		return response

	https_response = http_response