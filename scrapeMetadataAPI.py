import os
import requests
import json
import re
import urllib
import sys
import base64
from requests.packages.urllib3.exceptions import InsecureRequestWarning


#Change the lines below to match your config
server='http<s>://<stashIP:PORT>/graphql'
username='<username>'
password='<password>'

# Configuration options
ignore_ssl_warnings=True # Set to true if your Stash uses SSL w/ a self-signed cert
add_performers = True # If true, the script will add performers listed by Metadata API but not in Stash
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on MetadataAPI 

set_title = True # If true, the script will rename the scene based on Metadataapi's title
include_performers_in_title = True #If true, performers will be prepended to the title
parse_performers_freeones = True #If true, will try to parse newly added performers with the freeones parser
get_images_babeopedia = True #If true, will try to grab an image from babeopedia before the one from metadataapi

parse_with_filename = True # If true, will query MetadataAPI based on file name, rather than title, studio, and date
clean_filename = True #If true, will try to clean up filenames before attempting scrape (VERY UNTESTED)
accept_ambiguous_results = True  #The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, set this to true to use the first result

if ignore_ssl_warnings:
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

headers = {
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Connection": "keep-alive",
    "DNT": "1"
    }

#Utility Functions
def lreplace(pattern, sub, string):
    """
    Replaces 'pattern' in 'string' with 'sub' if 'pattern' starts 'string'.
    """
    return re.sub('^%s' % pattern, sub, string)

def scrubFileName(file_name):
    scrubbedWords = ['MP4-(.+?)$',' XXX ','1080p','720p','WMV-(.+?)$','-UNKNOWN',' x264-(.+?)$','DVDRip','WEBRIP','WEB','\[PRiVATE\]','HEVC','x265','PRT-xpost', '480p', ' SD', ' HD']

    clean_name = re.sub('\.', ' ', file_name) ##replace periods with spaces
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

#GraphQL Functions    
def getStashPerformers():  
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
    
    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        result = request.json()
        stashPerformers = result["data"]["allPerformers"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    return stashPerformers

def getStashScenes(query_string, page = 0):
    stashScenes =[]
    per_page = 100
    try:
        query = """
{{
  findScenes(filter: {{q:"\\"{0}\\"", per_page:{1}, page:{2}}})
  {{
    count
    scenes{{
      id
      title
      date
      details
      path
      studio {{
        id
        name
        }}
      performers
      	{{
            name
            id
        }}
    }}
  }}
}}
""".format(query_string, per_page, page)

        request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)

        if request.status_code == 200:
            result = request.json()
            stashScenes = result["data"]["findScenes"]["scenes"]
        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
        print("Getting Stash Scenes Page: "+str(page)+" of "+str(result["data"]["findScenes"]["count"] / per_page))
    
        if (page < result["data"]["findScenes"]["count"] / per_page):
            stashScenes = stashScenes+getStashScenes(query_string, page+1)
    except:
        print("Unexpected error getting stash scene:", sys.exc_info()[0]) 

    return stashScenes  
        
def updateStashSceneData(scene_data):
    query = """
mutation sceneUpdate($input:SceneUpdateInput!) {
  sceneUpdate(input: $input){
    title
  }
}
"""

    variables = {'input': scene_data}
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        result = request.json()

    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))    
        
def addPerformerToStash(performer_data):
    query = """
mutation performerCreate($input:PerformerCreateInput!) {
  performerCreate(input: $input){
    id 
  }
}
"""
    variables = {'input': performer_data}
    
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)
    try:
        if request.status_code == 200:
            result = request.json()
            return result["data"]["performerCreate"]["id"]

        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    except:
        print("Error in adding performer:")
        print(variables)
        print(result)

def getPerformerImageFromStash(url):
    return base64.b64encode(requests.get(url, auth=HTTPBasicAuth(username, password)).content, verify= not ignore_ssl_warnings) 

def getStashStudios():
    return None #stub

def addStudioToStash():
    return None #stub
    

def updateStashPerformerData(performer_data):
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
    #print(query)
    
    #print(performer_data)
    variables = {'input': performer_data}
    
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        return request.json()["data"]["performerUpdate"]

    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))    

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
    return scene_update_data
    
def getPerformerByName(performer_list, name):
    for performer in performer_list:
        if performer['name'].lower() == name.lower():
            return performer
        elif "aliases" in performer and performer["aliases"]!=None and name.lower() in performer["aliases"].lower():
                return performer
                print("Found an Alias for: "+name)
    return None

def createStashPerformerData(metadataapi_performer): #Creates stash-compliant data from raw data provided by metadataapi
    stash_performer = {}
    stash_performer["name"] = metadataapi_performer["name"]
    if keyIsSet(metadataapi_performer, ["parent","extras","birthday"]): stash_performer["birthdate"] = metadataapi_performer["parent"]["extras"]["birthday"]
    if keyIsSet(metadataapi_performer, ["parent","extras","measurements"]): stash_performer["measurements"] = metadataapi_performer["parent"]["extras"]["measurements"]
    if keyIsSet(metadataapi_performer, ["parent","extras","tattoos"]): stash_performer["tattoos"] = metadataapi_performer["parent"]["extras"]["tattoos"]
    if keyIsSet(metadataapi_performer, ["parent","extras","piercings"]): stash_performer["piercings"] = metadataapi_performer["parent"]["extras"]["piercings"]
    #TODO: support Aliases (does Metadataapi support this?)
  
    return stash_performer
        
def scrapePerformerFreeones(name):
    query = """
{
	scrapeFreeones(performer_name: \""""+name+"""\")
    { url twitter instagram birthdate ethnicity country eye_color height measurements fake_tits career_length tattoos piercings aliases }

}
"""
    
    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        return request.json()["data"]["scrapeFreeones"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))

def getBabeopediaImage(name):
    url = "https://www.babepedia.com/pics/"+urllib.quote(name)+".jpg"
    return requests.get(url).content  

def getMetadataapiImage(name):
    url = "https://metadataapi.net/api/performers?q="+urllib.quote(name)
    if len(requests.get(url).json()["data"])==1: #If we only have 1 hit
        raw_data = requests.get(url).json()["data"][0]
        image_url = raw_data["image"]
        if not "default.png" in image_url:
            print("Found image for "+name+" at "+image_url)
            return requests.get(image_url).content
    return ""

def getPerformerImageB64(name):  #Searches Babeopedia and MetadataAPI for a performer image
    performer = getPerformerByName(stashPerformers, name)
    
    if get_images_babeopedia:
        #Try Boobopedia
        image = getBabeopediaImage(name)
        image_b64 = base64.b64encode(image)
        if image_b64[0:4]=="/9j/":
            return image_b64
        
        #Try aliases at Boobopedia
        if keyIsSet(performer, "aliases"):
            aliases = [x.strip() for x in performer["aliases"].split(',')]
            for alias in aliases:
                image = getBabeopediaImage(alias)
                image_b64 = base64.b64encode(image)
                if image_b64[0:4]=="/9j/":
                    return image_b64
    
    #Try thePornDB
    image = getMetadataapiImage(name)
    image_b64 = base64.b64encode(image)
    if image_b64[0:4]=="/9j/":
        return image_b64
        
    return None

def scrapeMetadataAPI(query, override_ambiguous = False):  # Scrapes MetadataAPI based on query.  Returns "ambiguous" if more than 1 result is found, unless override is True
    raw_data ={}
    url = "https://metadataapi.net/api/scenes?parse="+urllib.quote(query)
    
    try:
        results = requests.get(url).json()["data"]
        if len(results)==0: return None
        if len(results)>1 and not override_ambiguous: return "ambiguous"
        
        if len(results)==1 or override_ambiguous: #If we only have 1 hit or we just want the first hit
            raw_data = requests.get(url).json()["data"][0]  
            return raw_data
    except ValueError:
        print("Error communicating with MetadataAPI")
    return raw_data

def updateSceneFromMetadataAPI(scene):

    scene_data = createSceneUpdateFromSceneData(scene)  #Start with our current data as a template
    if parse_with_filename:
        file_name = re.search(r'^\/(.+\/)*(.+)\.(.+)$', scene['path']).group(2)
        if clean_filename:
            file_name = scrubFileName(file_name)
        scrape_query = file_name
    else:
        scrape_query = scene_data['title']
    
    print("Grabbing Data For: "+scrape_query)
    scraped_data = scrapeMetadataAPI(scrape_query)
    
    if not parse_with_filename and scraped_data == "ambiguous" and keyIsSet(scene, "studio"):
        scrape_query = scrape_query+" "+scene['studio']['name']
        scraped_data = scrapeMetadataAPI(scrape_query)
    
    if not parse_with_filename and scraped_data == "ambiguous" and keyIsSet(scene_data, "date"):
        scrape_query = scrape_query+" "+scene_data['date']
        scraped_data = scrapeMetadataAPI(scrape_query)
    
    if not parse_with_filename and accept_ambiguous_results and keyIsSet(scene_data, "studio") and keyIsSet(scene_data, "date"):
        scraped_data = scrapeMetadataAPI(scrape_query, True)
    
    if scraped_data and not scraped_data == "ambiguous":  #If we got new data, update our current data with the new 
        scene_data["details"]=scraped_data["description"]
        scene_data["date"]=scraped_data["date"]
        scene_data["url"]=scraped_data["url"]
        
        #Add performers to scene
        if keyIsSet(scraped_data, "performers"):
            scraped_performer_ids = []
            for scraped_performer in scraped_data["performers"]:
                performer_id = None
                stash_performer = getPerformerByName(stashPerformers, scraped_performer['name'])
                if stash_performer:
                    performer_id=stash_performer["id"]
                elif add_performers and ((scraped_performer['name'].lower() in scene_data["title"].lower()) or not only_add_female_performers or (keyIsSet(scraped_performer, ["parent", "extras", "gender"]) and scraped_performer["parent"]["extras"]["gender"]=='Female')): #Add performer if we meet relevant requirements
                    print("Did not find "+scraped_performer['name']+" in Stash.  Adding performer.")
                    
                    performer_id = addPerformerToStash(createStashPerformerData(scraped_performer))
                    print(performer_id)
                    performer_data = {}
                                        
                    if parse_performers_freeones:
                        performer_data = scrapePerformerFreeones(scraped_performer['name'])
                        if not performer_data:
                            performer_data = {}
                    
                    performer_data["id"] = performer_id
                    
                    performer_data["image"] = getPerformerImageB64(scraped_performer['name'])
                    stashPerformers.append(updateStashPerformerData(performer_data))

                if performer_id!=None:  #If we have a valid ID, add performer to Scene
                    scraped_performer_ids.append(performer_id)
        
        # TODO: Support addition of studio (should be similar to addition of performer)
        
        scene_data["performer_ids"]=list(set(scene_data["performer_ids"]+scraped_performer_ids))
        
        performer_names = []
        if keyIsSet(scene_data, "performer_ids"):
            for performer_id in scene_data["performer_ids"]:
                for performer in stashPerformers:
                    if performer['id'] == performer_id:
                        performer_names.append(performer["name"])
        #Set Title
        if set_title:
            new_title=""
            if include_performers_in_title and len(performer_names)>2:
                new_title="{}, and {}".format(", ".join(performer_names[:-1]),  performer_names[-1])
            if include_performers_in_title and len(performer_names)==2:
                new_title=performer_names[0]+" and "+performer_names[1]
            if include_performers_in_title and len(performer_names)==1:
                new_title=performer_names[0]
            if include_performers_in_title:
                for name in performer_names:
                    scraped_data["title"] = lreplace(name,'',scraped_data["title"]).strip()
            
            new_title = new_title +" "+scraped_data["title"]
            scene_data["title"] = new_title
        
        updateStashSceneData(scene_data)
        print("Success")
    else:
        print("Failure")

def main():
    global stashPerformers
    
    query = ""
    if len(sys.argv)>1:
        query = sys.argv[1]
        
    scenes = getStashScenes(query)
    stashPerformers=getStashPerformers()
    
    for scene in scenes:
        updateSceneFromMetadataAPI(scene)

if __name__ == "__main__":
    main()
    

