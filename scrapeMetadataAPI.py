import os
import requests
import json
import re
import urllib
import sys
import base64
import math
import logging
from io import BytesIO
from urllib.parse import quote
from PIL import Image
from requests.packages.urllib3.exceptions import InsecureRequestWarning

###########################################################
#CONFIGURATION OPTIONS HAVE BEEN MOVED TO CONFIGURATION.PY#
###########################################################

#Utility Functions
def lreplace(pattern, sub, string):
    """
    Replaces 'pattern' in 'string' with 'sub' if 'pattern' starts 'string'.
    """
    return re.sub('^%s' % pattern, sub, string)

def scrubFileName(file_name):
    scrubbedWords = ['MP4-(.+?)$', ' XXX ', '1080p', '720p', 'WMV-(.+?)$', '-UNKNOWN', ' x264-(.+?)$', 'DVDRip','WEBRIP', 'WEB', '\[PRiVATE\]', 'HEVC', 'x265', 'PRT-xpost', '-xpost', '480p', ' SD', ' HD', '\'', '&']
    clean_name = ""
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

def listToLower(input_list):
    output_list = []
    for item in input_list:
        if isinstance(item, str):
            output_list.append(item.lower())
        else:
            output_list.append(item)
    return output_list

#Stash GraphQL Class
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
        if ignore_ssl: requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        self.populatePerformers()
        self.populateTags()
        self.populateStudios()
        
    #GraphQL Functions    
    
    def callGraphQL(self, query, variables = None):
        json = {}
        json['query'] = query
        if variables:
            json['variables'] = variables
        
        try:
            request = requests.post(self.server, json=json, headers=self.headers, auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)
            if request.status_code == 200:
                result = request.json()
                return result
            else:
                raise Exception("GraphQL query failed to run by returning code of {}. Query: {}.  Variables: {}".format(request.status_code, query, variables))
        except requests.exceptions.SSLError:
            proceed = input("Caught certificate error trying to talk to Stash. Add ignore_ssl_warnings=True to your configuration.py to ignore permanently. Ignore for now? (yes/no):")
            if proceed == 'y' or proceed == 'Y' or proceed =='Yes' or proceed =='yes':
                self.ignore_ssl_warnings =True
                requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
                return self.callGraphQL(query, variables)
            else:
                print("Exiting.")
                sys.exit()
    
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
        result = self.callGraphQL(query)
        stashPerformers = result["data"]["allPerformers"]
        for performer in stashPerformers:
            if isinstance(performer['aliases'], str): performer['aliases'] = [alias.strip() for alias in performer['aliases'].split(',')] #Convert comma delimited string to list
        
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
        result = self.callGraphQL(query)
        self.studios = result["data"]["allStudios"]

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
        result = self.callGraphQL(query)
        self.tags = result["data"]["allTags"]  

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
            result = self.callGraphQL(query, variables)

            stashScenes = result["data"]["findScenes"]["scenes"]
            total_pages = math.ceil(result["data"]["findScenes"]["count"] / variables['filter']['per_page'])
            print("Getting Stash Scenes Page: "+str(variables['filter']['page'])+" of "+str(total_pages))
            if (variables['filter']['page'] < total_pages):  #If we're not at the last page, recurse with page +1 
                variables['filter']['page'] = variables['filter']['page']+1
                stashScenes = stashScenes+self.findScenes(**variables)

        except:
            logging.error("Unexpected error getting stash scene:", exc_info=True)
            
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
        result = self.callGraphQL(query, variables)

        if "errors" in result.keys() and len(result["errors"]) > 0:
            raise Exception ("GraphQL Error when running query. Errors: {}".format(result["errors"])) 
        
    def addPerformer(self, performer_data):
        result = None
        update_data = performer_data
        if update_data.get('aliases', None):
            update_data['aliases'] = ', '.join(update_data['aliases'])
        
        query = """
    mutation performerCreate($input:PerformerCreateInput!) {
      performerCreate(input: $input){
        id 
      }
    }
    """
        variables = {'input': update_data}
        
        try:
            result = self.callGraphQL(query, variables)
            self.populatePerformers()
            return result["data"]["performerCreate"]["id"]

        except:
            logging.error("Error in adding performer", exc_info=True)
            logging.error(variables)
            logging.error(result)

    def getPerformerImage(self, url):
        return base64.b64encode(requests.get(url, auth=requests.auth.HTTPBasicAuth(username, password)).content, 
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
        try:
            result = self.callGraphQL(query, variables)
            self.populateStudios()
            return result["data"]["studioCreate"]["id"]
        except Exception as e:
            logging.error("Error in adding studio:", exc_info=True)
            logging.error(variables)

    def addTag(self, tag_data):
        query = """
        mutation tagCreate($input:TagCreateInput!) {
          tagCreate(input: $input){
            id       
          }
        }
        """
        variables = {'input': tag_data}

        try:
            result = self.callGraphQL(query, variables)
            self.populateTags()
            return result["data"]["tagCreate"]["id"]
        except Exception as e:
            logging.error("Error in adding tags", exc_info=True)
            logging.error(variables)
    
    def deleteTagByName(self, name):
        tag_data = {}
        tag_data['id'] = self.getTagByName(name)
        if tag_data['id']:
            return deleteTag(tag_data)
        return False
    
    def deleteTagByID(self, id):
        tag_data = {}
        tag_data['id'] = id
        if tag_data['id']:
            return deleteTag(tag_data)
        return False

    def deleteTag(self, input_tag_data):  
        tag_data = {}
        tag_data["id"] = input_tag_data["id"]
        
        query = """
        mutation tagDestroy($input:TagDestroyInput!) {
          tagDestroy(input: $input)
        }
        """
        variables = {'input': tag_data}

        try:
            result = self.callGraphQL(query, variables)
            self.populateTags()
            return result["data"]["tagDestroy"]
        except Exception as e:
            logging.error("Error in deleting tag", exc_info=True)
            logging.error(variables)
    
    def updatePerformer(self, performer_data):
        update_data = performer_data
        if update_data.get('aliases', None):
            update_data['aliases'] = ', '.join(update_data['aliases'])
        
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
        variables = {'input': update_data}
        result = self.callGraphQL(query, variables)
        return result["data"]["performerUpdate"]

    def scrapePerformerFreeones(self, name):
        query = """
    {
        scrapeFreeones(performer_name: \""""+name+"""\")
        { url twitter instagram birthdate ethnicity country eye_color height measurements fake_tits career_length tattoos piercings aliases }

    }
    """
        result = self.callGraphQL(query)
        if keyIsSet(result['data'], ['scrapeFreeones', 'aliases']):
            result["data"]["scrapeFreeones"]['aliases'] = [alias.strip() for alias in result["data"]["scrapeFreeones"]['aliases'].split(',')]
            
        return result["data"]["scrapeFreeones"]
        
    def __getPerformerByName(self, name, check_aliases = False):  # A private function that allows disabling of checking for aliases
        
        for performer in self.performers:
            if performer['name'].lower() == name: # Check input name against performer name
                return performer
            elif check_aliases and keyIsSet(performer, "aliases"):  # Check input name against performer aliases
                performer_aliases_lower = listToLower(performer["aliases"])
                if name in performer_aliases_lower:
                    return performer
    
    def getPerformerByName(self, name, aliases = []):
        name = name.lower()
        input_aliases_lower = listToLower(aliases)
        
        result = self.__getPerformerByName(name, True)
        if result:  # This matches input name with existing name or alias 
            return result
        
        for input_alias in input_aliases_lower: # For each alias, recurse w/ name = alias, but disable alias to alias mapping
            result = self.__getPerformerByName(input_alias, False)
            if result:
                return result
        
        return None            

    def getStudioByName(self, name):
        if compact_studio_names:
            name = name.replace(' ','')
        for studio in self.studios:
            if studio['name'].lower().strip() == name.lower().strip():
                return studio
        return None
    
    def getTagByName(self, name, add_tag_if_missing = False):
        logging.debug("Getting tag id for tag \'"+name+"\'.")
        search_name = name.lower().replace('-', ' ').replace('(', '').replace(')', '').strip().replace(' ', '')
        for tag in self.tags:
            if search_name == tag['name'].lower().replace('-', ' ').replace('(', '').replace(')', '').strip().replace(' ', ''):
                logging.debug("Found the tag.  ID is "+tag['id'])
                return tag
        
        # Add the Tag to Stash
        if add_tag_if_missing:
            stash_tag = {}
            stash_tag["name"] = name
            print("Did not find " + name + " in Stash.  Adding Tag.")
            self.addTag(stash_tag)
            return self.getTagByName(name)

        return None
              
#Script-specific functions        
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
    if keyIsSet(metadataapi_performer, ["parent", "name"]): 
        stash_performer["name"] = metadataapi_performer["parent"]["name"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "birthday"]): 
        stash_performer["birthdate"] = metadataapi_performer["parent"]["extras"]["birthday"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "measurements"]): 
        stash_performer["measurements"] = metadataapi_performer["parent"]["extras"]["measurements"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "tattoos"]): 
        stash_performer["tattoos"] = metadataapi_performer["parent"]["extras"]["tattoos"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "piercings"]): 
        stash_performer["piercings"] = metadataapi_performer["parent"]["extras"]["piercings"]
    if keyIsSet(metadataapi_performer, ["parent", "aliases"]) and len(metadataapi_performer["parent"]["aliases"])>1: 
        stash_performer["aliases"] = metadataapi_performer["parent"]["aliases"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "gender"]):
        if metadataapi_performer["parent"]["extras"]["gender"] == "Male":
            stash_performer["gender"] = 'MALE'
        if metadataapi_performer["parent"]["extras"]["gender"] == "Female":
            stash_performer["gender"] = 'FEMALE'            
        if metadataapi_performer["parent"]["extras"]["gender"] == "Transgender Male":
            stash_performer["gender"] = 'TRANSGENDER_MALE'
        if metadataapi_performer["parent"]["extras"]["gender"] == "Transgender Female":
            stash_performer["gender"] = 'TRANSGENDER_FEMALE'
        if metadataapi_performer["parent"]["extras"]["gender"] == "Intersex":
            stash_performer["gender"] = 'INTERSEX'
    return stash_performer

def createStashStudioData(metadataapi_studio):  # Creates stash-compliant data from raw data provided by metadataapi
    stash_studio = {}
    if compact_studio_names:
        stash_studio["name"] = metadataapi_studio["name"].replace(' ', '')
    else:
        stash_studio["name"] = metadataapi_studio["name"]
    stash_studio["url"] = metadataapi_studio["url"]
    if metadataapi_studio["logo"] is not None and "default.png" not in metadataapi_studio["logo"]:
        image = requests.get(metadataapi_studio["logo"]).content
        image_b64 = base64.b64encode(image)
        stash_studio["image"] = image_b64.decode(ENCODING)

    return stash_studio

def getJpegImage(image_url):
    try:
        r = requests.get(image_url, stream=True)
        r.raw.decode_content = True # handle spurious Content-Encoding
        image = Image.open(r.raw)
        if image.format:
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image = buffered.getvalue()
            return image

    except Exception as e:
        print("Error Getting Image: "+str(e))

    return None    

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
    global my_stash
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
            if performer.get("aliases",None):
                for alias in performer["aliases"]:
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
    global metadataapi_error_count
    url = "https://metadataapi.net/api/scenes?parse="+urllib.parse.quote(query)    
    try:
        result = requests.get(url).json()["data"]
        metadataapi_error_count = 0
        return result
    except ValueError:
        print("Error communicating with MetadataAPI")        
        metadataapi_error_count = metadataapi_error_count + 1
        if metadataapi_error_count > 3:
            print("MetaDataAPI seems to be down.  Exiting.")
            sys.exit()
        
def manuallyDisambiguateMetadataAPIResults(scrape_query, scraped_data):
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

def areAliases(first_performer, second_performer):
    if first_performer == second_performer: #No need to conduct checks if they're the same
        return True
    
    global my_stash
    first_performer_aliases = [first_performer]
    second_performer_aliases = [second_performer]
    ##build aliases of both first/second performer
    #First performer
    result = my_stash.getPerformerByName(first_performer)
    if result and keyIsSet(result, "aliases"):
        first_performer_aliases =  list(set(first_performer_aliases + result["aliases"]))
    result = my_stash.scrapePerformerFreeones(first_performer)
    if result and keyIsSet(result, "aliases"):
        first_performer_aliases =  list(set(first_performer_aliases + result["aliases"]))
    #Second Performer
    result = my_stash.getPerformerByName(second_performer)
    if result and keyIsSet(result, "aliases"):
        second_performer_aliases =  list(set(second_performer_aliases + result["aliases"]))
    result = my_stash.scrapePerformerFreeones(second_performer)
    if result and keyIsSet(result, "aliases"):
        second_performer_aliases =  list(set(second_performer_aliases + result["aliases"]))        
    #check if one is an alias of another, but don't compare aliases
    if first_performer in second_performer_aliases or second_performer in first_performer_aliases:
        return True
    return False

def getQuery(scene):
    if parse_with_filename:
        try:
            if re.search(r'^[A-Z]:\\', scene['path']):  #If we have Windows-like paths
                parse_result = re.search(r'^[A-z]:\\((.+)\\)*(.+)\.(.+)$', scene['path']).group(2)
            else:  #Else assume Unix-like paths
                parse_result = re.search(r'^\/((.+)\/)*(.+)\.(.+)$', scene['path'])
            file_name = parse_result.group(3)
            dirs = parse_result.group(2).split("/")
        except Exception:
            print("Error when parsing scene path: "+scene['path'])
            return
        if clean_filename:
            file_name = scrubFileName(file_name)
        
        scrape_query = file_name
        #ADD DIRS TO QUERY
        for x in range(dirs_in_query):
            scrape_query = dirs[-1-x] +" "+scrape_query
    else:
        scrape_query = scene['title']
    return scrape_query

def updateSceneFromMetadataAPI(scene):
    try:
        scrape_query = ""
        tag_ids_to_add = []
        tags_to_add = []
        performer_names = []
        
        scrape_query = getQuery(scene)
        scene_data = createSceneUpdateFromSceneData(scene)  # Start with our current data as a template 

        print("Grabbing Data For: " + scrape_query)
        scraped_data = scrapeMetadataAPI(scrape_query)

        if scraped_data:  
            if ambiguous_tag: ambiguous_tag_id = my_stash.getTagByName(ambiguous_tag)['id']
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
            if scrape_tag: tags_to_add.append({'tag':scrape_tag})
            if set_tags and keyIsSet(scraped_scene, "tags"):
                tags_to_add = tags_to_add + scraped_scene["tags"]

            # Add performers to scene
            if set_performers and keyIsSet(scraped_scene, "performers"):
                scraped_performer_ids = []
                for scraped_performer in scraped_scene["performers"]:
                    performer_id = None
                    performer_name = ""
                    performer_aliases = []
                    unique_performer_metadataapi = False
                    
                    performer_name = scraped_performer['name'] 
                    stash_performer = my_stash.getPerformerByName(performer_name)
                    if not stash_performer: #If site name matches someone in Stash, proceed.  Otherwise...
                        if keyIsSet(scraped_performer, ['parent','name']) and areAliases(scraped_performer['name'], scraped_performer['parent']['name'] ): #"Parent" performer found at ThePornDB, and Parent performer seems to be a valid alias to site performer
                            performer_name = scraped_performer['parent']['name']
                            unique_performer_metadataapi = True
                            stash_performer = my_stash.getPerformerByName(performer_name, performer_aliases) #Adopt the parent name only if we can verify it's an alias of the site name.  If so, either tag w/ existing performer or add new performer when requirements are met.
                       
                    if stash_performer:  #If performer already exists
                        performer_id = stash_performer["id"]
                    # Add ambigous performer tag if we meet relevant requirements
                    elif  not unique_performer_metadataapi: 
                        if  tag_ambiguous_performers and (
                            not only_add_female_performers or (
                                keyIsSet(scraped_performer, ["extra", "gender"]) and 
                                scraped_performer["extra"]["gender"] != 'Male'
                                )
                            ): #Note the relaxed gender requirement for ambiguous performers
                            print(performer_name+" was not found in Stash. However, "+performer_name+" is not linked to a known (multi-site) performer at ThePornDB.  Skipping addition and tagging scene.")
                            tag_id = my_stash.getTagByName("ThePornDB Ambiguous Performer: "+performer_name, True)["id"]
                            scene_data["tag_ids"].append(tag_id)
                            if performer_name.lower() in scrape_query.lower():  #If the ambiguous performer is in the file name, put them in the title too.
                                performer_names.append(performer_name)
                    # Add performer if we meet relevant requirements
                    elif add_performers:
                        if  (
                            performer_name.lower() in scrape_query.lower() or  
                            scraped_performer['name'].lower() in scrape_query.lower() or 
                            not only_add_female_performers or (
                                keyIsSet(scraped_performer, ["parent", "extras", "gender"]) and 
                                scraped_performer["parent"]["extras"]["gender"] == 'Female'
                                )
                            ):
                            print("Did not find " + performer_name + " in Stash.  Adding performer.")
                            performer_id = my_stash.addPerformer(createStashPerformerData(scraped_performer))
                            performer_data = {}
                            if scrape_performers_freeones:
                                performer_data = my_stash.scrapePerformerFreeones(performer_name)
                                if not performer_data:
                                    performer_data = {}
                            performer_data["id"] = performer_id
                            performer_data["image"] = getPerformerImageB64(performer_name)
                            my_stash.updatePerformer(performer_data)

                    if performer_id != None:  # If we have a valid ID, add performer to Scene
                        scraped_performer_ids.append(performer_id)
                scene_data["performer_ids"] = list(set(scene_data["performer_ids"] + scraped_performer_ids))                              

            # Set Title
            if set_title: 
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

            #Set tag_ids for tags_to_add           
            for tag_dict in tags_to_add:
                tag_id = None
                tag_name = tag_dict['tag'].replace('-', ' ').replace('(', '').replace(')', '').strip().title()
                if add_tags:
                    tag_id = my_stash.getTagByName(tag_name, add_tag_if_missing = True)["id"]
                else:
                    stash_tag = my_stash.getTagByName(tag_name, add_tag_if_missing = False)
                    if stash_tag:
                        tag_id = stash_tag["id"] 
                    else:
                        tag_id = None
                if tag_id:  # If we have a valid ID, add tag to Scene
                    tag_ids_to_add.append(tag_id)
                else:
                    logging.debug("Tried to add tag \'"+tag_dict['tag']+"\' but failed to find ID in Stash.")
            scene_data["tag_ids"] = list(set(scene_data["tag_ids"] + tag_ids_to_add))
            
            logging.debug("Now updating scene with the following data:")
            logging.debug(scene_data)

            my_stash.updateSceneData(scene_data)
            print("Success")
        else:
            print("No data found for: [{}]".format(scrape_query))
    except Exception as e:
        logging.error("Exception encountered when scraping '"+scrape_query, exc_info=True)

#Globals
metadataapi_error_count = 0
my_stash = None
ENCODING = 'utf-8'

###############################################
# DEFAULT CONFIGURATION OPTIONS.  DO NOT EDIT #
###############################################
use_https = False # Set to false for HTTP
server_ip= "<IP ADDRESS>"
server_port = "<PORT>"
username=""
password=""

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
add_studio = False  
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set
add_performers = False 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)

#Other config options
parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
dirs_in_query = 0 # The number of directories up the path to be included in the query for a filename parse query.  For example, if the file  is at \performer\mysite\video.mp4 and dirs_in_query is 1, query would be "mysite video."  If set to two, query would be "performer mysite video", etc.
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = False #If true, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = False #If true, will try to grab an image from babepedia before the one from metadataapi
include_performers_in_title = True #If true, performers will be prepended to the title
clean_filename = True #If true, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
compact_studio_names = False # If true, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings = False # Set to true if your Stash uses SSL w/ a self-signed cert

def loadConfig():
    try:  # Try to load configuration.py values
        import configuration
        for key, value in vars(configuration).items():
            globals()[key]=value
        return True
    except ImportError:
        logging.error("No configuration found.  Double check your configuration.py file exists.")
        create_config = input("Create configuruation.py? (yes/no):")
        if create_config == 'y' or create_config == 'Y' or create_config =='Yes' or create_config =='yes':
            createConfig()
        else:
            logging.error("No configuration found.  Exiting.")
            sys.exit()
        
def createConfig():        
    server_ip = input("What's your Stash server's IP address? (no port please):")
    server_port = input("What's your Stash server's port?:")
    https_input = input("Does your Stash server use HTTPS? (yes/no):")
    use_https = False
    if https_input == 'y' or https_input == 'Y' or https_input =='Yes' or https_input =='yes':
        use_https = True
    username = input ("What's your Stash server's username? (Just press enter if you don't use one):")
    password = input ("What's your Stash server's username? (Just press enter if you don't use one):")

    f = open("configuration.py", "w")
    f.write("""
#Server configuration
use_https = {4} # Set to false for HTTP
server_ip= "{0}"
server_port = "{1}"
username="{2}"
password="{3}"

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
add_studio = False  
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set
add_performers = False 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)

#Other config options
parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
dirs_in_query = 0 # The number of directories up the path to be included in the query for a filename parse query.  For example, if the file  is at \performer\mysite\video.mp4 and dirs_in_query is 1, query would be "mysite video."  If set to two, query would be "performer mysite video", etc.
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = False #If true, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = False #If true, will try to grab an image from babepedia before the one from metadataapi
include_performers_in_title = True #If true, performers will be prepended to the title
clean_filename = True #If true, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
compact_studio_names = False # If true, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings=True # Set to true if your Stash uses SSL w/ a self-signed cert""".format(server_ip, server_port, username, password, use_https))
    f.close()
    print("Configuration file created.  All values are currently at defaults.  It is highly recommended that you edit the configuration.py to your liking.  Otherwise, just re-run the script to use the defaults.")
    sys.exit()

def main():
    logging.basicConfig(level=logging.DEBUG)
    try:
        global my_stash
        metadataapi_error_count = 0
        loadConfig()

        if use_https:
            server = 'https://'+str(server_ip)+':'+str(server_port)+'/graphql'
        else:
            server = 'http://'+str(server_ip)+':'+str(server_port)+'/graphql'
        
        my_stash = stash_interface(server, username, password, ignore_ssl_warnings)

        ambiguous_tag_id = my_stash.getTagByName(ambiguous_tag, True)["id"]
        scrape_tag_id  = my_stash.getTagByName(scrape_tag, True)["id"]
        
        query=""
        if len(sys.argv) > 1:
            query = "\""+sys.argv[1]+"\""
        
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
        logging.error("Something went wrong.  This probably means your configuration.py is invalid somehow.  If all else fails, delete or rename your configuration.py and the script will try to create a new one.", exc_info=True)

if __name__ == "__main__":
    main()
