from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.auth
import google.oauth2.id_token
from google.auth.transport import requests
from google.cloud import firestore, storage
import starlette.status as status
from datetime import datetime
import local_constants


app = FastAPI()

firestore_db = firestore.Client()
firebase_request_adapter = requests.Request()

app.mount('/static', StaticFiles(directory='static'), name='static' )
templets = Jinja2Templates(directory='templates')



@app.get("/", response_class=HTMLResponse)
async def root( request : Request ) :
    id_token = request.cookies.get("token")
    error_message = None
    user_token = None
    user_token = validateFirebaseToken(id_token)

    if not user_token:
        return templets.TemplateResponse('main.html', { 'request' : request, 'user_token' : None , 'error_message' : error_message, 'user_info': None })
    
    user = getUser(user_token).get()
    timeline_tweets = timelineTweets(user_token)
    return templets.TemplateResponse('main.html', { 'request' : request, 'user_token' : user_token , 'error_message' : error_message, 'user_info': user, 'timeline_tweets' : timeline_tweets })
    


@app.post("/set-username", response_class=HTMLResponse)
async def updateUserForm ( request: Request ):
    id_token = request.cookies.get("token")
    error_message = "No error here"
    user_token = None
    user_token = validateFirebaseToken(id_token)

    if not user_token :
        return RedirectResponse("/")
    
    form = await request.form()
    
    username = form['username']

    user = getUser(user_token).get()
    existingUserWithSameUsername = firestore_db.collection('users').where('username', "==", username).get()

    if len(existingUserWithSameUsername) > 0 :
        return templets.TemplateResponse('main.html', { 'request' : request, 'user_token' : user_token , 'error_message' : error_message, 'user_info': user })

    firestore_db.collection('users').document(user_token['user_id']).set({"username" : username, "follow" : []})
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)



@app.post("/add-tweet", response_class=RedirectResponse)
async def addTweet(request: Request):

    id_token = request.cookies.get("token")
    user_token = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    user = getUser(user_token).get()
    form = await request.form()

    if form['filename'].filename == '':
        tweet_data = {
            "name" : form["tweet"].lower(),
            "username" : user.get('username'),
            "date" : datetime.now()
        }
    else:
        tweet_data = {
            "name" : form["tweet"].lower(),
            "username" : user.get('username'),
            "date" : datetime.now(),
            "filename" : form["filename"].filename
        }
        addFile(form["filename"])

    firestore_db.collection("tweet").document().set(tweet_data)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)



def validateFirebaseToken(id_token):
    if not id_token:
        return None
    user_token = None
    try:
        user_token = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
    except ValueError as err:
        print(str(err))
    return  user_token


def addFile(file):
    storage_client = storage.Client( project = local_constants.PROJECT_NAME )
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = storage.Blob(file.filename, bucket)
    blob.upload_from_file(file.file)


def blobList(prefix):
    storage_client = storage.Client( project = local_constants.PROJECT_NAME )
    return storage_client.list_blobs(local_constants.PROJECT_STORAGE_BUCKET, prefix=prefix)


def downloadBlob(filename):
    storage_client = storage.Client( project = local_constants.PROJECT_NAME )
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
    blob = bucket.get_blob(filename)
    return blob.download_as_bytes()


def getUser(user_token):
    user_ref = firestore_db.collection('users').document(user_token['user_id'])
    return user_ref


def timelineTweets(user_token) :
    try:
        user = getUser(user_token).get()
        followers = user.get("follow")
        usersFollowingCurrentUser = []
        for follower in followers:
            usersFollowingCurrentUser.append(follower)
        usersFollowingCurrentUser.append(user.get("username"))

        tweets = firestore_db.collection('tweet').where('username', "in", usersFollowingCurrentUser).order_by("date", direction=firestore.Query.DESCENDING).limit(20).get()
        return tweets
    except:
        return []


@app.get("/find-user", response_class=HTMLResponse)
async def searchUsers( request : Request ) :
    id_token = request.cookies.get("token")
    user_token = None
    error_message = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    query_ref = request.query_params
    users_ref = firestore_db.collection("users").where("username", ">=", query_ref.get("user_name"))
    users = users_ref.get()
    accounts = []

    for user in users:
        if user.id != user_token['user_id']:
            accounts.append(user)
        
    user = getUser(user_token).get()
    timeline_tweets = timelineTweets(user_token)
    return templets.TemplateResponse('main.html', { 'request' : request, 'user_token' : user_token , 'error_message' : error_message, 'user_info': user, "accounts" : accounts, 'timeline_tweets' : timeline_tweets })


@app.get("/find-tweet", response_class=HTMLResponse)
async def findTweets( request : Request ) :
    id_token = request.cookies.get("token")
    user_token = None
    error_message = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    query_ref = request.query_params
    searched_tweets_ref = firestore_db.collection("tweet").where("name", ">", query_ref.get("tweet").lower())

    user = getUser(user_token).get()
    timeline_tweets = timelineTweets(user_token)
    return templets.TemplateResponse('main.html', { 'request' : request, 'user_token' : user_token , 'error_message' : error_message, 'user_info': user, "tweets" : searched_tweets_ref.get(), 'timeline_tweets' : timeline_tweets  })


@app.get("/account/{id}", response_class=HTMLResponse)
async def userProfile( request: Request, id : str ):
    id_token = request.cookies.get("token")
    user_token = None
    error_message = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    searched_user = firestore_db.collection('users').document(id).get()
    
    tweets = firestore_db.collection('tweet').where("username", "==", searched_user.get("username")).order_by("date", direction=firestore.Query.DESCENDING).limit(10).get()
    user = getUser(user_token).get()

    following = searched_user.get('username') in user.get('follow')

    return templets.TemplateResponse('account.html', { 'request' : request, 'user_token' : user_token , 'error_message' : error_message, "user" : searched_user , 'tweets' : tweets, 'following' : following })


@app.get("/follow/{id}", response_class=RedirectResponse)
async def follow(request : Request, id :str):
    id_token = request.cookies.get("token")
    user_token = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    

    user = getUser(user_token)
    searched_user_ref = firestore_db.collection("users").document(id).get()
    searched_usename = searched_user_ref.get("username")

    following = user.get().get("follow")

    updated_followers = []
    for followed in following:
        updated_followers.append(followed)

    updated_followers.append(searched_usename)
    user.update({ "follow" : updated_followers })
    return RedirectResponse(f'/account/{searched_user_ref.id}', status_code=307)


@app.get("/unfollow/{id}", response_class=RedirectResponse)
async def unfollowAccount(request : Request, id :str):
    id_token = request.cookies.get("token")
    user_token = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    

    user = getUser(user_token)
    searched_user_ref = firestore_db.collection("users").document(id).get()
    searched_username = searched_user_ref.get("username")

    following = user.get().get("follow")
    print(following)
    print(searched_username)


    updated_followers = []
    for followed in following:
        if searched_username not in following:
            updated_followers.append(followed)

    user.update({ "follow" : updated_followers })
    return RedirectResponse(f'/account/{searched_user_ref.id}', status_code=307)


@app.get("/delete-tweet/{id}", response_class=RedirectResponse)
async def deleteTweet(request: Request, id: str):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    

    user = getUser(user_token).get()
    tweet = firestore_db.collection('tweet').document(id)

    if tweet.get().get('username') == user.get('username'):
        tweet.delete()

    return RedirectResponse('/', status_code=307)

@app.post("/download-file", response_class=Response)
async def downloadFileHandler(request : Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    form = await request.form()
    filename = form['filename']
    blobs = blobList(filename)
    file = None
    for blob in blobs:
        file = blob
        break
    Response(downloadBlob(file.name))


@app.get('/edit/{id}', response_class=HTMLResponse)
async def editTweet( request: Request, id: str ):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    tweet = firestore_db.collection('tweet').document(id).get()
    return templets.TemplateResponse('edit.html', { 'request' : request, 'user_token' : user_token ,  'tweet' : tweet })

@app.post("/update-tweet/{id}", response_class=HTMLResponse)
async def updateTweet(request: Request, id: str):
    id_token = request.cookies.get("token")
    user_token = None
    user_token = validateFirebaseToken(id_token)
    if not user_token :
        return RedirectResponse("/")
    
    user = getUser(user_token).get()
    form = await request.form()
    tweet = firestore_db.collection('tweet').document(id)
    tweet_id = tweet.get().id
    if id != tweet_id:
        return RedirectResponse("/")
    
    if 'filename' in tweet.get().to_dict():
        if form['filename'].filename == '':
            tweet_data = {
                "name" : form["tweet"].lower(),
            }
        else:
            tweet_data = {
                "name" : form["tweet"].lower(),
                "filename" : form["filename"].filename
            }
            addFile(form["filename"])
    else : 
        tweet_data = {
            "name" : form["tweet"].lower(),
        }
    
    tweet.update(tweet_data)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    
    