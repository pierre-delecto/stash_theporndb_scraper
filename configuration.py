#Server configuration
use_https = True # Set to false for HTTP
server_ip= "<IP_ADDRESS>"
server_port = "<PORT>"
username="<USERNAME>"
password="<PASSWORD>"

# Configuration options
scrape_tag= "scraped_from_theporndb"  #Tag to be added to scraped scenes.  Set to None to disable
disambiguate_only = False # Set to True to run script only on scenes tagged due to ambiguous scraping. Useful for doing manual disambgiuation.  Must set ambiguous_tag for this to work
verify_aliases_only = False # Set to True to scrape only scenes that were skipped due to unconfirmed aliases - set confirm_questionable_aliases to True before using
rescrape_scenes= True # If False, script will not rescrape scenes previously scraped successfully.  Must set scrape_tag for this to work

#Set what fields we scrape
set_details = True
set_date = True
set_cover_image = True
set_performers = True
set_studio = True
set_tags = True
set_title = True
set_url = True

#Set what content we add to Stash, if found in ThePornDB but not in Stash
add_studio = True  
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set.  Will also tag ambiguous performers if set to true.
add_performers = True 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
#Disambiguation options for when a specific performer can't be verified
tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)
confirm_questionable_aliases = True #If True, when TPBD lists an alias that we can't verify, manually prompt for config.  Otherwise they are tagged for later reprocessing
trust_tpbd_aliases = True #If true, when TPBD lists an alias that we can't verify, just trust TBPD to be correct.  May lead to incorrect tagging

#Other config options
parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
dirs_in_query = 0 # The number of directories up the path to be included in the query for a filename parse query.  For example, if the file  is at \performer\mysite\video.mp4 and dirs_in_query is 1, query would be "mysite video."  If set to two, query would be "performer mysite video", etc.
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = True #If true, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = True #If true, will try to grab an image from babepedia before the one from ThePornDB
include_performers_in_title = True #If true, performers will be prepended to the title
clean_filename = True #If true, will try to clean up filenames before attempting scrape. Often unnecessary, as ThePornDB already does this
compact_studio_names = True # If true, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings= True # Set to true if your Stash uses SSL w/ a self-signed cert
