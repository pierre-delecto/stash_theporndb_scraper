result = {"data":[{"what":"1"}]}

if  next(iter(result.get("data", [{}])), {}).get("id", None):
    performer_id = result["data"][0]["id"]
    print(result["data"][0]["id"])
else:
    print("No")