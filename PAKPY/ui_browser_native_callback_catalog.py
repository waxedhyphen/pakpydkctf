"""Classification and deterministic policies for DKCTF Scaleform native callbacks.

The catalog intentionally describes preview behavior, not the original game's host ABI.
Unknown callbacks remain isolated and side-effect free.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CallbackSpec:
    name: str
    category: str
    behavior: str
    return_policy: str = "undefined"
    description: str = ""


def compact_name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


_DATA_READ = {
    "getdatavalue", "fgetdatavalue", "readdatavalue", "getvalue", "getdictionary",
    "getislandsummaryentry",
}
_DATA_WRITE = {
    "setdatavalue", "fsetdatavalue", "writedatavalue", "initdatavalue",
    "finitdatavalue", "notifydatavalue", "filldatadictionary",
}
_DATA_LISTEN = {"listenfordata"}
_AUDIO = {"playsound", "debugsoundplay", "effectssetting", "musicsetting"}
_TELEMETRY = {
    "logevent", "errorevent", "miiverseautoposts", "miiversespoilerposts",
    "miiversedisplayposts", "domiiversepost", "shownewautopost", "debugdoautopost",
}
_CONTROLLER = {
    "isdynamiccontrollermodeactive", "getprimarycontrollertype",
    "getcontrollertypefromplayer", "isplayer1controlleridx", "isplayer2controlleridx",
    "setmodeandcontrollers", "setreassigningcontrollerindices",
    "setplayer1controllermotionenabled", "setplayer2controllermotionenabled",
    "setplayer1controllermode", "setplayer2controllermode",
    "startcontrollerswap", "stopcontrollerswap", "enteredmodeselectscreen",
}
_SAVE = {
    "newsavegame", "selectsavegame", "copysavegame", "deletesavegame",
    "populatesavedata", "initslotdata", "setisfunkymode",
    "setfirsttimeselectingfunkycomplete", "setfirsttimeopeninginventorycomplete",
    "settrophykeydisplayed", "settrophykeyrevealed", "sethardmodedisplayed",
    "setfullycompleteddisplayed", "sethardmoderevealed", "setfullycompleterevealed",
    "setballooncount", "setcurrentworld",
}
_SHOP = {
    "shopevent", "getshoptext", "selectshopitem", "purchaseshopitem",
    "getfigurinestatus", "getnewfigurine", "getuitext", "ishealthboostactive",
}
_EXTRAS = {
    "stopextras", "startextras", "startextrastype", "stopextrastype",
    "startextrascategory", "stopextrascategory", "startextrasitem", "stopextrasitem",
    "getextrasunlockstate", "getextrascategoryunlocked", "getisnewextraitem",
    "clearisnewextraitem", "getisnewextracategory", "clearisnewextracategory",
    "chooseextrasimage", "playcreditssequence", "startload", "startunload", "isunitloaded",
}
_LEADERBOARD = {
    "startfillingleaderboard", "fillleaderboard", "createleaderboardentry",
    "cancelqueries", "posttoleaderboard", "internetposttime", "fetchreplay",
    "inittransitiontoreplay", "isinleaderboardreplay", "isinleaderboardreplay",
    "setistimeattackonline", "internetpromptabouttimeattack",
}
_NAVIGATION = {
    "preparefortransition", "transitionstate", "activatetransition", "activatelevelload",
    "initleveltransition", "initgametransition", "initfrontendtransition",
    "initworldtransition", "initareatransition", "activatehud", "activateshell",
    "activatemastershell", "activatemap", "activateinventoryselect",
    "activateextrasviewer", "activatedeathscreen", "activatecamera",
    "enterpause", "exitpause", "quittofrontend", "continuelevel", "retrylevel",
    "replaylevel", "gameoverretry", "gameoverquit", "thankyoufadecomplete",
    "settransparencyregion",
    "eolbeatupcomplete", "activatecurrentnode", "moveindirection",
}
_LIFECYCLE = {
    "areswfsloaded", "initialize", "enteredtitlescreen", "exitedtitlescreen",
    "hideprompt", "showprompt", "shouldprompt", "timeattackpromptreturn",
    "activatehealthboost", "activatelevelcomplete", "activatetrophydialog",
}
_GAMEPLAY_EVENTS = {
    "eolresultsevent", "bonusevent", "beatupevent", "eolbeatupevent",
    "eolbeatupmultiplier", "gameoverevent", "thankyouevent", "shopevent",
    "consolidateinventoryitems", "setplayer1inventory", "setplayer2inventory",
    "updatecharactertypes", "checkaddballoons",
}

_DESCRIPTIONS = {
    "getdatavalue": "Reads a preview data-dictionary value or an active game-state mock.",
    "setdatavalue": "Writes only to the current movie's isolated preview data store.",
    "filldatadictionary": "Creates the named preview dictionaries without contacting the game.",
    "listenfordata": "Registers a bounded preview subscription descriptor.",
    "playsound": "Queues an audio request for inspection; no audio device is opened.",
    "logevent": "Stores a bounded telemetry record locally and performs no upload.",
    "preparefortransition": "Records a pending transition in preview state.",
    "transitionstate": "Updates the preview transition state machine.",
    "areswfsloaded": "Returns true so UI initialization can proceed in the standalone viewer.",
    "newsavegame": "Creates or replaces a preview-only save-slot record.",
    "selectsavegame": "Selects a preview save slot without touching files.",
    "purchaseshopitem": "Updates only preview shop state; no persistent inventory changes occur.",
    "getextrasunlockstate": "Returns the configurable preview unlock state.",
    "fillleaderboard": "Creates a deterministic local leaderboard placeholder.",
}


def _prefix_policy(key):
    if key.startswith(("is", "has", "can", "should", "are")):
        return "false"
    if key.startswith("get"):
        return "undefined"
    if key.startswith(("set", "clear", "start", "stop", "activate", "init", "prepare", "enter", "exit", "select", "choose", "copy", "delete", "new", "populate", "fill", "update", "play", "post", "retry", "continue", "quit")):
        return "true"
    return "undefined"


def callback_spec(name):
    text = str(name or "")
    key = compact_name(text)
    category = "unknown"
    behavior = "log-only"
    policy = _prefix_policy(key)
    if key in _DATA_READ:
        category, behavior, policy = "data-read", "preview-data", "base"
    elif key in _DATA_WRITE:
        category, behavior, policy = "data-write", "preview-data", "base"
    elif key in _DATA_LISTEN:
        category, behavior, policy = "data-listen", "preview-subscription", "true"
    elif key in _AUDIO or "sound" in key or key.startswith("music"):
        category, behavior, policy = "audio", "queue-only", "true"
    elif key in _TELEMETRY or key.startswith(("log", "telemetry")):
        category, behavior, policy = "telemetry", "local-log", "undefined"
    elif key in _CONTROLLER or "controller" in key:
        category, behavior = "controller", "preview-controller"
    elif key in _SAVE or "savegame" in key or key.startswith("setfirsttime"):
        category, behavior = "save/profile", "preview-save"
    elif key in _SHOP or "shop" in key or "figurine" in key:
        category, behavior = "shop", "preview-shop"
    elif key in _EXTRAS or "extras" in key:
        category, behavior = "extras", "preview-extras"
    elif key in _LEADERBOARD or "leaderboard" in key or "replay" in key:
        category, behavior = "leaderboard", "preview-leaderboard"
    elif key in _NAVIGATION or any(word in key for word in ("transition", "activate", "pause")):
        category, behavior = "navigation", "preview-navigation"
    elif key in _LIFECYCLE:
        category, behavior = "lifecycle", "preview-lifecycle"
    elif key in _GAMEPLAY_EVENTS or key.endswith("event"):
        category, behavior, policy = "gameplay-event", "preview-event", "true"
    return CallbackSpec(
        text, category, behavior, policy,
        _DESCRIPTIONS.get(key, "Preview-only deterministic handling; no host process is called."),
    )


KNOWN_CATEGORIES = (
    "data-read", "data-write", "data-listen", "navigation", "controller",
    "save/profile", "shop", "extras", "leaderboard", "audio", "telemetry",
    "lifecycle", "gameplay-event", "unknown",
)
