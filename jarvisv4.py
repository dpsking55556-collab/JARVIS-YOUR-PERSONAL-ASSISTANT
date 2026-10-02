# -*- coding: utf-8 -*-
"""
Jarvis v4 - Hindi voice assistant (Python 3.8, Windows, 32-bit OK)
Chalane ka tareeka:  py jarvis_v4.py
Is file ko UTF-8 me hi save karna (VS Code me default UTF-8 hota hai).
"""
import ast
import datetime
import json
import operator
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

try:
    import tkinter as tk
    from tkinter import scrolledtext
except Exception:  # sirf testing ke liye
    tk = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES_FILE = os.path.join(HERE, "jarvis_notes.txt")
CONFIG_FILE = os.path.join(HERE, "jarvis_config.json")
SHOT_DIR = os.path.join(HERE, "screenshots")

DEFAULT_CONFIG = {
    "city": "Delhi",
    "wake_word_on": True,
    # Optional AI chatbot. Khali chhodo to bhi sab chalega.
    # Key yahan file me (ya environment variable JARVIS_API_KEY me) khud daalna, kisi ko bhejna nahi.
    "api_key": "",
    "api_base": "https://api.openai.com/v1",
    "api_model": "gpt-4o-mini",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    if os.environ.get("JARVIS_API_KEY"):
        cfg["api_key"] = os.environ["JARVIS_API_KEY"]
    return cfg


# ---------------------------------------------------------------- helpers
def has(text, words):
    return any(w in text for w in words)


def http_json(url, data=None, headers=None, timeout=10):
    h = {"User-Agent": "JarvisV3/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_eval(expr):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Num):
            return n.n
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("bahut bada")
            return OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError("galat")
    return ev(ast.parse(expr, mode="eval"))


NUM_WORDS = [
    ("गुणा", "*"), ("guna", "*"), ("multiply", "*"), ("into", "*"), ("times", "*"), ("x", "*"),
    ("भाग", "/"), ("bhag", "/"), ("bhaag", "/"), ("divided by", "/"), ("divide", "/"),
    ("जोड़", "+"), ("jod", "+"), ("plus", "+"), ("प्लस", "+"), ("add", "+"),
    ("घटा", "-"), ("minus", "-"), ("माइनस", "-"), ("ghata", "-"),
    ("power", "**"),
]


def try_calculate(text):
    t = text.lower()
    for w in ["calculate", "calculator", "hisab", "hisaab", "हिसाब", "कैलकुलेट", "kitna hota hai",
              "कितना होता है", "kitne hote hain", "कितने होते हैं", "kitna hoga", "कितना होगा",
              "kya hai", "क्या है", "batao", "बताओ", "jarvis", "जार्विस"]:
        t = t.replace(w, " ")
    for w, s in NUM_WORDS:
        if w == "x":
            t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", t)
        else:
            t = t.replace(w, " %s " % s)
    t = t.replace("×", "*").replace("÷", "/")
    t = t.replace("^", "**")
    if not re.search(r"\d", t) or not re.search(r"[\+\-\*/%]", t):
        return None
    expr = re.sub(r"[^0-9\.\+\-\*/%\(\)\s]", "", t).strip()
    if not expr:
        return None
    try:
        res = safe_eval(expr)
    except ZeroDivisionError:
        return "Zero se bhaag nahi ho sakta."
    except Exception:
        return None
    if isinstance(res, float) and res == int(res) and abs(res) < 1e15:
        res = int(res)
    elif isinstance(res, float):
        res = round(res, 4)
    return "Jawab hai %s" % res


JOKES = [
    "टीचर: बताओ सबसे तेज़ चीज़ क्या है? बच्चा: रिज़ल्ट, क्योंकि आने से पहले ही पता चल जाता है।",
    "पत्नी: सुनो, मैं कैसी लग रही हूँ? पति: जैसे बैटरी, पूरी चार्ज होने पर ही अच्छी लगती हो।",
    "बेटा: पापा, मुझे सब भूल जाते हैं। पापा: कौन? बेटा: पता नहीं, भूल गया।",
    "एक आदमी ने कंप्यूटर से पूछा: तू इतना स्लो क्यों है? कंप्यूटर बोला: तुम्हारे पास मुझसे ज़्यादा टैब खुले हैं।",
    "Doctor: aapko aaram ki zaroorat hai. Patient: lekin doctor sahab, WiFi ka password kya hai?",
]

APPS = {
    "notepad": ("notepad.exe", ["notepad", "नोटपैड"]),
    "calculator": ("calc.exe", ["calculator app", "calc", "कैलकुलेटर खोल", "calculator khol", "calculator open"]),
    "paint": ("mspaint.exe", ["paint", "पेंट"]),
    "command prompt": ("cmd.exe", ["command prompt", "cmd", "कमांड प्रॉम्प्ट"]),
    "file explorer": ("explorer.exe", ["file explorer", "my computer", "this pc", "फाइल एक्सप्लोरर"]),
    "task manager": ("taskmgr.exe", ["task manager", "टास्क मैनेजर"]),
    "vs code": ("code", ["vs code", "vscode", "वीएस कोड"]),
}

SITES = [
    (["youtube", "यूट्यूब", "यूटूब"], "https://www.youtube.com", "YouTube"),
    (["gmail", "जीमेल", "email", "ईमेल"], "https://mail.google.com", "Gmail"),
    (["whatsapp", "व्हाट्सएप", "वॉट्सऐप", "व्हाट्सऐप"], "https://web.whatsapp.com", "WhatsApp Web"),
    (["instagram", "इंस्टाग्राम"], "https://www.instagram.com", "Instagram"),
    (["facebook", "फेसबुक"], "https://www.facebook.com", "Facebook"),
    (["maps", "मैप", "नक्शा"], "https://maps.google.com", "Google Maps"),
    (["google", "गूगल"], "https://www.google.com", "Google"),
]

OPEN_WORDS = ["open", "khol", "kholo", "खोल", "खोलो", "चालू", "start", "chalu", "launch"]
THANKS = ["thanks", "thank you", "shukriya", "dhanyavad", "शुक्रिया", "धन्यवाद", "थैंक"]


class Brain:
    """Saari commands yahan. GUI se alag hai, isliye aasani se test hoti hai."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.history = []

    # --- entry point: (reply_text, optional_action) ---
    def reply(self, raw):
        text = raw.strip()
        t = text.lower()
        t = re.sub(r"^(hey |ok |ओके )?(jarvis|जार्विस|जारविस|जर्विस)[,\s]*", "", t).strip()
        if not t:
            return "जी, बोलिए।"

        if has(t, ["exit", "quit", "band karo", "बंद करो", "alvida", "अलविदा", "bye", "बाय"]):
            return "__EXIT__"

        if has(t, ["note likh", "note kar", "नोट लिख", "नोट कर", "याद रख", "yaad rakh", "add note", "note:"]):
            return self.add_note(text)
        if has(t, ["notes padh", "note padh", "नोट पढ़", "नोट्स पढ़", "mere notes", "मेरे नोट", "show notes"]):
            return self.read_notes()

        if has(t, ["screenshot", "स्क्रीनशॉट", "screen shot", "स्क्रीन शॉट"]):
            return self.screenshot()

        if has(t, ["time", "samay", "समय", "baje", "बजे", "टाइम"]) and not has(t, ["date"]):
            n = datetime.datetime.now()
            return "अभी %d बजकर %02d मिनट हुए हैं।" % (n.hour % 12 or 12, n.minute)
        if has(t, ["date", "tarikh", "tareekh", "तारीख", "तारीख़", "aaj kaun sa din", "kaunsa din", "आज कौन सा दिन", "day today", "दिन"]):
            n = datetime.datetime.now()
            days = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
            months = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
            return "आज %s, %d %s %d है।" % (days[n.weekday()], n.day, months[n.month - 1], n.year)

        if has(t, ["joke", "chutkula", "चुटकुला", "जोक", "hasao", "हँसाओ", "हंसाओ"]):
            return random.choice(JOKES)

        if has(t, ["weather", "mausam", "mausum", "मौसम", "वेदर"]):
            return self.weather(t)

        calc = try_calculate(t)
        if calc and not has(t, ["wikipedia", "विकिपीडिया"]):
            return calc

        if has(t, ["search", "serch", "सर्च", "google par", "गूगल पर", "khojo", "खोजो", "dhundho", "ढूंढो"]):
            q = self.strip(t, ["search", "serch", "सर्च करो", "सर्च", "google par", "गूगल पर", "khojo", "खोजो",
                               "dhundho", "ढूंढो", "karo", "करो", "for", "about"])
            if q:
                webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(q))
                return "गूगल पर '%s' खोज रहा हूँ।" % q
        if has(t, ["youtube par", "यूट्यूब पर", "youtube pe", "play ", "gana", "गाना", "song"]):
            q = self.strip(t, ["youtube par", "यूट्यूब पर", "youtube pe", "play", "chalao", "चलाओ", "gana", "गाना",
                               "song", "bajao", "बजाओ", "karo", "करो"])
            if q:
                webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
                return "YouTube पर '%s' खोल रहा हूँ।" % q

        if has(t, OPEN_WORDS):
            for name, (cmd, keys) in APPS.items():
                if has(t, keys):
                    return self.open_app(name, cmd)
            for keys, url, nm in SITES:
                if has(t, keys):
                    webbrowser.open(url)
                    return "%s खोल रहा हूँ।" % nm

        if has(t, ["wikipedia", "विकिपीडिया", "kaun hai", "कौन है", "kaun the", "कौन थे", "kya hai", "क्या है",
                   "kya hota hai", "क्या होता है", "ke baare mein", "के बारे में", "ke bare me", "bare me batao",
                   "who is", "what is", "tell me about"]):
            topic = self.strip(t, ["wikipedia", "विकिपीडिया", "kaun hai", "कौन है", "kaun the", "कौन थे", "kya hai",
                                   "क्या है", "kya hota hai", "क्या होता है", "ke baare mein", "के बारे में",
                                   "ke bare me", "bare me", "batao", "बताओ", "bataiye", "बताइए", "who is",
                                   "what is", "tell me about", "mujhe", "मुझे", "par", "पर", "ke", "के", "ka", "का"])
            if topic:
                ans = self.wiki(topic)
                if ans:
                    return ans

        small = self.small_talk(t)
        if small:
            return small

        ai = self.ask_ai(text)
        if ai:
            return ai

        return random.choice([
            "माफ़ कीजिए, यह मुझे समझ नहीं आया। आप 'मदद' बोलकर देख सकते हैं कि मैं क्या-क्या कर सकता हूँ।",
            "हम्म, यह मेरे बस की बात नहीं है अभी। कुछ और पूछिए?",
            "मैं अभी सीख रहा हूँ। समय, तारीख, मौसम, विकिपीडिया या चुटकुला आज़माइए।",
        ])

    # --- pieces ---
    @staticmethod
    def strip(t, words):
        for w in sorted(words, key=len, reverse=True):
            t = re.sub(r"(?<![\w\u0900-\u097F])" + re.escape(w) + r"(?![\w\u0900-\u097F])", " ", t)
        return re.sub(r"\s+", " ", t).strip(" ?.,!।")

    def small_talk(self, t):
        if has(t, ["help", "madad", "मदद", "kya kar sakte", "क्या कर सकते", "kya kya"]):
            return ("मैं ये कर सकता हूँ: समय, तारीख, मौसम, चुटकुला, विकिपीडिया से जानकारी "
                    "('अब्दुल कलाम कौन थे'), हिसाब ('5 गुणा 8'), नोट लिखना/पढ़ना, स्क्रीनशॉट, "
                    "ऐप खोलना ('नोटपैड खोलो'), वेबसाइट खोलना ('यूट्यूब खोलो'), गूगल/यूट्यूब पर खोजना।")
        if has(t, ["hello", "hi", "hey", "namaste", "नमस्ते", "नमस्कार", "हैलो", "हेलो", "हाय"]) and len(t) < 25:
            return random.choice(["नमस्ते! बताइए, क्या सेवा करूँ?", "हैलो! मैं सुन रहा हूँ।"])
        if has(t, ["kaise ho", "कैसे हो", "kaisa hai", "कैसे हैं", "how are you", "kya haal", "क्या हाल"]):
            return "मैं बिल्कुल बढ़िया हूँ, शुक्रिया! आप कैसे हैं?"
        if has(t, ["tumhara naam", "तुम्हारा नाम", "aapka naam", "आपका नाम", "who are you", "tum kaun", "तुम कौन", "आप कौन"]):
            return "मैं जार्विस हूँ, आपका पर्सनल असिस्टेंट।"
        if has(t, ["kisne banaya", "किसने बनाया", "who made you"]):
            return "मुझे देवांश ने बनाया है।"
        if has(t, THANKS):
            return "आपका स्वागत है!"
        if has(t, ["i love you", "love you", "pyaar", "प्यार"]):
            return "अरे वाह! मैं तो बस एक प्रोग्राम हूँ, पर आपकी बात दिल को छू गई।"
        if has(t, ["good morning", "सुप्रभात", "subah"]):
            return "सुप्रभात! आपका दिन शानदार हो।"
        if has(t, ["good night", "शुभ रात्रि", "shubh ratri", "शुभरात्रि"]):
            return "शुभ रात्रि! मीठे सपने।"
        if has(t, ["i am sad", "udas", "उदास", "bore", "बोर"]):
            return "अरे, चिंता मत कीजिए। चाहें तो मैं एक चुटकुला सुनाऊँ? बस 'चुटकुला सुनाओ' बोलिए।"
        return None

    def add_note(self, text):
        note = re.split(r"(?i)note likh(?:o|na)?|note kar(?:o)?|नोट लिखो|नोट लिख|नोट करो|नोट कर|yaad rakho|याद रखो|याद रख|add note|note:", text, maxsplit=1)
        body = (note[-1] if len(note) > 1 else text).strip(" :,.-")
        body = re.sub(r"(?i)^(ki|कि)\s+", "", body)
        if not body:
            return "क्या लिखूँ? जैसे: 'नोट लिखो कल दूध लाना है'।"
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write("%s - %s\n" % (datetime.datetime.now().strftime("%d-%m-%Y %H:%M"), body))
        return "नोट लिख लिया: %s" % body

    def read_notes(self):
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception:
            return "अभी कोई नोट नहीं है।"
        if not lines:
            return "अभी कोई नोट नहीं है।"
        return "आपके आख़िरी नोट:\n" + "\n".join(lines[-5:])

    def screenshot(self):
        try:
            from PIL import ImageGrab
        except Exception:
            return "स्क्रीनशॉट के लिए Pillow चाहिए। Terminal में चलाओ: py -m pip install pillow"
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            path = os.path.join(SHOT_DIR, "shot_%s.png" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            ImageGrab.grab().save(path)
            return "स्क्रीनशॉट सेव हो गया: %s" % path
        except Exception as e:
            return "स्क्रीनशॉट नहीं ले पाया: %s" % e

    def open_app(self, name, cmd):
        try:
            if os.name == "nt":
                subprocess.Popen(cmd, shell=True)
            else:
                subprocess.Popen([cmd])
            return "%s खोल रहा हूँ।" % name
        except Exception as e:
            return "%s नहीं खुल पाया: %s" % (name, e)

    def wiki(self, topic):
        for lang in ("hi", "en"):
            try:
                s = http_json("https://%s.wikipedia.org/w/api.php?action=opensearch&limit=1&format=json&search=%s"
                              % (lang, urllib.parse.quote(topic)))
                if not s[1]:
                    continue
                title = s[1][0]
                d = http_json("https://%s.wikipedia.org/api/rest_v1/page/summary/%s"
                              % (lang, urllib.parse.quote(title.replace(" ", "_"))))
                ext = d.get("extract", "")
                if ext:
                    parts = re.split(r"(?<=[।\.])\s", ext)
                    return " ".join(parts[:2]).strip()
            except Exception:
                continue
        return None

    def weather(self, t):
        city = self.strip(t, ["weather", "mausam", "mausum", "मौसम", "वेदर", "kaisa hai", "कैसा है", "aaj ka",
                              "आज का", "ka", "का", "ki", "की", "me", "में", "mein", "batao", "बताओ", "today",
                              "in", "hai", "है", "kya", "क्या"])
        city = city or self.cfg.get("city", "Delhi")
        try:
            g = http_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&name=" + urllib.parse.quote(city))
            r = g["results"][0]
            w = http_json("https://api.open-meteo.com/v1/forecast?current_weather=true&latitude=%s&longitude=%s"
                          % (r["latitude"], r["longitude"]))["current_weather"]
            codes = {0: "आसमान साफ़ है", 1: "ज़्यादातर साफ़", 2: "थोड़े बादल", 3: "बादल छाए हैं", 45: "कोहरा",
                     48: "कोहरा", 51: "हल्की बूँदाबाँदी", 61: "हल्की बारिश", 63: "बारिश", 65: "तेज़ बारिश",
                     80: "बौछारें", 95: "आँधी-तूफ़ान"}
            desc = codes.get(w.get("weathercode"), "")
            return "%s में अभी तापमान %s°C है, हवा %s km/h। %s" % (r["name"], w["temperature"], w["windspeed"], desc)
        except Exception:
            return "'%s' का मौसम नहीं मिल पाया। इंटरनेट देखो, या शहर का नाम साफ़ बोलो।" % city

    def ask_ai(self, text):
        key = self.cfg.get("api_key", "").strip()
        if not key:
            return None
        self.history.append({"role": "user", "content": text})
        self.history = self.history[-10:]
        msgs = [{"role": "system", "content": "You are Jarvis, a friendly assistant. Always reply in simple Hindi (Devanagari), short."}] + self.history
        try:
            body = json.dumps({"model": self.cfg["api_model"], "messages": msgs}).encode("utf-8")
            d = http_json(self.cfg["api_base"].rstrip("/") + "/chat/completions", data=body,
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}, timeout=25)
            ans = d["choices"][0]["message"]["content"].strip()
            self.history.append({"role": "assistant", "content": ans})
            return ans
        except Exception as e:
            return "AI से जवाब नहीं मिला (%s)। Key/इंटरनेट जाँचिए।" % e


# ---------------------------------------------------------------- voice out
class Speaker:
    """pyttsx3 ko apne thread me chalate hain, taaki GUI na atke."""

    def __init__(self):
        self.q = queue.Queue()
        self.speaking = False
        self.hindi = False
        self.ready = threading.Event()
        if pyttsx3 is not None:
            threading.Thread(target=self.run, daemon=True).start()
            self.ready.wait(5)

    def run(self):
        try:
            eng = pyttsx3.init()
            for v in eng.getProperty("voices"):
                blob = (v.name + " " + str(v.id) + " " + str(getattr(v, "languages", ""))).lower()
                if "hindi" in blob or "hemant" in blob or "kalpana" in blob or "hi-in" in blob:
                    eng.setProperty("voice", v.id)
                    self.hindi = True
                    break
            eng.setProperty("rate", 165)
        except Exception:
            self.ready.set()
            return
        self.ready.set()
        while True:
            txt = self.q.get()
            self.speaking = True
            try:
                eng.say(txt)
                eng.runAndWait()
            except Exception:
                pass
            self.speaking = False

    def say(self, txt):
        if pyttsx3 is None:
            return
        has_dev = re.search(r"[\u0900-\u097F]", txt) is not None
        if has_dev and not self.hindi:
            return  # Hindi voice nahi hai, English voice Devanagari galat padhegi
        self.q.put(txt[:400])


# ---------------------------------------------------------------- GUI
class App:
    WAKE = ["jarvis", "jarvish", "jarwis", "जार्विस", "जारविस", "जर्विस", "जार्विज", "जरविस", "जर्वीस", "जारविज़", "जार्विश"]

    def __init__(self):
        self.cfg = load_config()
        self.brain = Brain(self.cfg)
        self.speaker = Speaker()
        self.ui_q = queue.Queue()
        self.busy = threading.Lock()
        self.stop_bg = None
        self.rec = sr.Recognizer() if sr else None
        if self.rec:
            self.rec.pause_threshold = 0.8

        self.root = tk.Tk()
        self.root.title("JARVIS | Personal assistant")
        self.root.geometry("960x820")
        self.root.minsize(760, 680)
        self.root.configure(bg="#03080d")
        self._closing = False
        self._pulse = 0
        self._wake_enabled = bool(self.cfg.get("wake_word_on", True))
        self.build_ui()

        self.add("sys", "Jarvis v4 तैयार है। 'मदद' लिखो या बोलो।")
        if sr is None:
            self.add("sys", "SpeechRecognition नहीं मिला - सिर्फ़ typing चलेगी। (py -m pip install SpeechRecognition pyaudio)")
        if pyttsx3 is None:
            self.add("sys", "pyttsx3 नहीं मिला - आवाज़ नहीं आएगी। (py -m pip install pyttsx3)")
        elif not self.speaker.hindi:
            self.add("sys", "Windows में Hindi voice नहीं मिली, इसलिए हिंदी जवाब सिर्फ़ लिखे जाएँगे। "
                            "Settings > Time & Language > Speech > Add voices > Hindi डालो।")
        self.root.after(150, self.pump)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        if self.wake_var.get():
            self.start_wake()

    # --- UI plumbing (sab UI kaam main thread me) ---
    def add(self, tag, text):
        self.ui_q.put(("add", tag, text))

    def pump(self):
        if self._closing:
            return
        try:
            while True:
                item = self.ui_q.get_nowait()
                if item[0] == "add":
                    self.add_bubble(item[1], item[2])
                elif item[0] == "status":
                    self.status.config(text=item[1] or "Ready. Type a command or press the microphone.")
                    active = "सुन रहा" in item[1] or "समझ रहा" in item[1]
                    self.mic_caption.config(text="LISTENING" if active else "TAP TO SPEAK")
                elif item[0] == "show":
                    self.show_window()
                elif item[0] == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    # --- Tkinter-only interface; no images, themes or extra UI packages ---
    def build_ui(self):
        self.bg = "#03080d"
        self.panel = "#07131e"
        self.cyan = "#55dfff"
        self.font = "Nirmala UI" if os.name == "nt" else "Noto Sans Devanagari UI"
        self.bubbles = []
        shell = tk.Frame(self.root, bg=self.bg)
        shell.pack(fill="both", expand=True, padx=28, pady=20)

        top = tk.Frame(shell, bg=self.bg)
        top.pack(fill="x")
        tk.Label(top, text="J / PERSONAL ASSISTANT", font=("Segoe UI", 10, "bold"),
                 bg=self.bg, fg="#5f9db4").pack(side="left")
        mode = "VOICE + TEXT" if self.rec else "TEXT MODE"
        tk.Label(top, text=mode + "  /  V4.0", font=("Segoe UI", 10),
                 bg=self.bg, fg=self.cyan).pack(side="right")
        tk.Frame(shell, height=1, bg="#173445").pack(fill="x", pady=(12, 0))

        hero = tk.Frame(shell, bg=self.bg)
        hero.pack(fill="x", pady=(10, 12))
        self.core = tk.Canvas(hero, width=194, height=180, bg=self.bg,
                              highlightthickness=0)
        self.core.pack(side="left", padx=(0, 20))
        identity = tk.Frame(hero, bg=self.bg)
        identity.pack(side="left", fill="both", expand=True)
        tk.Label(identity, text="J A R V I S", font=("Segoe UI", 38, "bold"),
                 bg=self.bg, fg=self.cyan, anchor="w").pack(fill="x", pady=(25, 0))
        tk.Label(identity, text="YOUR VOICE. YOUR COMMAND.", font=("Segoe UI", 10, "bold"),
                 bg=self.bg, fg="#8cbbcd", anchor="w").pack(fill="x", pady=(0, 9))
        tk.Label(identity, text="Hindi voice assistant  /  Built for Devansh",
                 font=("Segoe UI", 10), bg=self.bg, fg="#607f92", anchor="w").pack(fill="x")
        self.clock = tk.Label(identity, text="", font=("Consolas", 10),
                              bg=self.bg, fg="#7ba5ba", anchor="w")
        self.clock.pack(fill="x", pady=(10, 0))

        title = tk.Frame(shell, bg=self.bg)
        title.pack(fill="x", pady=(0, 10))
        tk.Label(title, text="CONVERSATION", font=("Segoe UI", 10, "bold"),
                 bg=self.bg, fg="#badbe8").pack(side="left")
        tk.Label(title, text="Hindi / English", font=("Segoe UI", 9),
                 bg=self.bg, fg="#607f92").pack(side="right")
        chat = tk.Frame(shell, bg=self.panel, highlightbackground="#163449", highlightthickness=1)
        chat.pack(fill="both", expand=True)
        chat.configure(height=90)
        chat.pack_propagate(False)
        self.chat_canvas = tk.Canvas(chat, bg=self.panel, highlightthickness=0)
        scrollbar = tk.Scrollbar(chat, orient="vertical", command=self.chat_canvas.yview,
                                 width=10, bg="#123044", troughcolor=self.panel,
                                 activebackground="#28799a", bd=0)
        scrollbar.pack(side="right", fill="y")
        self.chat_canvas.pack(side="left", fill="both", expand=True)
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)
        self.chat_body = tk.Frame(self.chat_canvas, bg=self.panel)
        self.chat_window = self.chat_canvas.create_window((0, 0), window=self.chat_body, anchor="nw")
        self.chat_body.bind("<Configure>", self.update_scroll)
        self.chat_canvas.bind("<Configure>", self.resize_chat)
        self.chat_canvas.bind("<MouseWheel>", self.scroll_chat)
        self.chat_body.bind("<MouseWheel>", self.scroll_chat)
        self.chat_canvas.bind("<Button-4>", lambda e: self.chat_canvas.yview_scroll(-3, "units"))
        self.chat_canvas.bind("<Button-5>", lambda e: self.chat_canvas.yview_scroll(3, "units"))

        shortcuts = tk.Frame(shell, bg=self.bg)
        shortcuts.pack(fill="x", pady=(12, 10))
        tk.Label(shortcuts, text="TRY", bg=self.bg, fg="#607f92",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
        for label, command in [("Help", "मदद"), ("Time", "समय बताओ"),
                               ("5 x 8", "5 गुणा 8"), ("Notes", "मेरे नोट")]:
            self.make_button(shortcuts, label, lambda t=command: self.quick_command(t)).pack(side="left", padx=(0, 8))

        controls = tk.Frame(shell, bg=self.bg)
        controls.pack(fill="x")
        mic_area = tk.Frame(controls, bg=self.bg)
        mic_area.pack(side="right", padx=(18, 0))
        self.mic = tk.Canvas(mic_area, width=90, height=90, bg=self.bg,
                             highlightthickness=0, cursor="hand2", takefocus=1)
        self.mic.pack()
        for r, color, width in [(43, "#102c3e", 2), (37, "#176a88", 1), (32, "#55dfff", 2)]:
            self.mic.create_oval(45-r, 45-r, 45+r, 45+r, outline=color, width=width,
                                 fill="#092332" if r == 32 else "")
        self.mic.create_oval(39, 25, 51, 49, fill=self.cyan, outline=self.cyan)
        self.mic.create_arc(33, 34, 57, 59, start=180, extent=180, style="arc", outline=self.cyan, width=2)
        self.mic.create_line(45, 59, 45, 66, fill=self.cyan, width=2)
        self.mic.create_line(38, 66, 52, 66, fill=self.cyan, width=2)
        self.mic.bind("<Button-1>", lambda e: self.listen_click())
        self.mic.bind("<Return>", lambda e: self.listen_click())
        self.mic.bind("<space>", lambda e: self.listen_click())
        self.mic.bind("<FocusIn>", lambda e: self.mic.configure(highlightthickness=1, highlightbackground=self.cyan))
        self.mic.bind("<FocusOut>", lambda e: self.mic.configure(highlightthickness=0))
        self.mic_caption = tk.Label(mic_area, text="TAP TO SPEAK", font=("Segoe UI", 8, "bold"),
                                    bg=self.bg, fg=self.cyan)
        self.mic_caption.pack()
        self.listen_btn = self.mic

        input_area = tk.Frame(controls, bg=self.bg)
        input_area.pack(side="left", fill="both", expand=True, pady=(13, 0))
        tk.Label(input_area, text="COMMAND INPUT", font=("Segoe UI", 8, "bold"), bg=self.bg,
                 fg="#607f92", anchor="w").pack(fill="x", pady=(0, 6))
        entry_row = tk.Frame(input_area, bg="#0a1b29", highlightbackground="#28516a", highlightthickness=1)
        entry_row.pack(fill="x")
        self.entry = tk.Entry(entry_row, font=(self.font, 12), bg="#0a1b29", fg="#e0f4ff",
                              insertbackground=self.cyan, relief="flat", bd=0,
                              selectbackground="#195773")
        self.entry.pack(side="left", fill="x", expand=True, padx=12, ipady=11)
        self.entry.bind("<Return>", lambda e: self.send())
        self.make_button(entry_row, "SEND  >", self.send, bright=True).pack(side="right", padx=7, pady=7)

        footer = tk.Frame(shell, bg=self.bg)
        footer.pack(fill="x", pady=(10, 0))
        self.wake_var = tk.BooleanVar(value=self._wake_enabled)
        tk.Checkbutton(footer, text="Wake word: 'Jarvis'", variable=self.wake_var,
                       command=self.toggle_wake, font=("Segoe UI", 9), bg=self.bg, fg="#8cbbcd",
                       selectcolor="#0b2433", activebackground=self.bg, activeforeground=self.cyan,
                       bd=0, highlightthickness=0, cursor="hand2").pack(side="left")
        tk.Label(footer, text="ENTER TO SEND", font=("Segoe UI", 8),
                 bg=self.bg, fg="#607f92").pack(side="right")
        self.status = tk.Label(shell, text="Ready. Type a command or press the microphone.",
                               font=(self.font, 9), bg=self.bg, fg="#8cbbcd", anchor="w")
        self.status.pack(fill="x", pady=(5, 0))
        self.entry.focus_set()
        self.animate_core()

    def make_button(self, parent, text, command, bright=False):
        bg = "#10445b" if bright else "#0b1d2c"
        return tk.Button(parent, text=text, command=command, font=("Segoe UI", 9, "bold"),
                         bg=bg, fg=self.cyan if bright else "#9abecd", activebackground="#185873",
                         activeforeground="#e8faff", relief="flat", bd=0, padx=13, pady=6,
                         cursor="hand2", highlightthickness=1, highlightbackground="#18384b")

    def quick_command(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.send()

    def animate_core(self):
        if self._closing:
            return
        import math
        c = self.core
        c.delete("all")
        cx, cy = 97, 90
        for radius, color, width in [(82, "#0b2739", 1), (76, "#124c67", 2),
                                      (63, "#14647e", 2), (57, "#55dfff", 2), (44, "#164e67", 1)]:
            c.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, outline=color, width=width)
        for angle in range(0, 360, 30):
            a = math.radians(angle)
            c.create_line(cx+65*math.cos(a), cy+65*math.sin(a),
                          cx+72*math.cos(a), cy+72*math.sin(a), fill="#55dfff", width=3)
        for shift in (0, 180):
            c.create_arc(cx-82, cy-82, cx+82, cy+82, start=self._pulse+shift,
                         extent=58, style="arc", outline="#55dfff", width=3)
        c.create_polygon(cx, cy-30, cx-29, cy+22, cx+29, cy+22,
                         outline="#73eaff", fill="#0c3346", width=2)
        c.create_polygon(cx, cy-19, cx-18, cy+14, cx+18, cy+14,
                         outline="#d0f8ff", fill="#55dfff", width=1)
        self._pulse = (self._pulse + 2) % 360
        self.clock.config(text=datetime.datetime.now().strftime("%d %b %Y  /  %H:%M:%S"))
        self.root.after(90, self.animate_core)

    def add_bubble(self, tag, text):
        row = tk.Frame(self.chat_body, bg=self.panel)
        row.pack(fill="x", padx=18, pady=(10, 2))
        if tag == "sys":
            label = tk.Label(row, text="SYSTEM  /  " + text, bg=self.panel, fg="#88a7b9",
                             font=(self.font, 9), justify="left", anchor="w")
            label.pack(fill="x", pady=3)
        else:
            me = tag == "me"
            bubble = tk.Frame(row, bg="#12354a" if me else "#0c2030",
                              highlightbackground="#235975" if me else "#193a50", highlightthickness=1)
            bubble.pack(side="right" if me else "left", anchor="e" if me else "w")
            tk.Label(bubble, text="YOU" if me else "JARVIS", font=("Segoe UI", 8, "bold"),
                     bg=bubble["bg"], fg="#93c5d9" if me else self.cyan, anchor="w").pack(fill="x", padx=14, pady=(9, 2))
            label = tk.Label(bubble, text=text, bg=bubble["bg"], fg="#deeff7", font=(self.font, 11),
                             justify="left", anchor="w")
            label.pack(padx=14, pady=(0, 11), anchor="w")
        label.configure(wraplength=max(240, int(self.chat_canvas.winfo_width() * 0.75)-40))
        label.bind("<MouseWheel>", self.scroll_chat)
        self.bubbles.append(label)
        self.root.after_idle(self.scroll_to_bottom)

    def update_scroll(self, event=None):
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def resize_chat(self, event):
        self.chat_canvas.itemconfigure(self.chat_window, width=event.width)
        for label in self.bubbles:
            label.configure(wraplength=max(240, int(event.width * 0.75)-40))
        self.update_scroll()

    def scroll_to_bottom(self):
        if not self._closing:
            self.update_scroll()
            self.chat_canvas.yview_moveto(1.0)

    def scroll_chat(self, event):
        if event.delta:
            self.chat_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def show_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(400, lambda: self.root.attributes("-topmost", False))
        try:
            self.root.focus_force()
            self.entry.focus_set()
        except Exception:
            pass

    def quit(self):
        self._closing = True
        try:
            if self.stop_bg:
                self.stop_bg(wait_for_stop=False)
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)

    # --- commands ---
    def handle(self, text, from_voice=False):
        self.add("me", text)
        ans = self.brain.reply(text)
        if ans == "__EXIT__":
            self.add("bot", "अलविदा!")
            self.speaker.say("अलविदा")
            time.sleep(1.5)
            self.ui_q.put(("quit",))
            return
        self.add("bot", ans)
        self.speaker.say(ans)

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        threading.Thread(target=self.handle, args=(text,), daemon=True).start()

    # --- mic ---
    def listen_click(self):
        if self.rec is None:
            self.add("sys", "SpeechRecognition install नहीं है।")
            return
        threading.Thread(target=self.listen_once, daemon=True).start()

    def pause_bg(self):
        if self.stop_bg:
            try:
                self.stop_bg(wait_for_stop=True)
            except Exception:
                pass
            self.stop_bg = None

    def listen_once(self):
        if not self.busy.acquire(blocking=False):
            return
        resume = self._wake_enabled
        try:
            self.pause_bg()
            self.ui_q.put(("status", "सुन रहा हूँ... बोलिए"))
            try:
                with sr.Microphone() as src:
                    self.rec.adjust_for_ambient_noise(src, duration=0.5)
                    audio = self.rec.listen(src, timeout=6, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                self.ui_q.put(("status", "कुछ सुनाई नहीं दिया।"))
                return
            except Exception as e:
                self.add("sys", "माइक में दिक्कत: %s" % e)
                self.ui_q.put(("status", ""))
                return
            self.ui_q.put(("status", "समझ रहा हूँ..."))
            try:
                text = self.rec.recognize_google(audio, language="hi-IN")
            except sr.UnknownValueError:
                self.add("bot", "माफ़ कीजिए, सुनाई नहीं दिया। फिर से बोलिए।")
                self.ui_q.put(("status", ""))
                return
            except Exception as e:
                self.add("sys", "इंटरनेट/Google की दिक्कत: %s" % e)
                self.ui_q.put(("status", ""))
                return
            self.ui_q.put(("status", ""))
            self.handle(text, True)
        finally:
            self.busy.release()
            if resume and self._wake_enabled:
                self.start_wake()

    # --- wake word ---
    def toggle_wake(self):
        self._wake_enabled = bool(self.wake_var.get())
        self.cfg["wake_word_on"] = self._wake_enabled
        if self.wake_var.get():
            self.start_wake()
        else:
            self.pause_bg()
            self.add("sys", "Wake word बंद।")

    def start_wake(self):
        if self.rec is None or self.stop_bg is not None:
            return
        try:
            mic = sr.Microphone()
            with mic as src:
                self.rec.adjust_for_ambient_noise(src, duration=0.5)
            self.stop_bg = self.rec.listen_in_background(mic, self.wake_cb, phrase_time_limit=4)
            self.ui_q.put(("status", "'Jarvis' सुनने के लिए तैयार (माइक चालू)"))
        except Exception as e:
            self.stop_bg = None
            self.add("sys", "Wake word शुरू नहीं हुआ (माइक/pyaudio?): %s" % e)

    def wake_cb(self, recognizer, audio):
        if self.speaker.speaking or self.busy.locked():
            return
        heard = ""
        for lang in ("hi-IN", "en-IN"):
            try:
                heard += " " + recognizer.recognize_google(audio, language=lang).lower()
            except Exception:
                pass
        if heard and any(w in heard for w in self.WAKE):
            self.ui_q.put(("show",))
            self.add("sys", "Wake word सुना: '%s'" % heard.strip())
            # "jarvis time batao" - saath me command ho to seedha chalao
            rest = heard
            for w in self.WAKE:
                rest = rest.replace(w, " ")
            rest = rest.strip()
            if len(rest) > 3:
                threading.Thread(target=self.handle, args=(rest,), daemon=True).start()
            else:
                self.speaker.say("जी, बोलिए")
                self.add("bot", "जी, बोलिए।")
                threading.Thread(target=self.listen_once, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if tk is None:
        print("tkinter nahi mila. Python dobara install karo (tcl/tk ke saath).")
        sys.exit(1)
    App().run()
