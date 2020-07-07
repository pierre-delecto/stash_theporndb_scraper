#!/usr/bin/env python

###########################################
### NZBGET POST-PROCESSING SCRIPT       ###

# A simple script to ask Stash to scan for new content, initiate a scrape from TPDB, and run a generate task for the new content.
# Note that your NZBGet system must have the requirements for the scrapeScenes.py script, so run pip install -r requirements.txt on that system before running.
# Filetype is ".py3" so that NZBGet can be forced to use python3 to execute, as python2 is the default on most systems. If the "python" command runs python3 on your NZBGet system, change the extension to ".py".  Otherwise, ou may need to set the ShellOveride field in the ExtensionScripts section of your NZBGet config to include ".py3=/usr/bin/python3" (or whatever your path to python3 is) to force use of python3.

### NZBGET POST-PROCESSING SCRIPT       ###
###########################################


import sys
import os
import StashInterface
import scrapeScenes
import time


# Exit codes used by NZBGet
POSTPROCESS_SUCCESS=93
POSTPROCESS_NONE=95
POSTPROCESS_ERROR=94


#Check par and unpack status for errors
if os.environ['NZBPP_PARSTATUS'] == '1' or os.environ['NZBPP_PARSTATUS'] == '4' or os.environ['NZBPP_UNPACKSTATUS'] == '1':
    print('[WARNING] Download of "%s" has failed, exiting' % (os.environ['NZBPP_NZBNAME']))
    sys.exit(POSTPROCESS_NONE)

StashInterface.main(['-s','-w'])
time.sleep(30)
scrapeScenes.main(['-no'])
StashInterface.main(['-g'])

sys.exit(POSTPROCESS_SUCCESS)