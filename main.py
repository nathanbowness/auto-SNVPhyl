try:
    API_KEY = open("api_key","r").read()
except FileNotFoundError:
    print("Can't find api_key")
    raise

print("Using " + API_KEY + " as API key.")