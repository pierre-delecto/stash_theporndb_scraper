This is a Python script intended to run from a command line to scrape information for Stash scenes from ThePornDB (metadataapi.net).  Requires Python 3.  Developed for the "development" version (not the "latest"/stable branch) of Stash, but may also work with "latest."

The script supports setting titles, performers, tags, studios, details, and date.  All fields are optional and can be disabled via config options.  

Current title, studio, details, and date are overwritten with new data. Current performers and tags are maintained with new results added. 

If a new performer/studio/tag is found that's not currently in Stash, the script can optionally add the performer/studio/tag using data from ThePornDB.  It can also optionally (via config options) scrape FreeOnes for performer data, and try to pull an image from Babepedia.

# Usage
## Installation
- Download the script and install the requirements (pip install -r requirements.txt).  
- Rename SAMPLE_configuration.py to configuration.py. 
- Modify the configuration.py to include the URL of your Stash endpoint.  Be sure to specify http or https.  Also include your username and password, if using.  Set any configuration parameters you'd like, which are explained in the script.  

## Using the script
Run the script by entering 'python scrapeScenes.py' into your terminal.  If run without parameters, the script scrapes all Stash scenes using the options from configuration.py.  Add the -h flag to see other supported command line options.

Successfully scraped scenes are tagged with a custom tag, and excluded from future scans.  

Where ThePornDB returns multiple results for a scene, the script supports automatic disambiguation, manual disambiguation, or skipping the scene. Scenes that are skipped due to ambiguous results can be tagged.  An additional execution of the script can then be run only for previously skipped scenes with the ambiguous results tag. 
