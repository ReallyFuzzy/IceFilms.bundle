import smtplib
import re

import dns.resolver
	      
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

# Do not set these here as they will get overwritten when this file is updated.
# Set them in the user file: NotifierEmailSettings.py.
# See Plugin's Wiki page for more info.
NOTIFY_SMTP_SERVER = None
NOTIFY_SMTP_TLS = False
NOTIFY_SMTP_SERVER_PORT = smtplib.SMTP_PORT
NOTIFY_SMTP_USER = None
NOTIFY_SMTP_PASS = None
	
try:
	import NotifierEmailSettings
	
	NOTIFY_SMTP_SERVER = NotifierEmailSettings.NOTIFY_SMTP_SERVER
	
	if (hasattr(NotifierEmailSettings, "NOTIFY_SMTP_USER")):
		# Assume if user / password is a combo.
		NOTIFY_SMTP_USER = NotifierEmailSettings.NOTIFY_SMTP_USER
		NOTIFY_SMTP_PASS = NotifierEmailSettings.NOTIFY_SMTP_PASS
	
	if (
		hasattr(NotifierEmailSettings, "NOTIFY_SMTP_SERVER_PORT") and
		NotifierEmailSettings.NOTIFY_SMTP_SERVER_PORT
	):
		NOTIFY_SMTP_SERVER_PORT = NotifierEmailSettings.NOTIFY_SMTP_SERVER_PORT 
		
	if (
		hasattr(NotifierEmailSettings, "NOTIFY_SMTP_TLS") and 
		NotifierEmailSettings.NOTIFY_SMTP_TLS
	):
		NOTIFY_SMTP_TLS = NotifierEmailSettings.NOTIFY_SMTP_TLS
		
except Exception, ex:
	# Couldn't import user settings. Use defaults.
	Log("ERROR Loading user mail settings")
	Log(str(ex))
	pass	
	
def notify(recipient, name, title, img_src):
	
	# Build Message up.
	recipients = [recipient]
	sender = str(name) + ' Plex Plugin <favourites@' +  str(name).lower().replace(" ","") + '.example.com>'
	
	msg = MIMEMultipart('alternative')
	msg['Subject'] = '[Plex ' + str(name) + '] New episode of ' + title + ' available'
	msg['From'] = sender
	msg['To'] = recipients[0]
	
	body = ("""\
	<html><BODY><table width=95%%><tr>
	  <td width="5%%" style="padding-right: 20px"><img src="%s" height=200></td>
	  <td valign="top">
	  A new episode of %s has been found on %s.<p>
	  You can now watch this via your Favourites in Plex's %s plugin.<p>
	  You will not be notified about any additional new episodes until you have watched or mark as watched all new episodes in Plex. 
	  </td>
	</tr></table></body></html>
	""")
	body = body % (img_src, title, str(name), str(name))
	
	msg.attach(MIMEText(body,'html'))

	# Send Message.
	# If we've been given an SMTP user name, use that, otherwise use our made up name.	
	smtp_user = NOTIFY_SMTP_USER if NOTIFY_SMTP_USER else sender
	
	# Do we have an SMTP Host to use?
	if (NOTIFY_SMTP_SERVER):
		smtp_servers = [NOTIFY_SMTP_SERVER]
	else:
		# Nope. Let's try to lookup the recipient's hostname, get the matching
		# MX record and hopefully talk straight to it.
		smtp_servers = []
		recipient_host = re.search("@([\w.]+)", recipient).group(1)
		answers = dns.resolver.query(recipient_host, 'MX')
		for answer in answers:
			smtp_servers.append(".".join(answer.exchange[:-1]))
			
	mail_sent = False
	
	for smtp_server in smtp_servers:
	
		Log("Trying with SMTP server: " + smtp_server + ":" + str(NOTIFY_SMTP_SERVER_PORT))
		
		try:
			mail_server = smtplib.SMTP(smtp_server,NOTIFY_SMTP_SERVER_PORT)
			mail_server.ehlo()
			
			if (NOTIFY_SMTP_TLS):
				Log("Using TLS")
				mail_server.starttls()
				mail_server.ehlo()
				
			if (NOTIFY_SMTP_USER):
				Log("Logging in as " + NOTIFY_SMTP_USER)
				mail_server.login(NOTIFY_SMTP_USER, NOTIFY_SMTP_PASS)
            	
			mail_server.sendmail(smtp_user, recipients, msg.as_string())
			mail_server.quit()
			mail_server.close()
			mail_sent = True
			break
			
		except Exception, ex:
			Log(str(ex))
			pass
	
	if (not mail_sent):
		raise Exception("Notification Not Sent")