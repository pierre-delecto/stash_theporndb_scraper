import scrapeMetadataAPI 
try:  # Try to load configuration.py values
    import configuration
    for key, value in vars(configuration).items():
        globals()[key]=value
except ImportError:
    print("No configuration found.  Double check your configuration.py file exists.")
    create_config = input("Create configuruation.py? (yes/no):")
    if create_config == 'y' or create_config == 'Y' or create_config =='Yes' or create_config =='yes':
        createConfig()
    else:
        print("No configuration found.  Exiting.")
        sys.exit()

if use_https:
    server = 'https://'+str(server_ip)+':'+str(server_port)+'/graphql'
else:
    server = 'http://'+str(server_ip)+':'+str(server_port)+'/graphql'
    
my_stash = scrapeMetadataAPI.stash_interface(server, username, password, ignore_ssl_warnings)



print(my_stash.getTagByName("scraped_from_theporndb")['id'])