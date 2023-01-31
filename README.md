# MyEE API
Unofficial MyEE API.

Created predominantly to perform automated "Data Gifting" between family accounts on the mobile network operator EE (formerly Everything Everywhere) owned by BT Group.

Place in Crontab something like
 `#  0 0   23  *   *    cd /home/tools/MyEEDataGift/ && python3 MyEEDataGift.py &>> MyEEDataGift.log`