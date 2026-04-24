import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Load credentials from the project's token file
token_path = "/Users/alfredomartel/dev/antigravity/workspaces/Vibemus/data/youtube_token.json"
with open(token_path, "r") as f:
    import json
    creds_data = json.load(f)

creds = Credentials.from_authorized_user_info(creds_data)
yt = build("youtube", "v3", credentials=creds)

video_id = "oRjO2YFDnSw"
resp = yt.videos().list(part="snippet,contentDetails,statistics,status,topicDetails,recordingDetails,player", id=video_id).execute()
print(json.dumps(resp, indent=2))
