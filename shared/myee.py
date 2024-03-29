#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of MyEE-API <https://github.com/Matthew1471/MyEE-API>
# Copyright (C) 2023 Matthew1471!
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# We set a cookiejar policy.
import http.cookiejar

# The login form (now hosted on Azure AD B2C) now relies on JavaScript.
import json
import re

# Third party library to make HTTP(S) requests; "pip install requests" if getting import errors.
import requests

# Third party library to parse (X)HTML; "pip install beautifulsoup4" if getting import errors.
from bs4 import BeautifulSoup

class MyEE:

    # My EE Web Application.
    myAccountHost = 'https://ee.co.uk'

    # The Azure Active Directory B2C server.
    azureB2CHost = 'https://auth.ee.co.uk'

    # This prevents the requests module from creating its own user-agent (and ask to not be included in analytics).
    stealthyHeaders = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0', 'DNT':'1'}

    def __init__(self, email, password):
        # Session supports keep-alives but we disable cookie persistence (EE clutters requests with a LOT of cookies).
        self.requestsSession = requests.Session()
        self.requestsSession.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

        # We need to be assigned CSRF and state tokens from the login page *before* we can login.
        settingsJSON = self.getSession()

        # Authenticate with My EE.
        if not self.login(settingsJSON, email, password):
            raise ValueError('Failed to login to My EE.')

    def extractSettingsJSON(self, content):
        # We obtain the login form details from the JavaScript of the login page as text.
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
        response = self.requestsSession.get(url='https://id.ee.co.uk/id/login', headers=MyEE.stealthyHeaders, allow_redirects=False)

        # We get an EE ID Web Session ID.
        self.EEIDWEBSESSIONID = response.cookies['EEIDWEBSESSIONID']

        # We perform the API Gateway authorize and get bounced to the Azure Active Directory B2C Auth login.
        response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # Azure Active Directory B2C uses some cookies (https://learn.microsoft.com/en-us/azure/active-directory-b2c/cookie-definitions) which a Session object will automatically persist, also HTTP Keep-Alives will be enabled.
        self.azureADSession = requests.Session()

        # Get an Azure Active Directory B2C authorization code (see https://learn.microsoft.com/en-us/azure/active-directory-b2c/authorization-code-flow)
        response = self.azureADSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # EE uses this special URL to validate a session.
        correlationText = re.search('^<!-- CorrelationId: (?P<CorrelationID>.*?) -->', response.text, flags=re.MULTILINE)
        self.azureADSession.get(url=self.azureB2CHost + '/telemetry?c=' + correlationText.groups('CorrelationID')[0], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # Get the latest SETTINGS JSON.
        return self.extractSettingsJSON(response.text)

    def login(self, settingsJSON, username, password):
        stealthyHeadersForm = MyEE.stealthyHeaders
        stealthyHeadersForm.update({'X-CSRF-TOKEN' : settingsJSON['csrf']})

        # We perform the Azure AD B2C login (Stage #1, https://learn.microsoft.com/en-us/azure/active-directory-b2c/self-asserted-technical-profile) and get a 200 (appears to be an MS bug where tx and csrf is not URL Encoded.. we faithfully replicate this).
        response = self.azureADSession.post(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/SelfAsserted?tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=stealthyHeadersForm, data={'request_type':'RESPONSE', 'signInName':username}, allow_redirects=False)
        if response.text != '{"status":"200"}': return False

        # Then we "confirm" our session.
        response = self.azureADSession.get(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/api/' + settingsJSON['api'] + '/confirmed?csrf_token=' + settingsJSON['csrf'] + '&tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=MyEE.stealthyHeaders, allow_redirects=False)

        # Get the latest updated SETTINGS JSON.
        settingsJSON = self.extractSettingsJSON(response.text)

        # Update the CSRF Token.
        stealthyHeadersForm.update({'X-CSRF-TOKEN' : settingsJSON['csrf']})

        # We perform the Azure AD B2C login (Stage #2, https://learn.microsoft.com/en-us/azure/active-directory-b2c/self-asserted-technical-profile) and get a 200 (appears to be a MS bug where tx and csrf is not URL Encoded.. we faithfully replicate this).
        response = self.azureADSession.post(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/SelfAsserted?tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=stealthyHeadersForm, data={'request_type':'RESPONSE', 'signInName':username, 'password':password}, allow_redirects=False)
        if response.text != '{"status":"200"}': return False

        # Then we "confirm" our session.
        response = self.azureADSession.get(url=self.azureB2CHost + settingsJSON['hosts']['tenant'] + '/api/' + settingsJSON['api'] + '/confirmed?csrf_token=' + settingsJSON['csrf'] + '&tx=' + settingsJSON['transId'] + '&p=' + requests.utils.quote(settingsJSON['hosts']['policy']), headers=MyEE.stealthyHeaders, allow_redirects=False)

        # Now perform an API Gateway login to EE ID.
        callbackURL, self.OPBS, self.SID = self.loginToAPIGateway(response.text)

        # We request the EE ID Auth URL and get sent to the EE ID Dashboard.
        response = self.requestsSession.get(url=callbackURL, headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

        # The EEIDWEBSESSIONID has changed now we are authenticated.
        self.EEIDWEBSESSIONID = response.cookies['EEIDWEBSESSIONID']

        # EE ID Dashboard redirects us to "MyAccount".
        response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'EEIDWEBSESSIONID':self.EEIDWEBSESSIONID}, allow_redirects=False)

        # We request "myaccount.ee.co.uk/app" and get bounced to the "ee.co.uk/app".
        response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # We request the "ee.co.uk/app".
        response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # The MYACCOUNTSESSIONID has now been set.
        self.MyAccountSessionID = response.cookies['MYACCOUNTSESSIONID']

        # API Gateway authorize to "MyAccount".
        response = self.requestsSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, cookies={'OPBS':self.OPBS, 'SID':self.SID}, allow_redirects=False)

        # Azure AD B2C Authorize again.
        response = self.azureADSession.get(url=response.headers['Location'], headers=MyEE.stealthyHeaders, allow_redirects=False)

        # Login to API Gateway.
        callbackURL, _, _ = self.loginToAPIGateway(response.text)

        # "MyAccount" Authorize.
        response = self.requestsSession.get(url=callbackURL, headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False)

        # This is the only cookie required for the My EE session.
        if 'MYACCOUNTSESSIONID' in response.cookies:
            # The MYACCOUNTSESSIONID has changed.
            self.MyAccountSessionID = response.cookies['MYACCOUNTSESSIONID']

            # This CSRF token is used for a limited number of HTTP POST end-points in "MyAccount".
            self.MyAccountCSRFToken = response.cookies['X-XSRF-MYACCOUNT-TOKEN']

            # Abort following the further redirects to the My EE dashboard as we only want to be logged in.
            return True
        else:
            # The session cookie was not found. Login failed.
            return False

    def accountsummary(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/accountsummary', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def addOnsAvailableData(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/add-ons-available-data', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def alerts(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/alerts', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def basic(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/basic', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def cTnPicker(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/ctnpicker', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def dataPassHistory(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/datapass-history', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def extraChargesDetails(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/extra-charges-details', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def extraChargesTotal(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/extra-charges-total', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def familyGiftingAuth(self):
        # Need to get the CSRF token.
        response = self.requestsSession.get(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False)

        # We use BeautifulSoup to parse the returned HTML.
        soup = BeautifulSoup(response.text, 'html.parser')

        # Get a reference to the data gifting form (there is no ID to search for and this URL has actually moved).
        giftDataForm = soup.find('form', {'action': '/app/family-gifting?fa=giftData'})

        # Get the hidden HTML form CSRF Input value.
        return giftDataForm.find(id='csrf').attrs['value']

    def familyGiftingHistory(self, csrf):
        # Send the request (with the CSRF token).
        return self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=showMoreGiftingHistory', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, data={'csrf':csrf}, allow_redirects=False).json()

    def familyGiftingSubscriptionDataAllowance(self, csrf):
        # Send the request (with the CSRF token).
        return self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=subscriptionDataAllowance', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, data={'csrf':csrf}, allow_redirects=False).json()

    def familyGifting(self, dataTransferMB, supplierCtn, consumerCtn, csrf):
        # Send the request (with the CSRF token).
        response = self.requestsSession.post(url=MyEE.myAccountHost + '/plans-subscriptions/mobile/data-gifting?fa=giftData', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, data={'supplierCtn':supplierCtn, 'consumerCtn':consumerCtn, 'dataTransferMB':dataTransferMB, 'csrf':csrf}, allow_redirects=True)
        return (response.status_code == 200 and ('Data Gifting successful' in response.text))

    def freeDataUsage(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/freedata-usage', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def myAddressPayM(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/my-address-paym', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def otherAllowances(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/other-allowances', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def paymentHistory(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/payment-history', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def planBill(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/plan-bill', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def plansAndDevicesDetails(self, startPos=0, endPos=4):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/plans-and-devices-details?from=' + str(startPos) + '&to=' + str(endPos), headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, allow_redirects=False).json()

    def roles(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/roles', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def spendCap(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/spendcap', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()

    def switchMSISDN(self, switchMsisdn):
        # Send the request (with the CSRF token).
        response = self.requestsSession.post(url=MyEE.myAccountHost + '/app/api/switchmsisdn', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, data={'switchMsisdn':switchMsisdn, 'csrf':self.MyAccountCSRFToken}, allow_redirects=True)
        return (response.status_code == 200 and ('Switch ctn successfully done.' in response.text))

    def usageData(self, startPos=0, endPos=4):
        # Send the request (although this API does not appear to list details on which subscription each item is for).
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/usagedata?from=' + str(startPos) + '&to=' + str(endPos), headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MYACCOUNTSESSIONID}, allow_redirects=False).json()

    def usageDetails(self):
        # Send the request.
        return self.requestsSession.get(url=MyEE.myAccountHost + '/app/api/usage-details', headers=MyEE.stealthyHeaders, cookies={'MYACCOUNTSESSIONID':self.MyAccountSessionID}, allow_redirects=False).json()