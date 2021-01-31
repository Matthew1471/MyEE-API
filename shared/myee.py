#!/usr/bin/env python

# Third party library; "pip install requests" if getting import errors.
import requests

# We need to parse (X)HTML.
from bs4 import BeautifulSoup

class MyEE:

 # My EE Web Application.
 myEEHost = 'https://myaccount.ee.co.uk'

 # This prevents the requests module from creating its own user-agent (and ask to not be included in analytics).
 stealthyHeaders = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:85.0) Gecko/20100101 Firefox/85.0', 'DNT':'1'}

 def __init__(self, email, password):
  # We need to be assigned CSRF and requestID tokens *before* we can login.
  csrf, requestId = self.getSession()

  # Authenticate with MY EE.
  if not self.login(csrf, requestId, email, password):
   raise ValueError('Failed to login to My EE.')

 def getSession(self):
  # First the client requests the My EE login page but gets sent to the API authorization stage at https://api.ee.co.uk/v1/identity/authorize?client_id=xx&scope=openid+profile+email&redirect_uri=https%3A%2F%2Fid.ee.co.uk%2Fauth&nonce=xx&state=xx&acr_values=L2&response_type=code..
  myEELoginResponse = requests.get(url='https://id.ee.co.uk/id/login', headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We get an EE ID Web Session ID.
  self.EEIDWEBSESSIONID = myEELoginResponse.cookies['EEIDWEBSESSIONID']

  # We perform the API authorize and get bounced to the ID login at https://id.ee.co.uk/login?requestId=xx&state=xx.
  authorizeIDResponse = requests.get(url=myEELoginResponse.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We get a CSRF token for the login page.
  self.csrfToken = authorizeIDResponse.cookies['csrfToken']

  # We perform the ID login but this time with an EEIDWEBSESSIONID we get bounced back to the original My EE login server (https://id.ee.co.uk:443/id/login).
  redirectResponse = requests.get(url=authorizeIDResponse.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # Request the login page (with the EEIDWEBSESSIONID) as there's 2 hidden HTML form input values that are important to authenticate.
  loginPage = requests.get(url=redirectResponse.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # We use BeautifulSoup to parse the returned HTML.
  soup = BeautifulSoup(loginPage.text, 'html.parser')

  # Get a reference to the login form.
  loginForm = soup.find(id='userInformationForm')

  # Get the hidden HTML form Input values.
  return loginForm.find(id='csrf').attrs['value'], loginForm.find(id='requestId').attrs['value']

 def login(self, csrf, requestId, username, password):
  payload = {
             'csrf':csrf,
             'requestId':requestId,
             'username':username,
             'password':password,
            }

  # We perform the login and get redirected to an auth URL (or an error like https://id.ee.co.uk/login?requestId=xx&error=auth_locked&captchaRequired=true&error_description=account is locked).
  response = requests.post(url='https://api.ee.co.uk/v1/identity/authorize/login', headers=MyEE.stealthyHeaders, cookies={'csrfToken':self.csrfToken}, data=payload, allow_redirects=False)

  try:
   # Python 3
   from urllib.parse import urlparse, parse_qs
  except ImportError:
   # Python 2
   from urlparse import urlparse, parse_qs

  parsedLocation = urlparse(response.headers['Location'])
  parsedQuerystrings = parse_qs(parsedLocation.query)

  # If there is an error querystring then an error occurred.
  if 'error' in parsedQuerystrings:
   raise ValueError('Failed to login to My EE (' + str(parsedQuerystrings['error']) + ').')

  # We capture the OpenID Connect Provider Browser State and Session ID cookie.
  self.OPBS = response.cookies['OPBS']
  self.SID = response.cookies['SID']

  # We request the auth URL (https://id.ee.co.uk/auth?code=xx&state=xx&session_state=xx) and get sent to the dashboard.
  response = requests.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # The EEIDWEBSESSIONID has changed.
  self.EEIDWEBSESSIONID = response.cookies['EEIDWEBSESSIONID']

  # https://id.ee.co.uk/id/dashboard
  response = requests.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # https://myaccount.ee.co.uk/app
  response = requests.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # The MYACCOUNTSESSIONID has been set.
  self.MYACCOUNTSESSIONID = response.cookies['MYACCOUNTSESSIONID']

  # https://api.ee.co.uk/v1/identity/authorize?response_type=code&scope=openid&client_id=xx&redirect_uri=https://myaccount.ee.co.uk/app/auth&acr_values=L2&state=xx&nonce=xx
  response = requests.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'OPBS':self.OPBS, 'SID':self.SID},allow_redirects=False)

  # https://myaccount.ee.co.uk/app/auth?code=xx&state=xx&session_state=xx
  response = requests.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, allow_redirects=False)

  # This is the only cookie required for the My EE session.
  if 'MYACCOUNTSESSIONID' in response.cookies:

   # The MYACCOUNTSESSIONID has changed.
   self.MYACCOUNTSESSIONID = response.cookies['MYACCOUNTSESSIONID']

   # Abort early following the redirects to My EE as we only need to be logged in.
   return True
  else:
   # The session cookie was not found. Login failed.
   return False

 def familyGiftingAuth(self):
  # Need to get the CSRF token.
  response = requests.get(url=MyEE.myEEHost + '/app/family-gifting', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, allow_redirects=False)

  # We use BeautifulSoup to parse the returned HTML.
  soup = BeautifulSoup(response.text, 'html.parser')

  # Get a reference to the data gifting form.
  giftDataForm = soup.find(id='giftDataForm')

  # Get the hidden HTML form CSRF Input value.
  return giftDataForm.find(id='csrf').attrs['value']

 def familyGiftingHistory(self, csrf):
  # Send the request (with the CSRF token).
  return requests.post(url=MyEE.myEEHost + '/app/family-gifting?fa=showMoreGiftingHistory', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, data={'csrf':csrf}, allow_redirects=False).json()

 def familyGiftingSubscriptionDataAllowance(self, csrf):
  # Send the request (with the CSRF token).
  return requests.post(url=MyEE.myEEHost + '/app/family-gifting?fa=subscriptionDataAllowance', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, data={'csrf':csrf}, allow_redirects=False).json()

 def familyGifting(self, giftingAmountInMB, donorMsisdn, recipeintMsisdn, csrf):
  # Send the request (with the CSRF token).
  payload = {
             'fa':'giftData',
             'giftingAmountInMB':giftingAmountInMB,
             'donorMsisdn': donorMsisdn,
             'recipientMsisdn':recipeintMsisdn,
             'csrf':csrf
             }
  response = requests.post(url=MyEE.myEEHost + '/app/family-gifting', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, data=payload, allow_redirects=True)
  return (response.status_code == 200 and ('Data Gifting successful' in response.text))