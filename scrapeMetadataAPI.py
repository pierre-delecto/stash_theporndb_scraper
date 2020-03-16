import os
import requests
import json
import re
import urllib
import sys
import base64
from urllib.parse import quote


#Change the lines below to match your config
server = 'http<s>://<STASH-IP>:<PORT>/graphql'
username='<username>'
password='<password>'

# Configuration options
ignore_ssl_warnings=True # Set to true if your Stash uses SSL w/ a self-signed cert
add_performers = True # If true, the script will add performers listed by Metadata API but not in Stash
only_add_female_performers = True  #If true, only female performers are added (note, exception is made if performer name is already in title and name is found on MetadataAPI 

add_studio = True  # If true, the script will add studio listed by Metadata API but not in Stash
add_tags = True  # If true, the script will add tags listed by Metadata API but not in Stash

set_title = True # If true, the script will rename the scene based on Metadataapi's title
include_performers_in_title = True #If true, performers will be prepended to the title
parse_performers_freeones = True #If true, will try to parse newly added performers with the freeones parser
get_images_babeopedia = True #If true, will try to grab an image from babeopedia before the one from metadataapi

parse_with_filename = True # If true, will query MetadataAPI based on file name, rather than title, studio, and date
clean_filename = True #If true, will try to clean up filenames before attempting scrape (VERY UNTESTED)
accept_ambiguous_results = True  #The script tries to disambiguate using title, studio, and date (or just filename if parse_with_filename is true).  If this combo still returns more than one result, set this to true to use the first result

ENCODING = 'utf-8'

#if ignore_ssl_warnings:
#    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

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
    scrubbedWords = ['MP4-(.+?)$', ' XXX ', '1080p', '720p', 'WMV-(.+?)$', '-UNKNOWN', ' x264-(.+?)$', 'DVDRip','WEBRIP', 'WEB', '\[PRiVATE\]', 'HEVC', 'x265', 'PRT-xpost', '480p', ' SD', ' HD', '\'']

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
    
    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), 
                        verify= not ignore_ssl_warnings)
    if request.status_code == 200:
        result = request.json()
        stashPerformers = result["data"]["allPerformers"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    return stashPerformers

def getStashStudios():
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

    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password),
                            verify=not ignore_ssl_warnings)
    if request.status_code == 200:
        result = request.json()
        stashStudios = result["data"]["allStudios"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    return stashStudios


def getStashTags():
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

    request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password),
                            verify=not ignore_ssl_warnings)
    if request.status_code == 200:
        result = request.json()
        stashTags = result["data"]["allTags"]
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    return stashTags

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
      tags
      	{{
            name
            id
        }}
    }}
  }}
}}
""".format(query_string, per_page, page)

        request = requests.post(server, json={'query': query}, headers=headers, auth=(username, password), 
                                verify= not ignore_ssl_warnings)

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
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, 
                            auth=(username, password), verify= not ignore_ssl_warnings)

    if request.status_code == 200:
        result = request.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))   

    if "errors" in result.keys() and len(result["errors"]) > 0:
        raise Exception ("GraphQL Error when running query. Errors: {}".format(result["errors"])) 
        
def addPerformerToStash(performer_data):
    query = """
mutation performerCreate($input:PerformerCreateInput!) {
  performerCreate(input: $input){
    id 
  }
}
"""
    variables = {'input': performer_data}
    
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, 
                            auth=(username, password), verify= not ignore_ssl_warnings)
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
    return base64.b64encode(requests.get(url, auth=HTTPBasicAuth(username, password)).content, 
                            verify= not ignore_ssl_warnings) 

def addStudioToStash(studio_data):
    query = """
    mutation studioCreate($input:StudioCreateInput!) {
      studioCreate(input: $input){
        id       
      }
    }
    """

    variables = {'input': studio_data}

    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers,
                            auth=(username, password), verify=not ignore_ssl_warnings)
    try:
        if request.status_code == 200:
            result = request.json()

            # Update global list
            global stashStudios
            stashStudios = getStashStudios()

            return result["data"]["studioCreate"]["id"]

        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    except Exception as e:
        print("Error in adding studio:")
        print(variables)

def addTagsToStash(tag_data):
    query = """
    mutation tagCreate($input:TagCreateInput!) {
      tagCreate(input: $input){
        id       
      }
    }
    """

    variables = {'input': tag_data}

    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers,
                            auth=(username, password), verify=not ignore_ssl_warnings)
    try:
        if request.status_code == 200:
            result = request.json()

            # Update global stash tags so if we add more we don't add duplicates
            global stashTags
            stashTags = getStashTags()

            return result["data"]["tagCreate"]["id"]

        else:
            raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))
    except Exception as e:
        print(e)
        print("Error in adding tags:")
        print(variables)
    

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
    
    request = requests.post(server, json={'query': query, 'variables': variables}, headers=headers, 
                            auth=(username, password), verify= not ignore_ssl_warnings)
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
    else:
        scene_update_data["performer_ids"] = []
    if keyIsSet(scene_data, "tags"):
        scene_update_data["tag_ids"] = []
        for tag in scene_data["tags"]:
            scene_update_data["tag_ids"].append(tag["id"])
    else:
        scene_update_data["tag_ids"] = []
    return scene_update_data
    
def getPerformerByName(performer_list, name):
    for performer in performer_list:
        if performer['name'].lower() == name.lower():
            return performer
        elif "aliases" in performer and performer["aliases"]!=None and name.lower() in performer["aliases"].lower():
                return performer
                print("Found an Alias for: "+name)
    return None

def getStudioByName(studio_list, name):
    for studio in studio_list:
        if studio['name'].lower().strip() == name.lower().strip():
            return studio
    return None


def getTagByName(tag_list, name):
    current_tag = str(name.lower().replace('-', ' ').replace('(', '').replace(')', '').replace(
        'pov', '').replace('standing', '').strip().replace(' ', ''))
    for tag in tag_list:
        if str(tag['name'].lower()) == current_tag:
            return tag
        if str(tag['name'].lower().replace(' ', '').replace('-', ' ')) == current_tag:
            return tag
    return None

def createStashPerformerData(metadataapi_performer): #Creates stash-compliant data from raw data provided by metadataapi
    stash_performer = {}
    stash_performer["name"] = metadataapi_performer["name"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "birthday"]): stash_performer["birthdate"] = \
        metadataapi_performer["parent"]["extras"]["birthday"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "measurements"]): stash_performer["measurements"] = \
        metadataapi_performer["parent"]["extras"]["measurements"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "tattoos"]): stash_performer["tattoos"] = \
        metadataapi_performer["parent"]["extras"]["tattoos"]
    if keyIsSet(metadataapi_performer, ["parent", "extras", "piercings"]): stash_performer["piercings"] = \
        metadataapi_performer["parent"]["extras"]["piercings"]
    # TODO: support Aliases (does Metadataapi support this?)

    return stash_performer

def createStashStudioData(
        metadataapi_studio):  # Creates stash-compliant data from raw data provided by metadataapi
    stash_studio = {}
    stash_studio["name"] = metadataapi_studio["name"]
    stash_studio["url"] = metadataapi_studio["url"]
    if metadataapi_studio["logo"] is not None:
        image = get_base64_image(metadataapi_studio["logo"])
        stash_studio["image"] = image

    return stash_studio


def createStashTagData(
        metadataapi_tag):  # Creates stash-compliant data from raw data provided by metadataapi
    stash_tag = {}
    stash_tag["name"] = metadataapi_tag["tag"].lower().replace('-', ' ').replace('(', '').replace(')', '').replace(
        'pov', '').replace('standing', '').strip().title()

    return stash_tag

def get_base64_image(image_url):
    # Download
    #image = requests.get(image_url,
    #                     headers={'Accept':'image/jpg, image/jpeg'}).content
    image = requests.get(image_url).content
    image_b64 = base64.b64encode(image)
    if image_b64:
        return image_b64.decode(ENCODING)

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

def getBabeopediaImage(name):
    url = "https://www.babepedia.com/pics/"+urllib.parse.quote(name)+".jpg"
    return requests.get(url).content  

def getMetadataapiImage(name):
    url = "https://metadataapi.net/api/performers?q="+urllib.parse.quote(name)
    if len(requests.get(url).json()["data"])==1: #If we only have 1 hit
        raw_data = requests.get(url).json()["data"][0]
        image_url = raw_data["image"]
        if not "default.png" in image_url:
            print("Found image for "+name+" at "+image_url)
            return requests.get(image_url).content
    return ""

def getPerformerImageB64(name):  #Searches Babeopedia and MetadataAPI for a performer image
    try:
        performer = getPerformerByName(stashPerformers, name)

        # Try thePornDB first
        image = getMetadataapiImage(name)
        if image is not None and image != '':
            image_b64 = base64.b64encode(image)
            stringbase = str(image_b64)
            if stringbase[2:6] == "/9j/":
                return image_b64.decode(ENCODING)

        if get_images_babeopedia:
            # Try Boobopedia
            image = getBabeopediaImage(name)
            if image is not None and image != '':
                image_b64 = base64.b64encode(image)
                stringbase = str(image_b64)
                if stringbase[2:6] == "/9j/":
                    return image_b64.decode(ENCODING)

            # Try aliases at Boobopedia
            if keyIsSet(performer, "aliases"):
                aliases = [x.strip() for x in performer["aliases"].split(',')]
                for alias in aliases:
                    image = getBabeopediaImage(alias)
                    if image is not None and image != '':
                        image_b64 = base64.b64encode(image)
                        stringbase = str(image_b64)
                        if stringbase[2:6] == "/9j/":
                            return image_b64.decode(ENCODING)

        return None
    except Exception as e:
        print(e)

def scrapeMetadataAPI(query, override_ambiguous = False):  # Scrapes MetadataAPI based on query.  Returns "ambiguous" if more than 1 result is found, unless override is True
    raw_data ={}
    url = "https://metadataapi.net/api/scenes?parse="+urllib.parse.quote(query)
    
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
    try:
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

        if scraped_data is not None:
            if not parse_with_filename and scraped_data == "ambiguous" and keyIsSet(scene, "studio"):
                scrape_query = scrape_query + " " + scene['studio']['name']
                scraped_data = scrapeMetadataAPI(scrape_query)

            if not parse_with_filename and scraped_data == "ambiguous" and keyIsSet(scene_data, "date"):
                scrape_query = scrape_query + " " + scene_data['date']
                scraped_data = scrapeMetadataAPI(scrape_query)

            if not parse_with_filename and accept_ambiguous_results and keyIsSet(scene_data, "studio") and keyIsSet(
                    scene_data,
                    "date"):
                scraped_data = scrapeMetadataAPI(scrape_query, True)

            if scraped_data and not scraped_data == "ambiguous":  # If we got new data, update our current data with the new
                scene_data["details"] = scraped_data["description"]
                scene_data["date"] = scraped_data["date"]
                scene_data["cover_image"] = get_base64_image(scraped_data["background"]['small'])

                # Add Studio to the scene
                if keyIsSet(scraped_data, "site"):
                    studio_id = None
                    scraped_studio = scraped_data['site']
                    stash_studio = getStudioByName(stashStudios, scraped_studio['name'])
                    if stash_studio:
                        studio_id = stash_studio["id"]
                    elif add_studio:
                        # Add the Studio to Stash
                        print("Did not find " + scraped_studio['name'] + " in Stash.  Adding Studio.")
                        studio_id = addStudioToStash((createStashStudioData(scraped_studio)))
                        print(studio_id)

                    if studio_id != None:  # If we have a valid ID, add studio to Scene
                        scene_data["studio_id"] = studio_id

                # Add Tags to the scene
                if keyIsSet(scraped_data, "tags"):
                    scraped_tag_ids = []
                    for scraped_tag in scraped_data["tags"]:
                        tag_id = None
                        # stashTags = getStashTags()
                        stash_tag = getTagByName(stashTags, scraped_tag['tag'])
                        if stash_tag:
                            tag_id = stash_tag["id"]
                        elif add_tags:
                            # Add the Tag to Stash
                            print("Did not find " + scraped_tag['tag'] + " in Stash.  Adding Tag.")
                            tag_id = addTagsToStash((createStashTagData(scraped_tag)))
                            print(tag_id)

                        if tag_id != None:  # If we have a valid ID, add tag to Scene
                            scraped_tag_ids.append(tag_id)

                # Add performers to scene
                if keyIsSet(scraped_data, "performers"):
                    scraped_performer_ids = []
                    for scraped_performer in scraped_data["performers"]:
                        performer_id = None
                        stash_performer = getPerformerByName(stashPerformers, scraped_performer['name'])
                        if stash_performer:
                            performer_id = stash_performer["id"]
                        elif add_performers and ((scraped_performer['name'].lower() in scene_data[
                            "title"].lower()) or not only_add_female_performers or (
                                                         keyIsSet(scraped_performer, ["parent", "extras", "gender"]) and
                                                         scraped_performer["parent"]["extras"][
                                                             "gender"] == 'Female')):  # Add performer if we meet relevant requirements
                            print("Did not find " + scraped_performer['name'] + " in Stash.  Adding performer.")

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

                        if performer_id != None:  # If we have a valid ID, add performer to Scene
                            scraped_performer_ids.append(performer_id)

                # TODO: Support addition of tags (should be similar to addition of performer)

                scene_data["performer_ids"] = list(set(scene_data["performer_ids"] + scraped_performer_ids))
                scene_data["tag_ids"] = list(set(scene_data["tag_ids"] + scraped_tag_ids))

                performer_names = []
                if keyIsSet(scene_data, "performer_ids"):
                    for performer_id in scene_data["performer_ids"]:
                        for performer in stashPerformers:
                            if performer['id'] == performer_id:
                                performer_names.append(performer["name"])
                # Set Title
                if set_title:
                    new_title = ""
                    if include_performers_in_title and len(performer_names) > 2:
                        new_title = "{}, and {}".format(", ".join(performer_names[:-1]), performer_names[-1])
                    if include_performers_in_title and len(performer_names) == 2:
                        new_title = performer_names[0] + " and " + performer_names[1]
                    if include_performers_in_title and len(performer_names) == 1:
                        new_title = performer_names[0]
                    if include_performers_in_title:
                        for name in performer_names:
                            scraped_data["title"] = lreplace(name, '', scraped_data["title"]).strip()

                    new_title = new_title + " " + scraped_data["title"]
                    scene_data["title"] = new_title

                updateStashSceneData(scene_data)
                print("Success")
            else:
                print("Failure: [{}]".format(scrape_query))
                print(scene_data['details'])
    except Exception as e:
        print(e)

def main():
    try:
        global stashPerformers
        global stashStudios
        global stashTags

        query="nanny"
        if len(sys.argv) > 2:
            query = sys.argv[1]

        scenes = getStashScenes(query)
        stashPerformers = getStashPerformers()
        stashStudios = getStashStudios()
        stashTags = getStashTags()

        for scene in scenes:
            updateSceneFromMetadataAPI(scene)

        print("Success! Finished.")

    except Exception as e:
        print(e)

if __name__ == "__main__":
    main()
    

