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

# Switching to my SIM.
print('* Switching SIMs.')
myEE.switchMSISDN(credentials['MyEE_DonorMSISDN'])

# Get the data usage history.
print('* Downloaded data usage history:')
print(json.dumps(myEE.dataPassHistory(), indent=4))