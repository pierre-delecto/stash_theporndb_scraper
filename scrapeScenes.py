import os
import requests
import json
import re
import urllib
import sys
import base64
import math
import logging
import argparse
import traceback
from datetime import datetime
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
    http_auth_type = ""
    auth_token = ""
    min_buildtime = datetime(2020, 6, 22) 
    
    headers = {
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Connection": "keep-alive",
        "DNT": "1"
        }

    def __init__(self, server_url, user = "", pword = "", ignore_ssl = "", debug = False):
        self.server = server_url
        self.username = user
        self.password = pword
        self.ignore_ssl_warnings = ignore_ssl
        if ignore_ssl: requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        self.debug_mode = debug
        self.setAuth()
        self.checkVersion()
        self.populatePerformers()
        self.populateTags()
        self.populateStudios()

    def setAuth(self):
        r = requests.get(self.server+"/playground", verify= not self.ignore_ssl_warnings)
        if len(r.history)>0 and r.history[-1].status_code == 302:
            self.http_auth_type="jwt"
            self.jwtAuth()
        elif r.status_code == 200:
            self.http_auth_type="none"
        else:
            self.http_auth_type="basic"
        return

    def jwtAuth(self):
        response = requests.post(self.server+"/login", data = {'username':self.username, 'password':self.password}, verify= not self.ignore_ssl_warnings)
        self.auth_token=response.cookies.get('session',None)
        if not self.auth_token:
            logging.error("Error authenticating with Stash.  Double check your IP, Port, Username, and Password", exc_info=self.debug_mode)
            sys.exit()
    #GraphQL Functions    
    def callGraphQL(self, query, variables = None):
        return self.__callGraphQL(query, variables)

    def __callGraphQL(self, query, variables, retry = True):
        graphql_server = self.server+"/graphql"
        json = {}
        json['query'] = query
        if variables:
            json['variables'] = variables
        
        try:
            if self.http_auth_type == "basic":
                response = requests.post(graphql_server, json=json, headers=self.headers, auth=(self.username, self.password), verify= not self.ignore_ssl_warnings)
            elif self.http_auth_type == "jwt":
                response = requests.post(graphql_server, json=json, headers=self.headers, cookies={'session':self.auth_token}, verify= not self.ignore_ssl_warnings)
            else:
                response = requests.post(graphql_server, json=json, headers=self.headers, verify= not self.ignore_ssl_warnings)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("error", None):
                    for error in result["error"]["errors"]:
                        logging.error("GraphQL error:  {}".format(error), exc_info=self.debug_mode)
                if result.get("data", None):
                    return result
            elif retry and response.status_code == 401 and self.http_auth_type == "jwt":
                self.jwtAuth()
                return self.__callGraphQL(query, variables, False)
            else:
                logging.error("GraphQL query failed to run by returning code of {}. Query: {}.  Variables: {}".format(response.status_code, query, variables), exc_info=self.debug_mode)
                raise Exception("GraphQL error")
        except requests.exceptions.SSLError:
            proceed = input("Caught certificate error trying to talk to Stash. Add ignore_ssl_warnings=True to your configuration.py to ignore permanently. Ignore for now? (yes/no):")
            if proceed == 'y' or proceed == 'Y' or proceed =='Yes' or proceed =='yes':
                self.ignore_ssl_warnings =True
                requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
                return self.callGraphQL(query, variables)
            else:
                print("Exiting.")
                sys.exit()

    def checkVersion(self):
        query = """
    {
    version{
        version
        build_time
        }
    }
    """
        result = self.callGraphQL(query)
        self.version_buildtime = datetime.strptime(result["data"]["version"]["build_time"], '%Y-%m-%d %H:%M:%S')
        if self.version_buildtime < stash_interface.min_buildtime:
            logging.error("Your Stash version appears too low to use this script.  Please upgrade to the latest \"development\" build and try again.", exc_info=self.debug_mode)
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
        max_scenes = kwargs.get("max_scenes", None)
        accepted_variables = {'filter':'FindFilterType!','scene_filter': 'SceneFilterType!','scene_ids':'[Int!]'}

        variables['filter'] = {} #Add filter to support pages, if necessary
                
        #Add accepted variables to our passsed variables
        for index, (accepted_variable, variable_type) in enumerate(accepted_variables.items()):
            if accepted_variable in kwargs:
                variables[accepted_variable] = kwargs[accepted_variable]

        #Set page and per_page, if not set
        variables['filter'] = variables.get('filter', {})
        variables['filter']['page'] = variables['filter'].get('page', 1)
        if max_scenes:
            variables['filter']['per_page'] = variables['filter'].get('per_page',  min(100, max_scenes))
        else:
            variables['filter']['per_page'] = variables['filter'].get('per_page',  100)
            
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
                  details
                  url
                  date
                  rating
                  path
                  studio {
                    id
                    name
                    }
                  gallery
                    {
                        id
                    }
                  movies
                    {
                        movie 
                        {
                            id
                        }
                    scene_index
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
            if not max_scenes: max_scenes = result["data"]["findScenes"]["count"]
            total_pages = math.ceil(max_scenes / variables['filter']['per_page'])
            print("Getting Stash Scenes Page: "+str(variables['filter']['page'])+" of "+str(total_pages))
            if (variables['filter']['page'] < total_pages and len(stashScenes)<max_scenes):  #If we're not at the last page or max_scenes, recurse with page +1 
                variables['filter']['page'] = variables['filter']['page']+1
                stashScenes = stashScenes+self.findScenes(**variables)

        except:
            logging.error("Unexpected error getting stash scene:", exc_info=self.debug_mode)
            
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
            logging.error("Error in adding performer", exc_info=self.debug_mode)
            logging.error(variables)
            logging.error(result)

    def getPerformerImage(self, url):  #UNTESTED
        if self.http_auth_type == "basic":
            return base64.b64encode(requests.get(url,proxies=config.proxies, auth=requests.auth.HTTPBasicAuth(self.username, self.password), 
                                verify= not self.ignore_ssl_warnings).content)
        elif self.http_auth_type == "jwt":
            return base64.b64encode(requests.get(url,proxies=config.proxies, headers=self.headers, cookies={'session':self.auth_token}, verify= not self.ignore_ssl_warnings).content)
        else:
            return base64.b64encode(requests.get(url,proxies=config.proxies, verify= not self.ignore_ssl_warnings).content)        
        
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
            logging.error("Error in adding studio:", exc_info=self.debug_mode)
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
            logging.error("Error in adding tags", exc_info=self.debug_mode)
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
            logging.error("Error in deleting tag", exc_info=self.debug_mode)
            logging.error(variables)
    
    def deletePerformer(self, input_data):  
        performer_data = {}
        performer_data["id"] = input_data["id"]
        
        query = """
        mutation performerDestroy($input:PerformerDestroyInput!) {
          performerDestroy(input: $input)
        }
        """
        variables = {'input': performer_data}

        try:
            result = self.callGraphQL(query, variables)
            self.populateTags()
            return result["data"]["performerDestroy"]
        except Exception as e:
            logging.error("Error in deleting performer", exc_info=self.debug_mode)
            logging.error(variables)
    
    def deleteScene(self, input_data, delete_file = False):  
        scene_data = {}
        scene_data["id"] = input_data["id"]
        scene_data['delete_file']=delete_file
        scene_data['delete_generated']=True
        
        query = """
        mutation sceneDestroy($input:SceneDestroyInput!) {
          sceneDestroy(input: $input)
        }
        """
        variables = {'input': scene_data}

        try:
            result = self.callGraphQL(query, variables)
            self.populateTags()
            return result["data"]["sceneDestroy"]
        except Exception as e:
            logging.error("Error in deleting scene", exc_info=self.debug_mode)
            logging.error(variables)

    def updatePerformer(self, performer_data):
        update_data = performer_data
        if update_data.get('aliases', None):
            update_data['aliases'] = ', '.join(update_data['aliases'])
        if update_data.get('image_path', None):
            update_data.pop('image_path',None)

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
        scrapePerformerList(scraper_id:"builtin_freeones", query:\""""+name+"""\")
        { name url twitter instagram birthdate ethnicity country eye_color height measurements fake_tits career_length tattoos piercings aliases }
        }"""
        result = self.callGraphQL(query)
        try:
            if len(result['data']["scrapePerformerList"])!=0:
                query = """   
                query ScrapePerformer($scraped_performer: ScrapedPerformerInput!){
                    scrapePerformer(scraper_id:"builtin_freeones", scraped_performer: $scraped_performer)
                    { url twitter instagram birthdate ethnicity country eye_color height measurements fake_tits career_length tattoos piercings aliases }
                }"""
                variables = {'scraped_performer': result['data']['scrapePerformerList'][0]}
                result = self.callGraphQL(query, variables)
                if keyIsSet(result['data'], ['scrapePerformer', 'aliases']):
                    result["data"]["scrapePerformer"]['aliases'] = [alias.strip() for alias in result["data"]["scrapePerformer"]['aliases'].split(',')]
                return result["data"]["scrapePerformer"]
            else:
                return None
        except Exception as e:
            logging.error("Error in scraping Freeones", exc_info=self.debug_mode)
            logging.error(variables)
        
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

    def createSceneUpdateData(self, scene_data):  #Scene data returned from stash has a different format than what is accepted by the UpdateScene graphQL query.  This converts one format to another
        scene_update_data = {}
        if keyIsSet(scene_data, "id"): scene_update_data["id"] = scene_data["id"]
        if keyIsSet(scene_data, "title"): scene_update_data["title"] = scene_data["title"]
        if keyIsSet(scene_data, "details"): scene_update_data["details"] = scene_data["details"]
        if keyIsSet(scene_data, "url"): scene_update_data["url"] = scene_data["url"]
        if keyIsSet(scene_data, "date"): scene_update_data["date"] = scene_data["date"]
        if keyIsSet(scene_data, "rating"): scene_update_data["rating"] = scene_data["rating"]
        if keyIsSet(scene_data, "studio"): scene_update_data["studio_id"] = scene_data["studio"]["id"]
        if keyIsSet(scene_data, "gallery"): scene_update_data["gallery_id"] = scene_data["gallery"]["id"]
        if keyIsSet(scene_data, "movies"):
            scene_update_data["movies"] = []
            for entry in scene_data["movies"]:
                update_date_movie = {}
                update_date_movie["movie_id"]=entry["movie"]["id"]
                update_date_movie["scene_index"]=entry["scene_index"]
                scene_update_data["movies"].append(update_date_movie)
        else:
            scene_update_data["movies"] = []
        
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
              
#Script-specific functions        
def createStashPerformerData(tpbd_performer): #Creates stash-compliant data from raw data provided by ThePornDB
    stash_performer = {}
    if keyIsSet(tpbd_performer, ["parent", "name"]): 
        stash_performer["name"] = tpbd_performer["parent"]["name"]
    if keyIsSet(tpbd_performer, ["parent", "extras", "birthday"]): 
        stash_performer["birthdate"] = tpbd_performer["parent"]["extras"]["birthday"]
    if keyIsSet(tpbd_performer, ["parent", "extras", "measurements"]): 
        stash_performer["measurements"] = tpbd_performer["parent"]["extras"]["measurements"]
    if keyIsSet(tpbd_performer, ["parent", "extras", "tattoos"]): 
        stash_performer["tattoos"] = tpbd_performer["parent"]["extras"]["tattoos"]
    if keyIsSet(tpbd_performer, ["parent", "extras", "piercings"]): 
        stash_performer["piercings"] = tpbd_performer["parent"]["extras"]["piercings"]
    if keyIsSet(tpbd_performer, ["parent", "aliases"]) and len(tpbd_performer["parent"]["aliases"])>1: 
        stash_performer["aliases"] = tpbd_performer["parent"]["aliases"]
    if keyIsSet(tpbd_performer, ["parent", "extras", "gender"]):
        if tpbd_performer["parent"]["extras"]["gender"] == "Male":
            stash_performer["gender"] = 'MALE'
        if tpbd_performer["parent"]["extras"]["gender"] == "Female":
            stash_performer["gender"] = 'FEMALE'            
        if tpbd_performer["parent"]["extras"]["gender"] == "Transgender Male":
            stash_performer["gender"] = 'TRANSGENDER_MALE'
        if tpbd_performer["parent"]["extras"]["gender"] == "Transgender Female":
            stash_performer["gender"] = 'TRANSGENDER_FEMALE'
        if tpbd_performer["parent"]["extras"]["gender"] == "Intersex":
            stash_performer["gender"] = 'INTERSEX'
    return stash_performer

def createStashStudioData(tpbd_studio):  # Creates stash-compliant data from raw data provided by TPBD
    stash_studio = {}
    if config.compact_studio_names:
        stash_studio["name"] = tpbd_studio["name"].replace(' ', '')
    else:
        stash_studio["name"] = tpbd_studio["name"]
    stash_studio["url"] = tpbd_studio["url"]
    if tpbd_studio["logo"] is not None and "default.png" not in tpbd_studio["logo"]:
        image = requests.get(tpbd_studio["logo"],proxies=config.proxies).content
        image_b64 = base64.b64encode(image)
        stash_studio["image"] = image_b64.decode(ENCODING)

    return stash_studio

def getJpegImage(image_url):
    try:
        r = requests.get(image_url, stream=True,proxies=config.proxies)
        r.raw.decode_content = True # handle spurious Content-Encoding
        image = Image.open(r.raw)
        if image.format:
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image = buffered.getvalue()
            return image

    except Exception as e:
        logging.error("Error Getting Image at URL:"+image_url, exc_info=config.debug_mode)

    return None    

def getBabepediaImage(name):
    url = "https://www.babepedia.com/pics/"+urllib.parse.quote(name)+".jpg"
    if requests.get(url,proxies=config.proxies):
        return getJpegImage(url)
    return None

def getTpbdImage(name):
    url = "https://metadataapi.net/api/performers?q="+urllib.parse.quote(name)
    if len(requests.get(url,proxies=config.proxies).json()["data"])==1: #If we only have 1 hit
        raw_data = requests.get(url,proxies=config.proxies).json()["data"][0]
        image_url = raw_data["image"]
        if not "default.png" in image_url:
            image = getJpegImage(image_url)
            return image
    return None

def getPerformerImageB64(name):  #Searches Babepedia and TPBD for a performer image, returns it as a base64 encoding
    global my_stash
    global config
    try:
        performer = my_stash.getPerformerByName(name)

        #Try Babepedia if flag is set    
        if config.get_images_babepedia:
            # Try Babepedia
            image = getBabepediaImage(name)
            if image:
                image_b64 = base64.b64encode(image)
                stringbase = str(image_b64)
                return image_b64.decode(ENCODING)

            # Try aliases at Babepedia
            if performer and performer.get("aliases",None):
                for alias in performer["aliases"]:
                    image = getBabepediaImage(alias)
                    if image:
                        image_b64 = base64.b64encode(image)
                        stringbase = str(image_b64)
                        return image_b64.decode(ENCODING)
                        
        # Try thePornDB
        image = getTpbdImage(name)
        if image:
            image_b64 = base64.b64encode(image)
            stringbase = str(image_b64)
            return image_b64.decode(ENCODING)
        
        return None
    except Exception as e:
        logging.error("Error Getting Performer Image", exc_info=config.debug_mode)


def getPerformer(name):
    global tpbd_error_count
    search_url = "https://metadataapi.net/api/performers?q="+urllib.parse.quote(name)
    data_url_prefix = "https://metadataapi.net/api/performers/"
    try:
        result = requests.get(search_url,proxies=config.proxies).json()
        tpbd_error_count = 0
        if  next(iter(result.get("data", [{}])), {}).get("id", None):
            performer_id = result["data"][0]["id"]
            return requests.get(data_url_prefix+performer_id,proxies=config.proxies).json()["data"]
        else:
            return None
    except ValueError:
        logging.error("Error communicating with ThePornDB")        
        tpbd_error_count = tpbd_error_count + 1
        if tpbd_error_count > 3:
            logging.error("ThePornDB seems to be down.  Exiting.")
            sys.exit()
           

def sceneQuery(query, parse_function = True):  # Scrapes ThePornDB based on query.  Returns an array of scenes as results, or None
    global tpbd_error_count
    if parse_function:
        url = "https://metadataapi.net/api/scenes?parse="+urllib.parse.quote(query)    
    else:
        url = "https://metadataapi.net/api/scenes?q="+urllib.parse.quote(query)
    try:
        result = requests.get(url,proxies=config.proxies).json()["data"]
        tpbd_error_count = 0
        return result
    except ValueError:
        logging.error("Error communicating with ThePornDB")        
        tpbd_error_count = tpbd_error_count + 1
        if tpbd_error_count > 3:
            logging.error("ThePornDB seems to be down.  Exiting.")
            sys.exit()
        
def manuallyDisambiguateResults(scraped_data):
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

def areAliases(first_performer, second_performer, site = None):
    if first_performer.lower() == second_performer.lower(): #No need to conduct checks if they're the same
        return True
    
    global my_stash
    global known_aliases
    global config
    if config.compact_studio_names and site:
        site = site.replace(' ','')

    first_performer_aliases = [first_performer]
    if known_aliases.get(first_performer, None):
        first_performer_aliases = first_performer_aliases + known_aliases.get(first_performer, None)
    second_performer_aliases = [second_performer]
    if known_aliases.get(second_performer, None):
        second_performer_aliases = second_performer_aliases + known_aliases.get(second_performer, None)
    ##build aliases of both first/second performer
    #First performer
    result = my_stash.getPerformerByName(first_performer)
    if result and keyIsSet(result, "aliases"):  #Add Stash Aliases
        first_performer_aliases =  list(set(first_performer_aliases + result["aliases"]))
    result = my_stash.scrapePerformerFreeones(first_performer)
    if result and keyIsSet(result, "aliases"):#Add Freeones Aliases
        first_performer_aliases =  list(set(first_performer_aliases + result["aliases"]))
    result = getPerformer(first_performer)
    if result and keyIsSet(result, "aliases"):#Add TPBD Aliases
        first_performer_aliases =  list(set(first_performer_aliases + result["aliases"]))
    #Second Performer
    result = my_stash.getPerformerByName(second_performer)
    if result and keyIsSet(result, "aliases"):#Add Stash Aliases
        second_performer_aliases =  list(set(second_performer_aliases + result["aliases"]))
    result = my_stash.scrapePerformerFreeones(second_performer)
    if result and keyIsSet(result, "aliases"):#Add Freeones Aliases
        second_performer_aliases =  list(set(second_performer_aliases + result["aliases"]))
    result = getPerformer(second_performer)
    if result and keyIsSet(result, "aliases"):#Add TPBD Aliases
        second_performer_aliases =  list(set(second_performer_aliases + result["aliases"]))        
    #check if one is an alias of another, but don't compare aliases
    if first_performer in second_performer_aliases or second_performer in first_performer_aliases:
        return True
    first_performer = first_performer+" ("+site+")"
    second_performer = second_performer+" ("+site+")"
    if first_performer in second_performer_aliases or second_performer in first_performer_aliases:
        return True
    return False

def getQuery(scene):
    global config
    if config.parse_with_filename:
        try:
            if re.search(r'^[A-z]:\\', scene['path']):  #If we have Windows-like paths
                parse_result = re.search(r'^[A-z]:\\((.+)\\)*(.+)\.(.+)$', scene['path'])
                dirs = parse_result.group(2).split("\\")
            else:  #Else assume Unix-like paths
                parse_result = re.search(r'^\/((.+)\/)*(.+)\.(.+)$', scene['path'])
                dirs = parse_result.group(2).split("/")
            file_name = parse_result.group(3)
        except Exception:
            logging.error("Error when parsing scene path: "+scene['path'], exc_info=config.debug_mode)
            return
        if config.clean_filename:
            file_name = scrubFileName(file_name)
        
        scrape_query = file_name
        #ADD DIRS TO QUERY
        for x in range(min(config.dirs_in_query, len(dirs))):
            scrape_query = dirs.pop()+" "+scrape_query
    else:
        scrape_query = scene['title']
    return '' if scrape_query is None else str(scrape_query)

def scrapeScene(scene):
    global my_stash
    global config
    try:
        scene_data = my_stash.createSceneUpdateData(scene)  # Start with our current data as a template
        scrape_query = ""
        scrape_query = getQuery(scene)
        scraped_data = sceneQuery(scrape_query)

        if not scraped_data:
            scraped_data = sceneQuery(scrape_query, False)

        if len(scraped_data)>1 and not config.parse_with_filename: 
            #Try to add studio
            if keyIsSet(scene, "studio"):
                scrape_query = scrape_query + " " + scene['studio']['name']
                new_data = sceneQuery(scrape_query)
                if new_data: scraped_data = new_data
            
        if len(scraped_data)>1 and not config.parse_with_filename:    
            #Try to and date
            if keyIsSet(scene_data, "date"):
                scrape_query = scrape_query + " " + scene_data['date']
                new_data = sceneQuery(scrape_query)
                if new_data: scraped_data = new_data
            
        if len(scraped_data) > 1:  # Fix a bug where multiple ThePornDB results are the same scene
            scene_iter = iter(scraped_data)
            next(scene_iter)
            for scraped_scene in scene_iter:
                if scraped_scene['title'] == scraped_data[0]['title']:
                    scraped_data.remove(scraped_scene)
        
        print("Grabbing Data For: " + scrape_query)

        if len(scraped_data) > 1 and config.manual_disambiguate: # Manual disambiguate
            scraped_data = manuallyDisambiguateResults(scraped_data)
        
        if len(scraped_data) > 1 and config.auto_disambiguate:  #Auto disambiguate
            print("Auto disambiguating...")
            print("Matched "+scrape_query+" with "+scraped_data[0]['title'])
            new_data = []
            new_data.append(scraped_data[0])
            scraped_data = new_data
    
        if len(scraped_data) > 1:  # Handling of ambiguous scenes
            print("Ambiguous data found for: [{}], skipping".format(scrape_query))
            if config.ambiguous_tag:    
                scene_data["tag_ids"].append(my_stash.getTagByName(config.ambiguous_tag)['id'])
                my_stash.updateSceneData(scene_data)
            return

        if scraped_data:
            scraped_scene = scraped_data[0]
            # If we got new data, update our current data with the new
            updateSceneFromScrape(scene_data, scraped_scene, scene['path'])
            print("Success")
        else:
            print("No data found for: [{}]".format(scrape_query))
    except Exception as e:
        logging.error("Exception encountered when scraping '"+scrape_query, exc_info=config.debug_mode)

def manConfirmAlias(scraped_performer, site): #Returns scraped_performer if response is positive, None otherwise.  If Always or Site are selected, scraped_performer is updated to include a new alias
    global known_aliases
    global config
    if config.compact_studio_names:
        site = site.replace(' ','')
    response = input("Found "+scraped_performer['name']+" as a performer in scene, which TPBD indicates is an alias of "+scraped_performer['parent']['name']+".  Should we trust that? (Y)es / (N)o / (A)lways / Always for this (S)ite:")
    if response == 'y' or response == 'Y' or response =='Yes' or response =='yes':
        return scraped_performer
    elif response == 'a' or response == 'A' or response =='always' or response =='Always':
        #Update our global var
        known_alias_entry = known_aliases.get(scraped_performer['parent']['name'], None)
        if known_alias_entry:
            known_aliases[scraped_performer['parent']['name']].append(scraped_performer['name'])
        else:
            known_aliases[scraped_performer['parent']['name']] = [scraped_performer['name']]
        if keyIsSet(scraped_performer, ["parent", "aliases"]):
            scraped_performer["parent"]['aliases'].append(scraped_performer['name'])
        else:
            scraped_performer["parent"]['aliases'] = [scraped_performer['name']]
        return scraped_performer
    elif response == 's' or response == 'S' or response =='Site' or response =='site':
        #Update our global var
        known_alias_entry = known_aliases.get(scraped_performer['parent']['name'], None)
        if known_alias_entry:
            known_aliases[scraped_performer['parent']['name']].append(scraped_performer['name']+" ("+site+")")
        else:
            known_aliases[scraped_performer['parent']['name']] = [scraped_performer['name']+" ("+site+")"]
        if keyIsSet(scraped_performer, ["parent", "aliases"]):
            scraped_performer["parent"]['aliases'].append(scraped_performer['name']+" ("+site+")")
        else:
            scraped_performer["parent"]['aliases'] = [scraped_performer['name']+" ("+site+")"]
        return scraped_performer
    return None

def addPerformer(scraped_performer):  #Adds performer using TPDB data, returns ID of performer
    global config
    stash_performer_data = createStashPerformerData(scraped_performer)
    if config.scrape_performers_freeones:
        freeones_data = my_stash.scrapePerformerFreeones(scraped_performer['parent']['name'])
        if freeones_data: 
            if keyIsSet(freeones_data, "aliases") and keyIsSet(scraped_performer, ["parent","aliases"]) :
                freeones_data['aliases'] = list(set(freeones_data['aliases'] + scraped_performer["parent"]['aliases']))
            stash_performer_data.update(freeones_data)

    stash_performer_data["image"] = getPerformerImageB64(scraped_performer['parent']['name'])
    return my_stash.addPerformer(stash_performer_data)

def updateSceneFromScrape(scene_data, scraped_scene, path = ""):
    global config
    tag_ids_to_add = []
    tags_to_add = []
    performer_names = []
    try:
        if config.ambiguous_tag: 
            ambiguous_tag_id = my_stash.getTagByName(config.ambiguous_tag)['id']
            if ambiguous_tag_id in scene_data["tag_ids"]: 
                scene_data["tag_ids"].remove(ambiguous_tag_id) #Remove ambiguous tag; it will be readded later if the scene is still ambiguous
        if my_stash.getTagByName(config.unconfirmed_alias)["id"] in scene_data["tag_ids"]: 
            scene_data["tag_ids"].remove(my_stash.getTagByName(config.unconfirmed_alias)["id"]) #Remove ambiguous tag; it will be readded later if the scene is still ambiguous

        if config.set_details: scene_data["details"] = scraped_scene["description"] #Add details
        if config.set_date: scene_data["date"] = scraped_scene["date"]  #Add date
        if config.set_url: scene_data["url"] = scraped_scene["url"]  #Add URL
        if config.set_cover_image and keyIsSet(scraped_scene, ["background","small"]) and "default.png" not in scraped_scene["background"]['small']:  #Add cover_image 
            cover_image = getJpegImage(scraped_scene["background"]['small'])
            if cover_image:
                image_b64 = base64.b64encode(cover_image)
                stringbase = str(image_b64)
                scene_data["cover_image"] = image_b64.decode(ENCODING)

        # Add Studio to the scene
        if config.set_studio and keyIsSet(scraped_scene, "site"):
            studio_id = None
            scraped_studio = scraped_scene['site']
            if config.compact_studio_names:
                scraped_studio['name'] = scraped_studio['name'].replace(' ','')
            stash_studio = my_stash.getStudioByName(scraped_studio['name'])
            if stash_studio:
                studio_id = stash_studio["id"]
            elif config.add_studio:
                # Add the Studio to Stash
                print("Did not find " + scraped_studio['name'] + " in Stash.  Adding Studio.")
                studio_id = my_stash.addStudio((createStashStudioData(scraped_studio)))
            if studio_id != None:  # If we have a valid ID, add studio to Scene
                scene_data["studio_id"] = studio_id
                
        # Add Tags to the scene
        if config.scrape_tag: tags_to_add.append({'tag':config.scrape_tag})
        if config.set_tags and keyIsSet(scraped_scene, "tags"):
            tags_to_add = tags_to_add + scraped_scene["tags"]

        # Add performers to scene
        if config.set_performers and keyIsSet(scraped_scene, "performers"):
            scraped_performer_ids = []
            for scraped_performer in scraped_scene["performers"]:
                not_female = False

                if keyIsSet(scraped_performer, ["parent", "extras"]) and (not keyIsSet(scraped_performer, ["parent", "extras", "gender"]) or scraped_performer["parent"]["extras"]["gender"] != 'Female'):
                    not_female = True

                if (not keyIsSet(scraped_performer, ["parent", "extras", "gender"]) and 
                        keyIsSet(scraped_performer, ["extra", "gender"]) and 
                        scraped_performer["extra"]["gender"] == 'Male'):
                    not_female = True
                
                if  (config.only_add_female_performers and 
                    not scraped_performer['name'] .lower() in path.lower() and
                    not_female):
                    continue # End current loop on male performers not in path
                
                performer_id = None
                performer_name = scraped_performer['name'] 
                stash_performer = my_stash.getPerformerByName(performer_name)
                add_this_performer = False
                if stash_performer:  
                    performer_id = stash_performer["id"] #If performer already exists, use that
                    performer_names.append(performer_name)  #Add to list of performers in scene
                elif keyIsSet(scraped_performer, ['parent','name']): #If site name does not match someone in Stash and TPBD has a linked parent
                    if  (  #Test for when we should automatically accept the parent name
                        areAliases(scraped_performer['name'], scraped_performer['parent']['name'], scraped_scene['site']['name'].replace(' ','') if config.compact_studio_names else scraped_scene['site']['name']) or #Parent performer seems to be a valid alias to site performer
                        " " not in scraped_performer['name'] or #Single name, so we just trust TPBD
                        config.trust_tpbd_aliases #Flag says to just trust TPBD
                    ):  
                        performer_name = scraped_performer['parent']['name'] #Adopt the parent name
                        stash_performer = my_stash.getPerformerByName(performer_name) 
                        if stash_performer:  
                            performer_id = stash_performer["id"] #If performer already exists, use that
                            performer_names.append(performer_name)  #Add to list of performers in scene
                        else:
                            add_this_performer = True
                    else: #We can't automatically trust the parent name.  Ask for manual confirmation if flag is set.
                        if config.confirm_questionable_aliases:
                            confirmed_performer =  manConfirmAlias(scraped_performer, scraped_scene['site']["name"])  
                            if confirmed_performer:
                                performer_name = scraped_performer['parent']['name'] #Adopt the parent name
                                stash_performer = my_stash.getPerformerByName(performer_name) 
                                if stash_performer:  
                                    performer_id = stash_performer["id"] #If performer already exists, use that
                                    performer_names.append(performer_name)  #Add to list of performers in scene
                                    stash_performer.update(createStashPerformerData(confirmed_performer))
                                    my_stash.updatePerformer(stash_performer) ##Update the performer to capture new aliases if needed
                                else:
                                    add_this_performer = True
                        else:
                            print("Found "+scraped_performer['name']+" in scene, which TPBD says is an alias of "+scraped_performer['parent']['name']+".  However, that couldn't be verified, so skipping addition and tagging scene.  To overwrite, manually add the performer and alias in stash, or set trust_tpbd_aliases or confirm_questionable_aliases to True in your configuration.py")
                            tag_id = my_stash.getTagByName("ThePornDB Unconfirmed Alias", True)["id"]
                            scene_data["tag_ids"].append(tag_id)
                            if performer_name.lower() in path.lower():  #If the ambiguous performer is in the file name, put them in the title too.
                                performer_names.append(performer_name)
                    
                # Add ambigous performer tag if we meet relevant requirements
                if  ( not stash_performer and #We don't have a match so far
                      not keyIsSet(scraped_performer, ['parent','name']) and #No TPBD parent
                      config.tag_ambiguous_performers  #Config says tag no parent
                    ):
                    print(performer_name+" was not found in Stash. However, "+performer_name+" is not linked to a known (multi-site) performer at ThePornDB.  Skipping addition and tagging scene.")
                    tag_id = my_stash.getTagByName("ThePornDB Ambiguous Performer: "+performer_name, True)["id"]
                    scene_data["tag_ids"].append(tag_id)
                    if performer_name.lower() in path.lower():  #If the ambiguous performer is in the file name, put them in the title too.
                        performer_names.append(performer_name)

                    
                # Add performer if we meet relevant requirements
                if add_this_performer and config.add_performers:
                    print("Did not find " + performer_name + " in Stash.  Adding performer.")
                    performer_id = addPerformer(scraped_performer)
                    performer_names.append(performer_name)

                if performer_id:  # If we have a valid ID, add performer to Scene
                    scraped_performer_ids.append(performer_id)
            scene_data["performer_ids"] = list(set(scene_data["performer_ids"] + scraped_performer_ids))                              

        # Set Title
        if config.set_title: 
            title_prefix = ""
            if config.include_performers_in_title:
                if len(performer_names) > 2:
                    title_prefix = "{}, and {} ".format(", ".join(performer_names[:-1]), performer_names[-1])
                elif len(performer_names) == 2:
                    title_prefix = performer_names[0] + " and " + performer_names[1] + " "
                elif len(performer_names) == 1:
                    title_prefix = performer_names[0] + " "
                for name in performer_names:
                    scraped_scene["title"] = lreplace(name, '', scraped_scene["title"]).strip()
            scene_data["title"] = str(title_prefix + scraped_scene["title"]).strip()

        #Set tag_ids for tags_to_add           
        for tag_dict in tags_to_add:
            tag_id = None
            tag_name = tag_dict['tag'].replace('-', ' ').replace('(', '').replace(')', '').strip().title()
            if config.add_tags:
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
    except Exception as e:
        logging.error("Scrape succeeded, but update failed.", exc_info=config.debug_mode)

class config_class:
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
    verify_aliases_only = False # Set to True to scrape only scenes that were skipped due to unconfirmed aliases 
    rescrape_scenes= False # If False, script will not rescrape scenes previously scraped successfully.  Must set scrape_tag for this to work
    debug_mode = True

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
    add_studio = False  
    add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set
    add_performers = False 

    #Disambiguation options
    #The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
    auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
    manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
    ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
    tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)
    trust_tpbd_aliases = True #If true, when TPBD lists an alias that we can't verify, just trust TBPD to be correct.  May lead to incorrect tagging
    confirm_questionable_aliases = True #If True, when TPBD lists an alias that we can't verify, manually prompt for config

    #Other config options
    parse_with_filename = True # If true, will query ThePornDB based on file name, rather than title, studio, and date
    dirs_in_query = 0 # The number of directories up the path to be included in the query for a filename parse query.  For example, if the file  is at \performer\mysite\video.mp4 and dirs_in_query is 1, query would be "mysite video."  If set to two, query would be "performer mysite video", etc.
    only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
    scrape_performers_freeones = False #If true, will try to scrape newly added performers with the freeones scraper
    get_images_babepedia = False #If true, will try to grab an image from babepedia before the one from ThePornDB
    include_performers_in_title = True #If true, performers will be prepended to the title
    clean_filename = True #If true, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
    compact_studio_names = False # If true, this will remove spaces from studio names added from ThePornDB
    ignore_ssl_warnings = False # Set to true if your Stash uses SSL w/ a self-signed cert
    trust_tpbd_aliases = False #Trust TPBDs aliases without double checking
    proxies={} # Leave empty or specify proxy like this: {'http':'http://user:pass@10.10.10.10:8000','https':'https://user:pass@10.10.10.10:8000'}

    def loadConfig(self):
        try:  # Try to load configuration.py values
            import configuration
            for key, value in vars(configuration).items():
                if key[0:2] == "__": 
                    continue
                if (key == "server_ip" or key == "server_port") and ("<" in value or ">" in value):
                    logging.warning("Please remove '<' and '>' from your server_ip and server_port lines in configuration.py")
                    sys.exit()
                if isinstance(value, type(vars(config_class).get(key, None))):
                    vars(self)[key]=value
                else:
                    logging.warning("Invalid configuration parameter: "+key, exc_info=config_class.debug_mode)
            return True
        except ImportError:
            logging.error("No configuration found.  Double check your configuration.py file exists.")
            create_config = input("Create configuruation.py? (yes/no):")
            if create_config == 'y' or create_config == 'Y' or create_config =='Yes' or create_config =='yes':
                createConfig()
            else:
                logging.error("No configuration found.  Exiting.")
                sys.exit()
        except NameError as err:
            logging.error("Invalid configuration.py.  Make sure you use 'True' and 'False' (capitalized)", exc_info=config_class.debug_mode)
            sys.exit()
            
    def createConfig(self):        
        self.server_ip = input("What's your Stash server's IP address? (no port please):")
        self.server_port = input("What's your Stash server's port?:")
        https_input = input("Does your Stash server use HTTPS? (yes/no):")
        self.use_https = False
        if https_input == 'y' or https_input == 'Y' or https_input =='Yes' or https_input =='yes':
            self.use_https = True
        self.username = input ("What's your Stash server's username? (Just press enter if you don't use one):")
        self.password = input ("What's your Stash server's username? (Just press enter if you don't use one):")

        f = open("configuration.py", "w")
        f.write("""
#Server configuration
use_https = {4} # Set to False for HTTP
server_ip= "{0}"
server_port = "{1}"
username="{2}"
password="{3}"

# Configuration options
scrape_tag= "scraped_from_theporndb"  #Tag to be added to scraped scenes.  Set to None to disable
disambiguate_only = False # Set to True to run script only on scenes tagged due to ambiguous scraping. Useful for doing manual disambgiuation.  Must set ambiguous_tag for this to work
rescrape_scenes= False # If False, script will not rescrape scenes previously scraped successfully.  Must set scrape_tag for this to work
debug_mode = False

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
add_studio = False  
add_tags = False  # Script will still add scrape_tag and ambiguous_tag, if set
add_performers = False 

#Disambiguation options
#The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, these options are used.  Set both to False to skip scenes with ambiguous results
auto_disambiguate = False  #Set to True to try to pick the top result from ThePornDB automatically.  Will not set ambiguous_tag
manual_disambiguate = False #Set to True to prompt for a selection.  (Overwritten by auto_disambiguate)
ambiguous_tag = "theporndb_ambiguous" #Tag to be added to scenes we skip due to ambiguous scraping.  Set to None to disable
trust_tpbd_aliases = True #If True, when TPBD lists an alias that we can't verify, just trust TBPD to be correct.  May lead to incorrect tagging
tag_ambiguous_performers = True  # If True, will tag ambiguous performers (performers listed on ThePornDB only for a single site, not across sites)

#Other config options
parse_with_filename = True # If True, will query ThePornDB based on file name, rather than title, studio, and date
dirs_in_query = 0 # The number of directories up the path to be included in the query for a filename parse query.  For example, if the file  is at \performer\mysite\video.mp4 and dirs_in_query is 1, query would be "mysite video."  If set to two, query would be "performer mysite video", etc.
only_add_female_performers = True  #If True, only female performers are added (note, exception is made if performer name is already in title and name is found on ThePornDB)
scrape_performers_freeones = False #If True, will try to scrape newly added performers with the freeones scraper
get_images_babepedia = False #If True, will try to grab an image from babepedia before the one from ThePornDB
include_performers_in_title = True #If true, performers will be added to the beginning of the title
clean_filename = True #If True, will try to clean up filenames before attempting scrape. Probably unnecessary, as ThePornDB already does this
compact_studio_names = False # If True, this will remove spaces from studio names added from ThePornDB
ignore_ssl_warnings=True # Set to True if your Stash uses SSL w/ a self-signed cert
trust_tpbd_aliases = False #Trust TPBDs aliases without double checking
proxies={} # Leave empty or specify proxy like this: {'http':'http://user:pass@10.10.10.10:8000','https':'https://user:pass@10.10.10.10:8000'}
""".format(server_ip, server_port, username, password, use_https))
        f.close()
        print("Configuration file created.  All values are currently at defaults.  It is highly recommended that you edit the configuration.py to your liking.  Otherwise, just re-run the script to use the defaults.")
        sys.exit()

def parseArgs():
    my_parser = argparse.ArgumentParser(description='Scrape Stash Scenes from ThePornDB')

    # Add the arguments
    my_parser.add_argument('query',
                        nargs='*',
                        default="",
                        metavar='query',
                        type=str,
                        help='Query string to pass to the Stash Scene "Find" box')
    my_parser.add_argument('-d',
                       '--debug',
                       action='store_true',
                       help='enable debugging')
    my_parser.add_argument('-r',
                       '--rescrape',
                       action='store_true',
                       help='rescrape already scraped scenes')
    my_parser.add_argument('-nr',
                       '--no_rescrape',
                       action='store_true',
                       help='do not rescrape already scraped scenes')
    my_parser.add_argument('-ao',
                       '--verify_aliases_only',
                       action='store_true',
                       help='scrape only scenes with performers that need to be verified')
    my_parser.add_argument('-do',
                       '--disambiguate_only',
                       action='store_true',
                       help='scrape only scenes tagged as ambiguous')
    my_parser.add_argument('-max',
                       '--max_scenes',
                       metavar='max_scenes',
                       default=0,
                       type=int,
                       help='maximum number of scenes to scrape')
    my_parser.add_argument('-t',
                       '--tags',
                       metavar='search_tags',
                       type=str,
                       default=[],
                       action='append',
                       help='only match scenes with these tags; repeat once for each required tag')
    my_parser.add_argument('-md',
                       '--man_disambiguate',
                       action='store_true',
                       help='prompt to manually select a scene when a single result isn\'t found')
    my_parser.add_argument('-ad',
                       '--auto_disambiguate',
                       action='store_true',
                       help='automatically  select the top scene when a single result isn\'t found')
    my_parser.add_argument('-mv',
                       '--man_verify_aliases',
                       action='store_true',
                       help='prompt to manually confirm an alias when automatic verification fails')
  
    # Execute the parse_args() method to collect our args
    args = my_parser.parse_args()
    #Set variables accordingly
    global config
    global max_scenes
    global required_tags
    if args.debug: config.debug_mode = True
    if args.rescrape: config.rescrape_scenes = True
    if args.no_rescrape: config.rescrape_scenes = False
    if args.disambiguate_only: 
        config.disambiguate_only = True
        config.manual_disambiguate = True
    if args.man_disambiguate:
        config.manual_disambiguate = True
    if args.auto_disambiguate:
        config.auto_disambiguate = True
    if args.man_verify_aliases:
        config.manConfirmAlias = True
    if args.verify_aliases_only: 
        config.verify_aliases_only = True
        config.manConfirmAlias = True
    if args.max_scenes: max_scenes = args.max_scenes
    for tag in args.tags:
        required_tags.append(tag)

    return args.query

#Globals
tpbd_error_count = 0
my_stash = None
ENCODING = 'utf-8'
known_aliases = {}
required_tags = []
max_scenes = 0
config = config_class()

def main():
    logging.basicConfig(level=logging.DEBUG)
    try:
        global my_stash
        global max_scenes
        global required_tags
        global config
        global tpbd_error_count
        tpbd_error_count = 0
        config.loadConfig()
        scenes = None
        
        if len(parseArgs()) == 1:
            query = "\""+parseArgs()[0]+"\""
        else:
            query = ' '.join(parseArgs())

        if not config.debug_mode: logging.getLogger().setLevel("WARNING")

        if config.use_https:
            server = 'https://'+str(config.server_ip)+':'+str(config.server_port)
        else:
            server = 'http://'+str(config.server_ip)+':'+str(config.server_port)
        
        my_stash = stash_interface(server, config.username, config.password, config.ignore_ssl_warnings)

        if config.ambiguous_tag: my_stash.getTagByName(config.ambiguous_tag, True)
        if config.scrape_tag: scrape_tag_id = my_stash.getTagByName(config.scrape_tag, True)["id"]
        config.unconfirmed_alias = my_stash.getTagByName("ThePornDB Unconfirmed Alias", True)["name"]
         
        findScenes_params = {}
        findScenes_params['filter'] = {'q':query, 'sort':"created_at", 'direction':'DESC'}
        findScenes_params['scene_filter'] = {}
        if max_scenes != 0:  findScenes_params['max_scenes'] = max_scenes

        if config.disambiguate_only:  #If only disambiguating scenes
            required_tags.append(config.ambiguous_tag)
        if config.verify_aliases_only: #If only disambiguating aliases
            required_tags.append(config.unconfirmed_alias)
        
        #Set our filter to require any required_tags
        if len(required_tags)>0:
            required_tag_ids = []
            for tag_name in required_tags:
                tag = my_stash.getTagByName(tag_name, False)
                if tag:
                    required_tag_ids.append(tag["id"])
                else:
                    logging.error("Did not find tag in Stash: "+tag_name, exc_info=config.debug_mode)
            findScenes_params['scene_filter'] =  {'tags': { 'modifier':'INCLUDES', 'value': [*required_tag_ids]}}
            scenes_with_tags = my_stash.findScenes(**findScenes_params)
            scenes = scenes_with_tags

        if not config.rescrape_scenes: #If only scraping unscraped scenes
            findScenes_params['scene_filter'] =  {'tags': { 'modifier':'EXCLUDES', 'value': [scrape_tag_id]}}
            scenes_without_tags = scenes = my_stash.findScenes(**findScenes_params)
            scenes = scenes_without_tags
        
        if config.rescrape_scenes and len(required_tags)==0:  #If no tags are required or excluded
            scenes = my_stash.findScenes(**findScenes_params)
        
        if len(required_tags)>0 and not config.rescrape_scenes:
            scenes = [scene for scene in scenes_with_tags if scene in scenes_without_tags] #Scenes that exist in both

        for scene in scenes:
            scrapeScene(scene)
        
        print("Success! Finished.")

    except Exception as e:
        logging.error("""Something went wrong.  Have you:
        • Checked to make sure you're running the "development" branch of Stash, not "latest"?
        • Checked that you can connect to Stash at the same IP and port listed in your configuration.py?
        If you've check both of these, run the script again with the --debug flag.  Then post the output of that in the Discord and hopefully someone can help.
        """, exc_info=config.debug_mode)

if __name__ == "__main__":
    main()
