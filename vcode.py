#!/usr/bin/python3
# vcode.py - check your device region by IMEI or serial number
# Copyright 2025 Archeron Draconis
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import requests;
import os;
import platform;
import datetime;

def download(http, url, dest):
    with http.get(url, stream=True) as res:
        res.raise_for_status();
        with open(dest, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                f.write(chunk);
def view(file):
    if platform.system() == "Windows":
        os.system(f"start {file}", shell=True);
    elif platform.system() == "Darwin":
        os.system(f"open {file}");
    elif platform.system() == "Linux":
        os.system(f"xdg-open {file}");

http = requests.session();

keyword = input("IMEI/serial: ");

download(http, "https://buy.mi.com/en/other/getimage", "captcha.png");
view("captcha.png");
vcode = input("Captcha: ");
os.remove("captcha.png");
print();

res = http.get(f"https://buy.mi.com/en/other/checkimei?keyword={keyword}&vcode={vcode}").json();

if res["code"] == 70011:
    print("Invalid captcha code");
elif res["code"] == 70017:
    print("IMEI or S/N does not exist");
elif res["code"] == 1:
    print("Product name:", res["data"]["goods_name"]);
    print("Add time:", datetime.datetime.fromtimestamp(res["data"]["add_time"]));
    country = res["data"]["country_text"];
    print("Country:", country);
    if country == "\u4e2d\u56fd\u9999\u6e2f":
        region = "Global";
    elif country == "Russian Federation":
        region = "Russia";
    elif country == "China":
        region = "China";
    else:
        region = "Unknown region";
    print("Region:", region);
else:
    print(res);
