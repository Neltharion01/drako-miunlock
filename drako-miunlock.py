#!/usr/bin/python
# Drako-Miunlock - portable solution to unlock Xiaomi devices
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

import json;
import hashlib;
import requests;
from base64 import b64encode, b64decode;
from Cryptodome.Cipher import AES;
import hmac;
import random;
import datetime;
import usb;

def parse_url(url, key):
    # skipping to params part
    index_of_q = url.find("?");
    if index_of_q == -1: return None;
    url = url[index_of_q+1:];
    # ... and then iterating keys
    for kv in url.split("&"):
        k, v = kv.split("=");
        if k == key: return v;
    return None;
# only for base64
def urlencode(s):
    return s.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D");

# b64encode that accepts and returns str
def b64encode_s(s):
    if type(s) == str: s = s.encode();
    return b64encode(s).decode();

# it seems everything works without useragent header...
def ximihttp():
    http = requests.Session();
    http.headers["User-Agent"] = "XiaomiPCSuite";
    return http;
def ximijson(s):
    return json.loads(s.replace("&&&START&&&", "", 1));
def urlparams(args):
    return "&".join(f"{k}={v}" for k, v in args.items());

XIMI_HMAC_KEY = b"2tBeoEyJTunmWUGq7bQH2Abn0k2NhhurOaqBfyxCuLVgn4AVj7swcawe53uDUno";
XIMI_AES_IV = b"0102030405060708";

def encrypt_args(ssecurity, path, args):
    ssecurity_b = b64decode(ssecurity);
    # 1) base64 encode all nested objects
    for k, v in args.items():
        if type(v) == dict:
            args[k] = b64encode_s(json.dumps(v));
    # 2) add sign field
    data = f"POST\n{path}\n{urlparams(args)}".encode();
    args["sign"] = hmac.digest(XIMI_HMAC_KEY, data, "sha1").hex();
    # 3) encrypt all fields
    for k, v in args.items():
        n = 16 - len(v) % 16; # padding
        aes = AES.new(ssecurity_b, AES.MODE_CBC, XIMI_AES_IV);
        args[k] = b64encode_s(aes.encrypt(v.encode() + bytes([n]) * n));
    # 4) attach a final signature
    data = f"POST&{path}&{urlparams(args)}&{ssecurity}".encode();
    args["signature"] = b64encode_s(hashlib.sha1(data).digest());
    return args;
def decrypt_res(ssecurity, res):
    ssecurity_b = b64decode(ssecurity.encode());
    aes = AES.new(ssecurity_b, AES.MODE_CBC, XIMI_AES_IV);
    # 1) base64 decode response
    res = b64decode(res.encode());
    # 2) decrypt it with ssecurity key
    res = aes.decrypt(res);
    # 3) remove the padding
    padding = res[-1];
    res = res[:-padding];
    # 4) base64 decode encrypted contents
    res = b64decode(res);
    return json.loads(res);

# not secure at all, but security isn't our concern now...
ALPHABET = "abcdefghijklmnopqrstuvwxyz";
def make_nonce():
    return "".join(random.choices(ALPHABET, k=16));

EU_COUNTRYCODES = ["DE", "NO", "BE", "FI", "PT", "BG", "DK", "LT", "LU", "HR", "LV", "FR", "HU", "SE", "SI", "SK", "IE", "EE", "MT", "IS", "GR", "IT", "ES", "AT", "CY", "CZ", "PL", "LI", "RO", "NL"];
def code2region(code):
    if code in EU_COUNTRYCODES: return "Europe", "https://eu-unlock.update.intl.miui.com";
    elif code == "RU": return "Russia", "https://ru-unlock.update.intl.miui.com";
    elif code == "IN": return "India", "https://in-unlock.update.intl.miui.com";
    elif code == "CN": return "China", "https://unlock.update.miui.com";
    else: return "Global", "https://unlock.update.intl.miui.com";

class EncryptedHttp:
    def __init__(self, base, ssecurity, cookies):
        self.base = base;
        self.ssecurity = ssecurity;
        self.http = ximihttp();
        self.http.cookies.update(cookies);
    def post(self, path, data):
        # BEWARE: insertion order matters! sid should always be the last, or api will throw 401 Unauthorized error
        data["sid"] = "miui_unlocktool_client";
        data = encrypt_args(self.ssecurity, path, data);
        res = self.http.post(self.base + path, data=data);
        if res.status_code != 200: raise FailedRequestError();
        return decrypt_res(self.ssecurity, res.text);
    def post_with_nonce(self, path, data):
        res = self.post("/api/v2/nonce", {"r": make_nonce()});
        if res["code"] != 0: raise Exception("could not retrieve nonce");
        data["nonce"] = res["nonce"];
        return self.post(path, data);
class FailedRequestError(Exception): pass;

VENDOR_GOOGLE=0x18d1;
EP_READ=0x81;
EP_WRITE=0x1;

class Fastboot:
    def __init__(self, dev):
        self.dev = dev;
    def _match_fastboot(dev):
        if dev.idVendor != VENDOR_GOOGLE: return False;
        iface = dev.configurations()[0].interfaces()[0];
        # from fastboot sources
        return iface.bInterfaceClass == 0xff and iface.bInterfaceSubClass == 0x42 and iface.bInterfaceProtocol == 0x3;
    def open():
        dev = usb.core.find(custom_match=Fastboot._match_fastboot);
        if dev != None:
            return Fastboot(dev);
        else:
            return None;
    def recv(self):
        while True:
            res = bytes(self.dev.read(EP_READ, 64));
            head, data = res[:4], res[4:];
            if head == b"OKAY":
                return data.decode();
            elif head == b"FAIL":
                raise FastbootError("command failed: " + str(data));
            elif head == b"INFO":
                print("(bootloader)", data.decode());
            elif head == b"TEXT":
                print(data.decode());
            elif head == b"DATA":
                # data ends with \0, so removing last char
                return int(data.decode()[:-1], 16);
            else:
                raise FastbootError("unknown fastboot response received: " + str(res));
    def getvar(self, varname):
        self.dev.write(EP_WRITE, b"getvar:" + varname.encode());
        return self.recv();
    def download(self, data):
        self.dev.write(EP_WRITE, b"download:" + f"{len(data):08x}".encode());
        if self.recv() != len(data):
            raise FastbootError("device didn't accept data");
        self.dev.write(EP_WRITE, data);
        return self.recv();
    def rawcmd(self, cmd):
        self.dev.write(EP_WRITE, cmd.encode());
        return self.recv();
class FastbootError(Exception): pass;

class Config:
    def load():
        out = Config();
        try:
            with open("cfg.json") as f:
                cfg = json.load(f);
                out.__dict__.update(cfg);
                return out;
        except FileNotFoundError:
            return None;
    def save(self):
        with open("cfg.json", "w") as f:
            json.dump(self.__dict__, f);

# obtaining mi unlock cookies
def login():
    http = ximihttp();

    print("You have to authenicate in browser and obtain the device id");
    print("Visit this url: https://account.xiaomi.com/pass/serviceLogin?sid=unlockApi&checkSafeAddress=true&passive=false&hidden=false");
    print("After that, you will see", '{"R":"","S":"OK"}');
    print("Copy the link xiaomi redirected you to, and paste here");
    print("deviceId is contained in the \"d\" query parameter\n");
    print("Note 1: if you are already logged in, redirect will happen immediately");
    print("Note 2: if you chose verification by phone, don't be surprised when they send verification code on WhatsApp");

    device_id = None;
    while device_id == None:
        link = input("--> Paste link: ");
        device_id = parse_url(link, "d");
        if device_id == None:
            print("Could not parse your link! Make sure it contains the \"d\" parameter");

    http.cookies["deviceId"] = device_id;

    print("\nDid you close your password manager yet? You need to write your password here for second time...\n");

    ssecurity = None;
    user = None;
    while ssecurity == None:
        if user == None:
            user = input("--> Mi account id/email/phone: ");
            pw = input("--> Password: ");

        pw_md5 = hashlib.md5(pw.encode()).hexdigest().upper();
        res = http.post("https://account.xiaomi.com/pass/serviceLoginAuth2?sid=unlockApi&_json=true&passive=true&hidden=true", data={"user": user, "hash": pw_md5});
        data = ximijson(res.text);

        if data["code"] == 70016:
            print("Could not log in! Invalid user or password");
            user, pw = None, None;
            continue;

        if data["securityStatus"] == 4 and "notificationUrl" in data and "bizType=SetEmail" in data["notificationUrl"]:
            print("Xiaomi asks you to add email to your Mi Account");
            print("https://account.xiaomi.com");
            input("Hit enter when you are ready");
            continue;

        ssecurity = data["ssecurity"];
        nonce = data["nonce"];
        location = data["location"];
        uid = http.cookies["userId"];

    print("Logged into Mi Account successfully. Now logging into Mi Unlock...\n");

    digest = hashlib.sha1(f"nonce={nonce}&{ssecurity}".encode()).digest();
    client_sign = urlencode(b64encode_s(digest));
    res = http.get(location + f"&clientSign={client_sign}");
    if res.text == "" or res.json()["S"] != "OK":
        print("Could not log into Mi Unlock! Most likely, device id is invalid\n");
        return login();
    elif "serviceToken" not in res.cookies:
        print("Didn't receive service token!");
        return login();

    uid = res.cookies["userId"];
    print("Successfully logged into Mi Unlock");

    cfg = Config();
    cfg.device_id = device_id;
    cfg.ssecurity = ssecurity;
    cfg.uid = uid;
    cfg.cookies = res.cookies.get_dict();

    # this request clears all cookies...
    res = http.get("https://account.xiaomi.com/pass/user/login/region");
    region = ximijson(res.text)["data"]["region"];
    print("Account id:", uid);
    print("Account region:", code2region(region)[0], end="\n\n");
    cfg.region = region;

    return cfg;

def main():
    cfg = Config.load();
    if cfg == None:
        print("No config data found on disk! Please log in\n");
        cfg = login();
        cfg.save();
        print("Saved config to disk\n");
    else:
        print("Loaded config from disk");
        print("Account id:", cfg.uid);
        print("Account region:", code2region(cfg.region)[0]);

    fastboot = None;
    while fastboot == None:
        fastboot = Fastboot.open();
        if fastboot == None:
            print("\nPlease connect a device and hit enter.");
            res = input("Alternatively, you can type \"manual\" to perform all fastboot commands manually (for example, when fastboot doesn't work on this PC): ");
            if res == "manual": break;

    if fastboot != None:
        if fastboot.getvar("unlocked") == "yes":
            print("\nSorry, but your device is unlocked already");
            return 1;

        # TODO fastboot oem get_token variant exists?
        product = fastboot.getvar("product");
        token = fastboot.getvar("token");
        serialno = fastboot.getvar("serialno");
        print(f"Device to be unlocked: {product} {serialno}.");
        print("Make sure it is the correct one.\n");
    else:
        print("\nNow, you need to get these 2 variables from fastboot: product and token");
        print("Run these commands and paste variable value.");
        product = input("--> `fastboot getvar product`: ");
        token = input("--> `fastboot getvar token`: ");
        print("These variables are required for server to authenicate the unlocking process\n");

    enchttp = EncryptedHttp(code2region(cfg.region)[1], cfg.ssecurity, cfg.cookies);
    try:
        res = enchttp.post_with_nonce("/api/v2/unlock/device/clear", {"data": {"product": product}});
    except FailedRequestError:
        print("Token expired. Please delete cfg.json and reauthenicate");
        return 1;

    if res["code"] != 0:
        print("Could not get device status");
        return 1;

    if res["cleanOrNot"] == 1:
        print("This device CLEARS its data on unlock");
    elif res["cleanOrNot"] == -1:
        print("This device DOES NOT clear its data on unlock");

    print("A locked device is an easy target for malware which may damage your device or cause financial loss. Please unlock it to receive latest software and security patches, ensuring device safety.");

    choice = input("--> Proceed? [Y/n] ");
    print();
    if choice not in "yY":
        print("Exiting...");
        return 0;

    data = {
        "appId": "1",
        "data": {
            "clientId": "2",
            "clientVersion": "7.6.727.43",
            "language": "en",
            "operate": "unlock",
            "pcId": hashlib.md5(cfg.device_id.encode()).hexdigest(),
            "product": product,
            "region": "",
            "deviceInfo": {
                "boardVersion": "",
                "product": product,
                "socId": "",
                "deviceName": ""
            },
            "deviceToken": token
        }
    };
    res = enchttp.post_with_nonce("/api/v3/ahaUnlock", data);

    if "code" in res and res["code"] == 0:
        encrypt_data = bytes.fromhex(res["encryptData"]);
        print("Successfully received encryptData.");
        if fastboot != None:
            try:
                fastboot.download(encrypt_data);
                fastboot.rawcmd("oem unlock");
                print("Unlock successful, have a nice day!");
                print("You may want to check this: https://lineageos.org");
            except FastbootError as e:
                print("Could not unlock:", e);

        else:
            print("Now, to unlock, please run on PC with fastboot:");
            print("echo", b64encode_s(encrypt_data), "| base64 -d >encryptData");
            print("fastboot stage encryptData");
            print("fastboot oem unlock\n");
            print("Please DO NOT REBOOT the device! This will reset the unlock token!");
            print("After unlock, you may want to visit: https://lineageos.org");
            print("Have a nice day!");

    elif "descEN" in res:
        print("Xiaomi rejected your unlock attempt, code", res["code"]);
        print(f"Description: \"{res['descEN']}\"");

        if res["code"] == 20033:
            print("Xiaomi has banned you from accessing Mi Unlock. The only way to workaround that is to delete your account at https://account.xiaomi.com and create it again.");
        elif res["code"] == 20036:
            print("Please wait", res["data"]["waitHour"], "hours.");
            time = datetime.datetime.now() + datetime.timedelta(hours=res["data"]["waitHour"]);
            print("Retry unlock at", time.strftime("%a, %d %b %Y %H:%M"));
        elif res["code"] == 20038:
            print("Device is locked. Visit https://i.mi.com/mobile/find and disable \"locate device\". Also, make sure your Mi Account ids in this tool and on device are same.");
        elif res["code"] == 20041:
            print("Please add a phone number. https://account.xiaomi.com");
    else:
        print("Received unexpected response:\n");
        print(res);
        print("\nYou probably should open an issue about that (warning: response may contain sensitive data)");

if __name__ == "__main__":
    main();
