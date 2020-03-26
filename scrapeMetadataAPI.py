import os
import requests
import json
import re
import urllib
import sys
import base64
import math
from io import BytesIO
from urllib.parse import quote
from PIL import Image
from requests.packages.urllib3.exceptions import InsecureRequestWarning

#Change the lines below to match your config
use_https = True # Set to false for HTTP
server_ip= "<IP ADDRESS>"
server_port = "<PORT>"
username="<USERNAME>"
password="<PASSWORD>"

# Configuration options
scrape_tag= "scraped_from_theporndb"  #Tag to be added to scraped scenes.  Set to None to disable
disambiguate_only = False # Set to True to run script only on scenes tagged due to ambiguous scraping. Useful for doing manual disambgiuation.  Must set ambiguous_tag for this to work
rescrape_scenes= False # If False, script will not rescrape scenes previously scraped successfully.  Must set scrape_tag for this to work

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
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set
add_performers = True 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable

#Other config options
parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = True #If true, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = True #If true, will try to grab an image from babepedia before the one from metadataapi
include_performers_in_title = True #If true, performers will be prepended to the title
clean_filename = True #If true, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
compact_studio_names = True # If true, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings=True # Set to true if your Stash uses SSL w/ a self-signed cert

ENCODING = 'utf-8'

if ignore_ssl_warnings:
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

#Utility Functions
def lreplace(pattern, sub, string):
    """
    Replaces 'pattern' in 'string' with 'sub' if 'pattern' starts 'string'.
    """
    return re.sub('^%s' % pattern, sub, string)

def scrubFileName(file_name):
    scrubbedWords = ['MP4-(.+?)$', ' XXX ', '1080p', '720p', 'WMV-(.+?)$', '-UNKNOWN', ' x264-(.+?)$', 'DVDRip','WEBRIP', 'WEB', '\[PRiVATE\]', 'HEVC', 'x265', 'PRT-xpost', '-xpost', '480p', ' SD', ' HD', '\'', '&']

    clean_name = re.sub('\.', ' ', file_name) ##replace periods
    for word in scrubbedWords: ##delete scrubbedWords
        clean_name = re.sub(word,'',clean_name,0,re.IGNORECASE)
    clean_name = clean_name.strip() #trim
    return clean_name

def keyIsSet(json_object, fields):  #checks if field exists for json_object.  If "fields" is a list, drills down through a tree defined by the list
    if json_object:
        if isinstance(fields, list):
            for field in fields:
                if field in json_object and json_object[field] != None:
                    json_object = json_object[field]
                else:
                    return False
            return True
        else:
            if fields in json_object and json_object[fields] != None:
                return True
    return False

class stash_interface:
    performers = []
    studios = []
    tags = []
    server = ""
    username = ""
    password = ""
    ignore_ssl_warnings = ""
    
    headers = {
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Connection": "keep-alive",
        "DNT": "1"
        }

    def __init__(self, server_url, user = "", pword = "", ignore_ssl = ""):
        self.server = server_url
        self.username = user
        self.password = pword
        self.ignore_ssl_warnings = ignore_ssl
        self.populatePerformers()
        self.populateTags()
        self.populateStudios()
        
    #GraphQL Functions    
    def populatePerformers(self):  
        stashPerformers =[]
        query = """
    {
        allPerformers
      {
        id
        name
        aliases
        image_path
      }
    }
    """
        
        request = requests.post(self.server, json={'query': query}, headers=self.headers, auth=(self.username, self.password), 
                            verify= not self.ignore_ssl_warnings)
        if request.status_code == 200:
            result = request.json()
            stashPerformers = result["data"]["allPerformers"]
        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        self.performers = stashPerformers

    def populateStudios(self):
        stashStudios = []
        query = """
    {
        allStudios
      {
        id
        name
        url
        image_path
      }
    }
    """

        request = requests.post(self.server, json={'query': query}, headers=self.headers, auth=(self.username, self.password),
                                verify=not self.ignore_ssl_warnings)
        if request.status_code == 200:
            result = request.json()
            stashStudios = result["data"]["allStudios"]
        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        self.studios = stashStudios

    def populateTags(self):
        stashTags = []
        query = """
    {
        allTags
      {
        id
        name
      }
    }
    """

        request = requests.post(self.server, json={'query': query}, headers=self.headers, auth=(self.username, self.password),
                                verify=not self.ignore_ssl_warnings)
        if request.status_code == 200:
            result = request.json()
            stashTags = result["data"]["allTags"]
        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        self.tags = stashTags

    def findScenes(self, **kwargs):
        stashScenes =[]
        variables = {}
        accepted_variables = {'filter':'FindFilterType!','scene_filter': 'SceneFilterType!','scene_ids':'[Int!]'}

        variables['filter'] = {} #Add filter to support pages, if necessary
                
        #Add accepted variables to our passsed variables
        for index, (accepted_variable, variable_type) in enumerate(accepted_variables.items()):
            if accepted_variable in kwargs:
                variables[accepted_variable] = kwargs[accepted_variable]

        #Set page and per_page, if not set
        variables['filter'] = variables.get('filter', {})
        variables['filter']['page'] = variables['filter'].get('page', 1)
        variables['filter']['per_page'] = variables['filter'].get('per_page', 100)
            
        #Build our query string (e.g., "findScenes(filter:FindFilterType!){" )
        query_string = "query("+", ".join(":".join(("$"+str(k),accepted_variables[k])) for k,v in variables.items())+'){'

        #Build our findScenes string
        findScenes_string = "findScenes("+", ".join(":".join((str(k),"$"+str(k))) for k,v in variables.items())+'){'

        try:
            query = query_string+findScenes_string+"""
                count
                scenes{
                  id
                  title
                  date
                  details
                  path
                  studio {
                    id
                    name
                    }
                  performers
                    {
                        name
                        id
                    }
                  tags
                    {
                        name
                        id
                    }
                }
              }
            }
            """

            request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers, auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)
    
            if request.status_code == 200:
                result = request.json()
                stashScenes = result["data"]["findScenes"]["scenes"]
                total_pages = math.ceil(result["data"]["findScenes"]["count"] / variables['filter']['per_page'])
                print("Getting Stash Scenes Page: "+str(variables['filter']['page'])+" of "+str(total_pages))
                if (variables['filter']['page'] < total_pages):
                    variables['filter']['page'] = variables['filter']['page']+1
                    stashScenes = stashScenes+self.findScenes(**variables)
            else:
                raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))

        except:
            print("Unexpected error getting stash scene:", sys.exc_info()[0]) 

        return stashScenes  
        
    def updateSceneData(self, scene_data):
        query = """
    mutation sceneUpdate($input:SceneUpdateInput!) {
      sceneUpdate(input: $input){
        title
      }
    }
    """

        variables = {'input': scene_data}
        request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers, 
                                auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)

        if request.status_code == 200:
            result = request.json()
        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))   

        if "errors" in result.keys() and len(result["errors"]) > 0:
            raise Exception ("GraphQL Error when running query. Errors: {}".format(result["errors"])) 
        
    def addPerformer(self, performer_data):
        query = """
    mutation performerCreate($input:PerformerCreateInput!) {
      performerCreate(input: $input){
        id 
      }
    }
    """
        variables = {'input': performer_data}
        
        request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers, 
                                auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)
        try:
            if request.status_code == 200:
                result = request.json()
                self.populatePerformers()
                return result["data"]["performerCreate"]["id"]

            else:
                raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        except:
            print("Error in adding performer:")
            print(variables)
            print(result)

    def getPerformerImage(self, url):
        return base64.b64encode(requests.get(url, auth=HTTPBasicAuth(username, password)).content, 
                                verify= not ignore_ssl_warnings) 

    def addStudio(self, studio_data):
        query = """
        mutation studioCreate($input:StudioCreateInput!) {
          studioCreate(input: $input){
            id       
          }
        }
        """

        variables = {'input': studio_data}

        request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers,
                                auth=(self.username, self.password), verify=not self.ignore_ssl_warnings)
        try:
            if request.status_code == 200:
                result = request.json()

                # Update studios
                self.populateStudios()

                return result["data"]["studioCreate"]["id"]

            else:
                raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        except Exception as e:
            print("Error in adding studio:")
            print(variables)

    def addTag(self, tag_data):
        query = """
        mutation tagCreate($input:TagCreateInput!) {
          tagCreate(input: $input){
            id       
          }
        }
        """

        variables = {'input': tag_data}

        request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers,
                                auth=(self.username, self.password), verify=not self.ignore_ssl_warnings)
        try:
            if request.status_code == 200:
                result = request.json()

                # Update global stash tags so if we add more we don't add duplicates
                self.populateTags()

                return result["data"]["tagCreate"]["id"]

            else:
                raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        except Exception as e:
            print(e)
            print("Error in adding tags:")
            print(variables)
    
    def updatePerformer(self, performer_data):
        query = """
    mutation performerUpdate($input:PerformerUpdateInput!) {
      performerUpdate(input: $input){
        id
        name
        aliases
        image_path 
      }
    }
    """
        variables = {'input': performer_data}
        
        request = requests.post(self.server, json={'query': query, 'variables': variables}, headers=self.headers, 
                                auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)
        if request.status_code == 200:
            return request.json()["data"]["performerUpdate"]

        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query)) 

    def getPerformerByName(self, name):
        for performer in self.performers:
            if performer['name'].lower() == name.lower():
                return performer
            elif "aliases" in performer and performer["aliases"]!=None and name.lower() in performer["aliases"].lower():
                    return performer
                    print("Found an Alias for: "+name)
        return None            

    def getStudioByName(self, name):
        if compact_studio_names:
            name = name.replace(' ','')
        for studio in self.studios:
            if studio['name'].lower().strip() == name.lower().strip():
                return studio
        return None

    def getTagByName(self, name):
        current_tag = str(name.lower().replace('-', ' ').replace('(', '').replace(')', '').replace(
            'pov', '').replace('standing', '').strip().replace(' ', ''))
        for tag in self.tags:
            if str(tag['name'].lower()) == current_tag:
                return tag
            if str(tag['name'].lower().replace(' ', '').replace('-', ' ')) == current_tag:
                return tag
        return None
        
#Scrape-specific functions        
def createSceneUpdateFromSceneData(scene_data):  #Scene data returned from stash has a different format than what is accepted by the UpdateScene graphQL query.  This converts one format to another
    scene_update_data = {}
    if keyIsSet(scene_data, "id"): scene_update_data["id"] = scene_data["id"]
    if keyIsSet(scene_data, "title"): scene_update_data["title"] = scene_data["title"]
    if keyIsSet(scene_data, "details"): scene_update_data["details"] = scene_data["details"]
    if keyIsSet(scene_data, "url"): scene_update_data["url"] = scene_data["url"]
    if keyIsSet(scene_data, "date"): scene_update_data["date"] = scene_data["date"]
    if keyIsSet(scene_data, "rating"): scene_update_data["rating"] = scene_data["rating"]
    if keyIsSet(scene_data, "studio"): scene_update_data["studio_id"] = scene_data["studio"]["id"]
    if keyIsSet(scene_data, "performers"):
        scene_update_data["performer_ids"] = []
        for performer in scene_data["performers"]:
            scene_update_data["performer_ids"].append(performer["id"])
    else:
        scene_update_data["performer_ids"] = []
    if keyIsSet(scene_data, "tags"):
        scene_update_data["tag_ids"] = []
        for tag in scene_data["tags"]:
            scene_update_data["tag_ids"].append(tag["id"])
    else:
        scene_update_data["tag_ids"] = []
    return scene_update_data
    
def createStashPerformerData(metadataapi_performer): #Creates stash-compliant data from raw data provided by metadataapi
    stash_performer = {}
    if keyIsSet(metadataapi_performer, ["parent", "name"]): stash_performer["name"] = metadataapi_performer["parent"]["name"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "birthday"]): stash_performer["birthdate"] = \
        metadataapi_performer["parent"]["extras"]["birthday"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "measurements"]): stash_performer["measurements"] = \
        metadataapi_performer["parent"]["extras"]["measurements"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "tattoos"]): stash_performer["tattoos"] = \
        metadataapi_performer["parent"]["extras"]["tattoos"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "piercings"]): stash_performer["piercings"] = \
        metadataapi_performer["parent"]["extras"]["piercings"]
    # TODO: support Aliases

    return stash_performer

def createStashStudioData(metadataapi_studio):  # Creates stash-compliant data from raw data provided by metadataapi
    stash_studio = {}
    if compact_studio_names:
        stash_studio["name"] = metadataapi_studio["name"].replace(' ', '')
    else:
        stash_studio["name"] = metadataapi_studio["name"]
    stash_studio["url"] = metadataapi_studio["url"]
    if metadataapi_studio["logo"] is not None and "default.png" not in metadataapi_studio["logo"]:
        stash_studio["image"] = get_base64_image(metadataapi_studio["logo"])

    return stash_studio

def createStashTagData(metadataapi_tag):  # Creates stash-compliant data from raw data provided by metadataapi
    stash_tag = {}
    stash_tag["name"] = metadataapi_tag["tag"].lower().replace('-', ' ').replace('(', '').replace(')', '').replace(
        'pov', '').replace('standing', '').strip().title()

    return stash_tag

def get_base64_image(image_url):
    # Download

    image = requests.get(image_url).content
    image_b64 = base64.b64encode(image)
    if image_b64:
        return image_b64.decode(ENCODING)

def getJpegImage(image_url):
    try:
        r = requests.get(image_url, stream=True)
        r.raw.decode_content = True # handle spurious Content-Encoding
        image = Image.open(r.raw)
        #image = Image.open(urllib.request.urlopen(image_url))
        if image.format:
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image = buffered.getvalue()
            return image

    except Exception as e:
        print("Error Getting Image: "+str(e))

    return None    

def scrapePerformerFreeones(name):
    query = """
{
	scrapeFreeones(performer_name: \""""+name+"""\")
    { url twitter instagram birthdate ethnicity country eye_color height measurements fake_tits career_length tattoos piercings aliases }

}
"""
    
    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), 
                            verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        return request.json()["data"]["scrapeFreeones"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))

def getBabepediaImage(name):
    url = "https://www.babepedia.com/pics/"+urllib.parse.quote(name)+".jpg"
    if requests.get(url):
        return getJpegImage(url)
    return None

def getMetadataapiImage(name):
    url = "https://metadataapi.net/api/performers?q="+urllib.parse.quote(name)
    if len(requests.get(url).json()["data"])==1: #If we only have 1 hit
        raw_data = requests.get(url).json()["data"][0]
        image_url = raw_data["image"]
        if not "default.png" in image_url:
            image = getJpegImage(image_url)
            return image
    return None

def getPerformerImageB64(name):  #Searches Babepedia and MetadataAPI for a performer image, returns it as a base64 encoding
    try:
        performer = my_stash.getPerformerByName(name)

        #Try Babepedia if flag is set    
        if get_images_babepedia:
            # Try Babepedia
            image = getBabepediaImage(name)
            if image:
                image_b64 = base64.b64encode(image)
                stringbase = str(image_b64)
                return image_b64.decode(ENCODING)

            # Try aliases at Babepedia
            if keyIsSet(performer, "aliases"):
                aliases = [x.strip() for x in performer["aliases"].split(',')]
                for alias in aliases:
                    image = getBabepediaImage(alias)
                    if image:
                        image_b64 = base64.b64encode(image)
                        stringbase = str(image_b64)
                        return image_b64.decode(ENCODING)
                        
        # Try thePornDB
        image = getMetadataapiImage(name)
        if image:
            image_b64 = base64.b64encode(image)
            stringbase = str(image_b64)
            return image_b64.decode(ENCODING)
        
        return None
    except Exception as e:
        print(e)

def scrapeMetadataAPI(query):  # Scrapes MetadataAPI based on query.  Returns an array of scenes as results, or None
    url = "https://metadataapi.net/api/scenes?parse="+urllib.parse.quote(query)    
    try:
        return requests.get(url).json()["data"]
    except ValueError:
        print("Error communicating with MetadataAPI")        
        
def manuallyDisambiguateMetadataAPIResults( scrape_query, scraped_data):
    print("Found ambiguous result.  Which should we select?:")
    for index, scene in enumerate(scraped_data):
        print(index+1, end = ': ')
        if keyIsSet(scene, ['site','name']): print(scene['site']['name'], end=" ")
        if keyIsSet(scene, ['date']): print(scene['date'], end=" ")
        if keyIsSet(scene, ['title']): print(scene['title'], end=" ")
        print('')
    print("0: None of the above.  Skip this scene.")
    
    selection = -1
    while selection < 0 or selection > len(scraped_data):
        try:
            selection = int(input("Selection: "))
            if selection  < 0 or selection > len(scraped_data):
                raise ValueError
        except ValueError:
            print("Invalid Selection")
    
    if selection == 0:
        return scraped_data
    else:
        new_data = []
        new_data.append(scraped_data[selection-1])
        return new_data

def updateSceneFromMetadataAPI(scene):
    try:
        scrape_query = ""
        tag_ids_to_add = []
        if ambiguous_tag: ambiguous_tag_id = my_stash.getTagByName(ambiguous_tag)['id']
        
        scene_data = createSceneUpdateFromSceneData(scene)  # Start with our current data as a template
        
        if parse_with_filename:
            file_name = re.search(r'^\/(.+\/)*(.+)\.(.+)$', scene['path']).group(2)
            if clean_filename:
                file_name = scrubFileName(file_name)
            scrape_query = file_name
        else:
            scrape_query = scene_data['title']

        print("Grabbing Data For: " + scrape_query)
        scraped_data = scrapeMetadataAPI(scrape_query)

        if scraped_data:  
            if not parse_with_filename:
                if len(scraped_data)>1:
                    #Try to add studio
                    if keyIsSet(scene, "studio"):
                        scrape_query = scrape_query + " " + scene['studio']['name']
                        new_data = scrapeMetadataAPI(scrape_query)
                        if new_data: scraped_data = new_data
            
                if len(scraped_data)>1:    
                    #Try to and date
                    if keyIsSet(scene_data, "date"):
                        scrape_query = scrape_query + " " + scene_data['date']
                        new_data = scrapeMetadataAPI(scrape_query)
                        if new_data: scraped_data = new_data
            
            if len(scraped_data) > 1:  # Fix a bug where multiple ThePornDB results are the same scene
                scene_iter = iter(scraped_data)
                next(scene_iter)
                for scene in scene_iter:
                    if scene['title'] == scraped_data[0]['title']:
                        scraped_data.remove(scene)
            
            if len(scraped_data) > 1 and manual_disambiguate: # Manual disambiguate
                scraped_data = manuallyDisambiguateMetadataAPIResults(scrape_query, scraped_data)
            
            if len(scraped_data) > 1 and auto_disambiguate:  #Auto disambiguate
                print("Auto disambiguating...")
                print("Matched "+scrape_query+" with "+scraped_data[0]['title'])
                new_data = []
                new_data.append(scraped_data[0])
                scraped_data = new_data
            
            if len(scraped_data) > 1:  # Handling of ambiguous scenes
                print("Ambiguous data found for: [{}], skipping".format(scrape_query))
                if ambiguous_tag:
                    tag_ids_to_add.append(ambiguous_tag_id)           
                    scene_data["tag_ids"] = list(set(scene_data["tag_ids"] + tag_ids_to_add))
                    my_stash.updateSceneData(scene_data)
                return
            
            scraped_scene = scraped_data[0]
            # If we got new data, update our current data with the new
            if ambiguous_tag and ambiguous_tag_id in scene_data["tag_ids"]: scene_data["tag_ids"].remove(ambiguous_tag_id) #Remove ambiguous tag if we disambiguated
            
            if set_details: scene_data["details"] = scraped_scene["description"] #Add details
            if set_date: scene_data["date"] = scraped_scene["date"]  #Add date
            if set_cover_image and keyIsSet(scraped_scene, ["background","small"]) and "default.png" not in scraped_scene["background"]['small']:  #Add cover_image 
                cover_image = getJpegImage(scraped_scene["background"]['small'])
                if cover_image:
                    image_b64 = base64.b64encode(cover_image)
                    stringbase = str(image_b64)
                    scene_data["cover_image"] = image_b64.decode(ENCODING)

            # Add Studio to the scene
            if set_studio and keyIsSet(scraped_scene, "site"):
                studio_id = None
                scraped_studio = scraped_scene['site']
                stash_studio = my_stash.getStudioByName(scraped_studio['name'])
                if stash_studio:
                    studio_id = stash_studio["id"]
                elif add_studio:
                    # Add the Studio to Stash
                    print("Did not find " + scraped_studio['name'] + " in Stash.  Adding Studio.")
                    studio_id = my_stash.addStudio((createStashStudioData(scraped_studio)))

                if studio_id != None:  # If we have a valid ID, add studio to Scene
                    scene_data["studio_id"] = studio_id

            # Add Tags to the scene
            tags_to_add = []
            if scrape_tag: tags_to_add.append({'tag':scrape_tag})
            if set_tags and keyIsSet(scraped_scene, "tags"):
                tags_to_add = tags_to_add + scraped_scene["tags"]
            
            for tag_dict in tags_to_add:
                tag_id = None
                stash_tag = my_stash.getTagByName(tag_dict['tag'])
                if stash_tag:
                    tag_id = stash_tag["id"]
                elif add_tags or (scrape_tag and tag_dict['tag'] == scrape_tag):
                    # Add the Tag to Stash
                    print("Did not find " + tag_dict['tag'] + " in Stash.  Adding Tag.")
                    tag_id = my_stash.addTag((createStashTagData(tag_dict)))

                if tag_id != None:  # If we have a valid ID, add tag to Scene
                    tag_ids_to_add.append(tag_id)
                scene_data["tag_ids"] = list(set(scene_data["tag_ids"] + tag_ids_to_add))

            # Add performers to scene
            if set_performers and keyIsSet(scraped_scene, "performers"):
                scraped_performer_ids = []
                for scraped_performer in scraped_scene["performers"]:
                    performer_id = None
                    if not keyIsSet(scraped_performer, ['parent','name']): #No "parent" performer at ThePornDB, skip addition
                        print(scraped_performer['parent']['name']+" is linked to a site, but not a general performer at ThePornDB.  Skipping addition.")
                        break
                    else:
                        stash_performer = my_stash.getPerformerByName(scraped_performer['parent']['name'])
                        if stash_performer:
                            performer_id = stash_performer["id"]
                        elif add_performers and ((scraped_performer['name'].lower() in scene_data[
                            "title"].lower()) or not only_add_female_performers or (
                                                         keyIsSet(scraped_performer, ["parent", "extras", "gender"]) and
                                                         scraped_performer["parent"]["extras"][
                                                             "gender"] == 'Female')):  # Add performer if we meet relevant requirements
                            print("Did not find " + scraped_performer['parent']['name'] + " in Stash.  Adding performer.")

                            performer_id = my_stash.addPerformer(createStashPerformerData(scraped_performer))
                            performer_data = {}

                            if scrape_performers_freeones:
                                performer_data = scrapePerformerFreeones(scraped_performer['parent']['name'])
                                if not performer_data:
                                    performer_data = {}

                            performer_data["id"] = performer_id

                            performer_data["image"] = getPerformerImageB64(scraped_performer['parent']['name'])
                            my_stash.updatePerformer(performer_data)

                        if performer_id != None:  # If we have a valid ID, add performer to Scene
                            scraped_performer_ids.append(performer_id)
                scene_data["performer_ids"] = list(set(scene_data["performer_ids"] + scraped_performer_ids))                              
            # Set Title
            if set_title:
                performer_names = [] 
                if keyIsSet(scene_data, "performer_ids"):
                    for performer_id in scene_data["performer_ids"]:
                        for performer in my_stash.performers:
                            if performer['id'] == performer_id:
                                performer_names.append(performer["name"])
                new_title = ""
                if include_performers_in_title and len(performer_names) > 2:
                    new_title = "{}, and {}".format(", ".join(performer_names[:-1]), performer_names[-1])
                if include_performers_in_title and len(performer_names) == 2:
                    new_title = performer_names[0] + " and " + performer_names[1]
                if include_performers_in_title and len(performer_names) == 1:
                    new_title = performer_names[0]
                if include_performers_in_title:
                    for name in performer_names:
                        scraped_scene["title"] = lreplace(name, '', scraped_scene["title"]).strip()

                new_title = new_title + " " + scraped_scene["title"]
                scene_data["title"] = new_title

            my_stash.updateSceneData(scene_data)
            print("Success")
        else:
            print("No data found for: [{}]".format(scrape_query))
    except Exception as e:
        print("Exception encountered when scraping '"+scrape_query+"'. Exception: "+str(e))

def main():
    try:
        global my_stash 
        
        if use_https:
            server = 'https://'+str(server_ip)+':'+str(server_port)+'/graphql'
        else:
            server = 'http://'+str(server_ip)+':'+str(server_port)+'/graphql'
        
        my_stash = stash_interface(server, username, password, ignore_ssl_warnings)
           
        if ambiguous_tag:
            stash_tag = my_stash.getTagByName(ambiguous_tag)
            if stash_tag:
                ambiguous_tag_id = stash_tag["id"]
            else:
                stash_tag = {}
                stash_tag["name"]= ambiguous_tag
                # Add the Tag to Stash
                print("Did not find " + ambiguous_tag + " in Stash.  Adding Tag.")
                ambiguous_tag_id = my_stash.addTag(stash_tag)

        if scrape_tag:
            stash_tag = my_stash.getTagByName(scrape_tag)
            if stash_tag:
                scrape_tag_id = stash_tag["id"]
            else:
                stash_tag = {}
                stash_tag["name"]= scrape_tag
                # Add the Tag to Stash
                print("Did not find " + scrape_tag + " in Stash.  Adding Tag.")
                scrape_tag_id = my_stash.addTag(stash_tag)
        
        query=""
        if len(sys.argv) > 1:
            query = sys.argv[1]
        
        findScenes_params = {}
        findScenes_params['filter'] = {'q':query, 'per_page':100, 'sort':"created_at", 'direction':'DESC'}
        
        if disambiguate_only:  #If only disambiguating scenes
            findScenes_params['scene_filter'] = {'tags': { 'modifier':'INCLUDES', 'value': [ambiguous_tag_id]}}
        elif not rescrape_scenes: #If only scraping unscraped scenes
            findScenes_params['scene_filter'] = {'tags': { 'modifier':'EXCLUDES', 'value': [scrape_tag_id]}}
        
        scenes = my_stash.findScenes(**findScenes_params)

        for scene in scenes:
            updateSceneFromMetadataAPI(scene)
        
        print("Success! Finished.")

    except Exception as e:
        print(e)

if __name__ == "__main__":
    main()
    

