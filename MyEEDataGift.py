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

# Support Python3 in Python2.
from __future__ import print_function

# All the shared functions are in this package.
from shared.myee import MyEE

# This script makes heavy use of JSON parsing.
import json

# Load credentials.
with open('credentials.json', 'r') as in_file:
    credentials = json.load(in_file)

# Create a My EE object.
print('* Logging into My EE.')
myEE = MyEE(credentials['MyEE_Username'], credentials['MyEE_Password'])

# Authenticate with the data gifting page.
print('* Getting data gifting token.')
csrf = myEE.familyGiftingAuth()

# Get the data gifting allowance.
print('* Checking data gifting allowances:')
allowances = myEE.familyGiftingSubscriptionDataAllowance(csrf)

# Work out how much data can be gifted.
for subscription in allowances:
    # We are only interested in the donor MSISDN.
    if subscription['msisdn'] != credentials['MyEE_DonorMSISDN']: continue

    # Print out the limits.
    allowancePrefixText = '  - Can gift up to ' + subscription['amountRemaining']  + ' ' + subscription['amountRemainingUnits'] + ' out of '
    if subscription['isUnlimited']:
        print(allowancePrefixText + 'the 100/120 GB gifting allowance after ' + subscription['amountUsed'] + ' ' + subscription['amountUsedUnits'] + ' data usage.')
    else:
        print(allowancePrefixText + subscription['totalVolume'] + ' ' + subscription['totalVolumeUnits'] + '.')

    # Variables used to work out the maximum amount allowed to data gift.
    giftingAmountInMB = 0
    giftingDisplayString = ''

    # Take each amount that can be gifted and work out the maximum amount allowed to data gift.
    for allowedDataTransferAmount in subscription['allowedDataTransferAmounts']:
        # Is this the largest allowable data gifting amount so far?
        if allowedDataTransferAmount['giftingAmountInMB'] > giftingAmountInMB:
            giftingAmountInMB = allowedDataTransferAmount['giftingAmountInMB']
            giftingDisplayString = allowedDataTransferAmount['giftingDisplayAmount'] + ' ' + allowedDataTransferAmount['giftingDisplayUnits']

# Get the history of the family gifting.
print('* Downloaded data gifting history:')
print(json.dumps(myEE.familyGiftingHistory(csrf), indent=4))

# Perform the data gifting.
if giftingAmountInMB > 0:
    print('* Performing data gifting of ' + giftingDisplayString + '.')
    myEE.familyGifting(giftingAmountInMB, credentials['MyEE_DonorMSISDN'], credentials['MyEE_RecipientMSISDN'], csrf)