#!/usr/bin/env python

# The login form (now hosted on Azure AD B2C) now relies on JavaScript.
import re
import json

# We set a cookie policy.
from http.cookiejar import DefaultCookiePolicy

# Third party library to make HTTP(S) requests; "pip install requests" if getting import errors.
import requests

# Third party library to parse (X)HTML; "pip install beautifulsoup4" if getting import errors.
from bs4 import BeautifulSoup

class MyEE:

 # My EE Web Application.
 myAccountHost = 'https://myaccount.ee.co.uk'
 azureB2CHost = 'https://auth.ee.co.uk'

 # This prevents the requests module from creating its own user-agent (and ask to not be included in analytics).
 stealthyHeaders = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0', 'DNT':'1'}

 def __init__(self, email, password):
  # Session supports keep-alives but we disable cookie persistence (EE clutters requests with a LOT of cookies).
  self.requestsSession = requests.Session()
  self.requestsSession.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))

  # We need to be assigned CSRF and state tokens from the login page *before* we can login.
  settingsJSON = self.getSession()

  # Authenticate with MY EE.
  if not self.login(settingsJSON, email, password):
   raise ValueError('Failed to login to My EE.')

 def extractSettingsJSON(self, content):
  # We obtain the login form details from the JavaScript of the login form as text.
  settingsText = re.search('^var SETTINGS = (?P<Settings>.*?);', content, flags=re.MULTILINE)

  # Then we convert it to JSON so it is more accessible.
  return json.loads(settingsText.groups('Settings')[0])

 def loginToAPIGateway(self, content):
  # We use BeautifulSoup to parse the returned HTML.
  soup = BeautifulSoup(content, 'html.parser')

  # Get the codes from the form.
  form = soup.find('form')
  actionURL = form.attrs.get('action')
  state = form.find('input', {'id': 'state'}).get('value')
  code = form.find('input', {'id': 'code'}).get('value')

  # Perform an API Gateway login.
  response = self.requestsSession.post(url=actionURL, headers=MyEE.stealthyHeaders, data={'state':state, 'code':code}, allow_redirects=False)

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
   raise ValueError('Failed to login to API Gateway (' + str(parsedQuerystrings['error']) + ').')

  # This should return a callback URI, OpenID Connect Provider Browser State and Session ID cookie.
  return response.headers['Location'], response.cookies['OPBS'], response.cookies['SID']

 def getSession(self):
  # First the client requests the My EE login page but gets sent to the API Gateway authorization page.
  myEELoginResponse = self.requestsSession.get(url='https://id.ee.co.uk/id/login', headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We get an EE ID Web Session ID.
  self.EEIDWEBSESSIONID = myEELoginResponse.cookies['EEIDWEBSESSIONID']

  # We perform the API Gateway authorize and get bounced to the Azure Active Directory B2C Auth login.
  authorizeIDResponse = self.requestsSession.get(url=myEELoginResponse.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # Azure Active Directory B2C uses some cookies (https://learn.microsoft.com/en-us/azure/active-directory-b2c/cookie-definitions) which a Session object will automatically persist, also HTTP Keep-Alives will be enabled.
  self.azureADSession = requests.Session()

  # Get an Azure Active Directory B2C authorization code (see https://learn.microsoft.com/en-us/azure/active-directory-b2c/authorization-code-flow)
  loginPage = self.azureADSession.get(url=authorizeIDResponse.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # EE uses this special URL to validate a session.
  correlationText = re.search('^<!-- CorrelationId: (?P<CorrelationID>.*?) -->', loginPage.text, flags=re.MULTILINE)
  self.azureADSession.get(url=self.azureB2CHost + '/telemetry?c=' + correlationText.groups('CorrelationID')[0], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # Get the latest SETTINGS JSON.
  return self.extractSettingsJSON(loginPage.text)

 def login(self, settingsJSON, username, password):
  stealthyHeadersForm = MyEE.stealthyHeaders
  stealthyHeadersForm.update({'X-CSRF-TOKEN' : settingsJSON['csrf']})

  # We perform the Azure AD B2C login (Stage #1, https://learn.microsoft.com/en-us/azure/active-directory-b2c/self-asserted-technical-profile) and get a 200 (appears to be an MS bug where tx and csrf is not URL Encoded.. we faithfully replicate this).
  response = self.azureADSession.post(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/SelfAsserted?tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=stealthyHeadersForm, data={'request_type':'RESPONSE', 'signInName':username, 'password':password}, allow_redirects=False)
  if response.text != '{"status":"200"}': return False

  # Then we "confirm" our session.
  response = self.azureADSession.get(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/api/' + settingsJSON['api'] + '/confirmed?rememberMe=false&csrf_token=' + settingsJSON['csrf'] + '&tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=MyEE.stealthyHeaders, allow_redirects=False)

  # Get the latest updated SETTINGS JSON.
  settingsJSON = self.extractSettingsJSON(response.text)

  # Update the CSRF Token.
  stealthyHeadersForm.update({'X-CSRF-TOKEN' : settingsJSON['csrf']})

  # We perform the Azure AD B2C login (Stage #2, https://learn.microsoft.com/en-us/azure/active-directory-b2c/self-asserted-technical-profile) and get a 200 (appears to be a MS bug where tx and csrf is not URL Encoded.. we faithfully replicate this).
  response = self.azureADSession.post(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/SelfAsserted?tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=stealthyHeadersForm, data={'request_type':'RESPONSE', 'signInName':username, 'password':password}, allow_redirects=False)
  if response.text != '{"status":"200"}': return False

  # Then we "confirm" our session.
  response = self.azureADSession.get(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/api/' + settingsJSON['api'] + '/confirmed?rememberMe=false&csrf_token=' + settingsJSON['csrf'] + '&tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=MyEE.stealthyHeaders, allow_redirects=False)

  # Now perform an API Gateway login to EE ID.
  callbackURL, self.OPBS, self.SID = self.loginToAPIGateway(response.text)

  # We request the EE ID Auth URL and get sent to the EE ID Dashboard.
  response = self.requestsSession.get(url=callbackURL, headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # The EEIDWEBSESSIONID has changed.
  self.EEIDWEBSESSIONID = response.cookies['EEIDWEBSESSIONID']

  # EE ID Dashboard redirects us to "MyAccount".
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

  # We request "MyAccount" but alas there's another token we need first... there's a queue system for busy periods (looks like QueueIT - https://queue-it.com/developers/how-queue-it-works/)?
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We ask QueueIT for a queue token.
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We should get granted a proper queue token from "MyAccount" when we pass the queue information in the querystring.
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # We need to enumerate the cookies to find the one we are interested in (as the cookie key can change).
  for cookie in response.cookies:

   # Only interested in the QueueIT token.
   if (cookie.name.startswith('QueueITAccepted-')):
       self.QueueITToken = cookie
       break

  # If there is no QueueIT token by this point then we cannot continue.
  if not self.QueueITToken:
   raise ValueError('Failed to login to My EE (Failed to get token from QueueIT)')

  # We request "MyAccount" but this time with queue cookie approval.
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={self.QueueITToken.name:self.QueueITToken.value}, allow_redirects=False)

  # The MYACCOUNTSESSIONID has now been set.
  self.MYACCOUNTSESSIONID = response.cookies['MYACCOUNTSESSIONID']

  # API Gateway authorize to "MyAccount".
  response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'OPBS':self.OPBS, 'SID':self.SID}, allow_redirects=False)

  # Azure AD B2C Authorize again.
  response = self.azureADSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

  # Login to API Gateway.
  callbackURL, _, _ = self.loginToAPIGateway(response.text)

  # "MyAccount" Authorize.
  response = self.requestsSession.get(url=callbackURL, headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, allow_redirects=False)

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
  response = self.requestsSession.get(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID, self.QueueITToken.name:self.QueueITToken.value}, allow_redirects=False)

  # We use BeautifulSoup to parse the returned HTML.
  soup = BeautifulSoup(response.text, 'html.parser')

  # Get a reference to the data gifting form DIV (there is no ID to search for and this URL is actually old).
  giftDataForm = soup.find('form', {'action': '/app/family-gifting?fa=giftData'})

  # Get the hidden HTML form CSRF Input value.
  return giftDataForm.find(id='csrf').attrs['value']

 def familyGiftingHistory(self, csrf):
  # Send the request (with the CSRF token).
  return self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=showMoreGiftingHistory', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID, self.QueueITToken.name:self.QueueITToken.value}, data={'csrf':csrf}, allow_redirects=False).json()

 def familyGiftingSubscriptionDataAllowance(self, csrf):
  # Send the request (with the CSRF token).
  return self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=subscriptionDataAllowance', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID, self.QueueITToken.name:self.QueueITToken.value}, data={'csrf':csrf}, allow_redirects=False).json()

 def familyGifting(self, dataTransferMB, supplierCtn, consumerCtn, csrf):
  # Send the request (with the CSRF token).
  payload = {
             'supplierCtn':supplierCtn,
             'consumerCtn':consumerCtn,
             'dataTransferMB':dataTransferMB,
             'csrf':csrf
             }
  response = self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=giftData', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID, self.QueueITToken.name:self.QueueITToken.value}, data=payload, allow_redirects=True)
  return (response.status_code == 200 and ('Data Gifting successful' in response.text))