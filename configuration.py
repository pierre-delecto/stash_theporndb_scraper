#Server configuration
use_https = True # Set to false for HTTP
server_ip= "192.168.1.3"
server_port = "9999"
username="abggm"
password="abggmpass"

# Configuration options
scrape_tag= "scraped_from_theporndb"  #Tag to be added to scraped scenes.  Set to None to disable
disambiguate_only = False # Set to True to run script only on scenes tagged due to ambiguous scraping. Useful for doing manual disambgiuation.  Must set ambiguous_tag for this to work
rescrape_scenes= True # If False, script will not rescrape scenes previously scraped successfully.  Must set scrape_tag for this to work

#Set what fields we scrape
set_details = True
set_date = True
set_cover_image = True
set_performers = True
set_studio = True
set_tags = True
set_title = True 

#Set what content we add to Stash, if found in ThePornDB but not in Stash
add_studio = True  
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set.  Will also tag ambiguous performers if set to true.
add_performers = True 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)

#Other config options
parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
dirs_in_query = 0
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = True #If true, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = True #If true, will try to grab an image from babepedia before the one from metadataapi
include_performers_in_title = True #If true, performers will be prepended to the title
clean_filename = True #If true, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
compact_studio_names = True # If true, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings= True # Set to true if your Stash uses SSL w/ a self-signed cert