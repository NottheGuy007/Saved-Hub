import streamlit as st
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import praw
import os
import json
import tempfile
import time

# Streamlit app configuration
st.set_page_config(page_title="Saved Content Viewer", layout="wide")

# Session state initialization
if "youtube_credentials" not in st.session_state:
    st.session_state.youtube_credentials = None
if "reddit_access_token" not in st.session_state:
    st.session_state.reddit_access_token = None
if "youtube_api" not in st.session_state:
    st.session_state.youtube_api = None
if "reddit" not in st.session_state:
    st.session_state.reddit = None
if "youtube_videos" not in st.session_state:
    st.session_state.youtube_videos = []
if "reddit_posts" not in st.session_state:
    st.session_state.reddit_posts = []
if "last_sync_time" not in st.session_state:
    st.session_state.last_sync_time = 0
if "sync_interval" not in st.session_state:
    st.session_state.sync_interval = 60  # Sync every 60 seconds

# YouTube API setup
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Reddit API setup
REDDIT_REDIRECT_URI = "http://localhost:8501"  # Streamlit default port

# Load secrets
try:
    YOUTUBE_CLIENT_SECRET_JSON = st.secrets["youtube"]["client_secret_json"]
    REDDIT_CLIENT_ID = st.secrets["reddit"]["client_id"]
    REDDIT_CLIENT_SECRET = st.secrets["reddit"]["client_secret"]
    REDDIT_USER_AGENT = st.secrets["reddit"]["user_agent"]
except KeyError as e:
    st.error(f"Missing secret: {e}. Please configure secrets.toml with YouTube and Reddit credentials.")
    st.stop()

# Create temporary file for YouTube client secret JSON
def create_temp_client_secret_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        temp_file.write(YOUTUBE_CLIENT_SECRET_JSON)
        return temp_file.name

def get_youtube_api(credentials):
    """Initialize YouTube API client with credentials."""
    return googleapiclient.discovery.build(
        YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials
    )

def fetch_youtube_saved_videos(youtube_api):
    """Fetch saved (liked) videos from YouTube."""
    try:
        videos = []
        request = youtube_api.videos().list(
            part="snippet", myRating="like", maxResults=10
        )
        response = request.execute()
        for item in response.get("items", []):
            videos.append({
                "title": item["snippet"]["title"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "thumbnail": item["snippet"]["thumbnails"]["default"]["url"]
            })
        return videos
    except googleapiclient.errors.HttpError as e:
        st.error(f"Error fetching YouTube videos: {e}")
        return []

def fetch_reddit_saved_posts(reddit):
    """Fetch saved posts from Reddit."""
    try:
        saved_posts = []
        for item in reddit.user.me().saved(limit=10):
            if hasattr(item, "title"):  # Submission (post)
                saved_posts.append({
                    "title": item.title,
                    "url": item.permalink,
                    "subreddit": item.subreddit.display_name
                })
        return saved_posts
    except Exception as e:
        st.error(f"Error fetching Reddit posts: {e}")
        return []

def youtube_login():
    """Handle YouTube OAuth login."""
    client_secret_file = create_temp_client_secret_file()
    try:
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            client_secret_file, YOUTUBE_SCOPES
        )
        flow.redirect_uri = "http://localhost:8501"
        authorization_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true"
        )
        st.session_state.oauth_state = state
        st.session_state.oauth_flow = flow
        st.markdown(f"[Login to YouTube]({authorization_url})")
    finally:
        os.unlink(client_secret_file)  # Clean up temporary file

def reddit_login():
    """Handle Reddit OAuth login."""
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        redirect_uri=REDDIT_REDIRECT_URI,
        user_agent=REDDIT_USER_AGENT
    )
    auth_url = reddit.auth.url(["identity", "read", "save"], "uniqueKey", "temporary")
    st.markdown(f"[Login to Reddit]({auth_url})")

def handle_youtube_callback():
    """Handle YouTube OAuth callback."""
    if "code" in st.query_params and "state" in st.query_params:
        if st.query_params["state"] == st.session_state.oauth_state:
            flow = st.session_state.oauth_flow
            flow.fetch_token(code=st.query_params["code"])
            st.session_state.youtube_credentials = flow.credentials
            st.session_state.youtube_api = get_youtube_api(flow.credentials)
            st.query_params.clear()
            sync_content()  # Sync content immediately after login
            st.rerun()

def handle_reddit_callback():
    """Handle Reddit OAuth callback."""
    if "code" in st.query_params:
        try:
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                redirect_uri=REDDIT_REDIRECT_URI,
                user_agent=REDDIT_USER_AGENT
            )
            reddit.auth.authorize(st.query_params["code"])
            st.session_state.reddit = reddit
            st.query_params.clear()
            sync_content()  # Sync content immediately after login
            st.rerun()
        except Exception as e:
            st.error(f"Reddit login failed: {e}")

def sync_content():
    """Sync YouTube and Reddit content if logged in."""
    current_time = time.time()
    if current_time - st.session_state.last_sync_time >= st.session_state.sync_interval:
        if st.session_state.youtube_api:
            st.session_state.youtube_videos = fetch_youtube_saved_videos(st.session_state.youtube_api)
        if st.session_state.reddit:
            st.session_state.reddit_posts = fetch_reddit_saved_posts(st.session_state.reddit)
        st.session_state.last_sync_time = current_time

# Main app
st.title("Saved Content Viewer")

# Handle OAuth callbacks
handle_youtube_callback()
handle_reddit_callback()

# Sync content if logged in
sync_content()

# Tabs for YouTube and Reddit
tab1, tab2 = st.tabs(["YouTube", "Reddit"])

with tab1:
    st.header("YouTube Saved Videos")
    if not st.session_state.youtube_credentials:
        st.write("Please log in to view your saved YouTube videos.")
        youtube_login()
    else:
        if st.session_state.youtube_videos:
            for video in st.session_state.youtube_videos:
                st.image(video["thumbnail"], width=120)
                st.markdown(f"[{video['title']}]({video['url']})")
        else:
            st.write("No saved videos found or an error occurred.")
        st.write(f"Last synced: {time.ctime(st.session_state.last_sync_time)}")

with tab2:
    st.header("Reddit Saved Posts")
    if not st.session_state.reddit:
        st.write("Please log in to view your saved Reddit posts.")
        reddit_login()
    else:
        if st.session_state.reddit_posts:
            for post in st.session_state.reddit_posts:
                st.markdown(f"**{post['title']}** (r/{post['subreddit']})")
                st.markdown(f"[Link](https://reddit.com{post['url']})")
        else:
            st.write("No saved posts found or an error occurred.")
        st.write(f"Last synced: {time.ctime(st.session_state.last_sync_time)}")

# Manual sync and logout buttons
st.sidebar.header("Controls")
if st.sidebar.button("Sync Now"):
    st.session_state.last_sync_time = 0  # Force sync
    sync_content()
    st.rerun()

if st.session_state.youtube_credentials or st.session_state.reddit:
    st.sidebar.header("Logout")
    if st.session_state.youtube_credentials and st.sidebar.button("Logout YouTube"):
        st.session_state.youtube_credentials = None
        st.session_state.youtube_api = None
        st.session_state.youtube_videos = []
        st.rerun()
    if st.session_state.reddit and st.sidebar.button("Logout Reddit"):
        st.session_state.reddit = None
        st.session_state.reddit_posts = []
        st.rerun()

# Auto-sync in background
if st.session_state.youtube_credentials or st.session_state.reddit:
    st.experimental_rerun() if time.time() - st.session_state.last_sync_time >= st.session_state.sync_interval else None
