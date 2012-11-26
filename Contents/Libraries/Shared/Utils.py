from htmlentitydefs import name2codepoint as n2cp

import re
import subprocess
import sys
import os

# Substitute single HTML entity with match real character.
def substitute_entity(match):
	ent = match.group(3)
	
	if match.group(1) == "#":
		if match.group(2) == '':
			return unichr(int(ent))
		elif match.group(2) == 'x':
			return unichr(int('0x'+ent, 16))
	else:
		cp = n2cp.get(ent)

		if cp:
			return unichr(cp)
		else:
			return match.group()

###############################################################################
# Replace encoded HTML entities with matching real character.

def decode_htmlentities(string):
	entity_re = re.compile(r'&(#?)(x?)(\d{1,5}|\w{1,8});')
	return entity_re.subn(substitute_entity, string)[0]


def add_favourites_cron(platform, name, prefix):

	if (platform == "MacOSX" or platform == "Linux"):
	
		# Check if we already have an entry....
		cmd = 'crontab -l | grep "http://localhost:32400' + str(prefix) + '/favourites/check";'
		cmd += 'if [ $? != 0 ]; then '
		
		# Entry doesn't exist. Get user's crontab.
		cmd += "crontab -l"
		
		# Pipe it to next set of commands....
		cmd += " | ("
		
		# First, re-print user's crontab.
		cmd += "cat"
		
		# Then add a comment.
		cmd += ';echo "# PLEX ' + str(name) + ' New Favourites check"'
		
		# Then add actual crontab entry.
		cmd += ';echo "15 * * * * curl http://localhost:32400' + str(prefix) + '/favourites/check >/dev/null 2>&1";'
		
		# Finished with that group. Send it back to crontab as stdin.
		cmd += ") | "
		
		# Install new crontab from stdin.
		cmd += "crontab"
		
		cmd += ";fi"
		
		subprocess.call(cmd, shell=True)

	elif (platform == "Windows"):
	
		# Work out where we live as a plugin.
		# Note that path[1] is the architecture specific Library path for this plugin.
		plugin_windows_path = sys.path[1]
		plugin_script =  plugin_windows_path + os.sep + "CallFavouritesChecker.vbs"
				
		cmd = [
			'schtasks',
			'/create',
			'/sc','HOURLY',
			'/tn','PLEX ' + str(name) + ' New Favourites Check',
			'/tr','"' + plugin_script + '" ' + 'http://localhost:32400' + str(prefix) + '/favourites/check'
		]
		
		subprocess.call(cmd)
		
	return
	
def del_favourites_cron(platform, name, prefix):

	if (platform == "MacOSX" or platform == "Linux"):
	
		# Get user's crontab.
		cmd = "crontab -l"
			
		# Grep out the lines we added
		cmd += '| grep -v "# PLEX ' + str(name) + ' New Favourites check"'
		cmd += '| grep -v "curl http://localhost:32400' + str(prefix) + '/favourites/check"'
		
		# Install new crontab from stdin.
		cmd += "| crontab"
	
		subprocess.call(cmd, shell=True)

	elif (platform == "Windows"):
	
		cmd = [
			'schtasks',
			'/delete',
			'/tn','PLEX ' + str(name) + ' New Favourites Check',
			'/F'
		]
		
		subprocess.call(cmd)
	
	return
