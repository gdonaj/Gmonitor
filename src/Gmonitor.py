#!/usr/bin/env python

import os
import configparser
import json
import threading
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory
from datetime import datetime
from collections import OrderedDict
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix

################################################################################################
# SETTINGS
################################################################################################

gDefaultSettings = {
    "validTimeout":    3900,
    "removeTimeout":   2764800,
    "maxColumns":      6,
    "showName":        True,
    "showDescription": True,
    "showLastSeen":    True,
    "demandKey":       False,
    "userpassword":    "letmesee",
    "adminpassword":   "secret",
    "keys": ["key123"]
}

def load_settings():
    if not os.path.exists(gSettingsFile):
        save_settings(gDefaultSettings)
        return dict(gDefaultSettings)
    try:
        with open(gSettingsFile, 'r') as f:
            loaded = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        loaded = {}
    merged = dict(gDefaultSettings)
    merged.update(loaded)
    return merged

def save_settings(settings_dict):
    with _inventory_lock:
        tmp_path = gSettingsFile + '.tmp'
        with open(tmp_path, 'w') as f:
            json.dump(settings_dict, f, indent=2)
        os.replace(tmp_path, gSettingsFile)

################################################################################################
# DATA INVENTORY
################################################################################################

def load_inventory():
    if not os.path.exists(gInventoryFile):
        return {}
    try:
        with open(gInventoryFile, 'r') as f:
            raw = json.load(f) 
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    for hostname, data in raw.items():
        timeStamp = data.get('timeStamp')
        if timeStamp:
            try:
                # data['timeStamp'] = datetime.fromisoformat(timeStamp)
                clean_str = str(timeStamp).replace('T', ' ').replace('Z', '')[:19]
                data['timeStamp'] = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, AttributeError):
                data['timeStamp'] = None
    
    return raw

def save_inventory():
    with _inventory_lock:
        entireColletion = {}
        for hostname, data in gINVENTORY.items():
            thisEntry = dict(data)
            timeStamp = thisEntry.get('timeStamp')
            if isinstance(timeStamp, datetime):
                thisEntry['timeStamp'] = timeStamp.isoformat()
            entireColletion[hostname] = thisEntry
        tmpFile = gInventoryFile + '.tmp'
        with open(tmpFile, 'w') as f:
            json.dump(entireColletion, f, indent=2)
        os.replace(tmpFile, gInventoryFile)

################################################################################################
# STARTUP
################################################################################################

_inventory_lock = threading.RLock()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.secret_key = os.environ.get("SECRET_KEY","super_secret_signing_key")

gConfig = configparser.ConfigParser()
gConfig.read('Gmonitor.ini')

gPort          = gConfig.getint('Server', 'port', fallback=8080)
gSettingsFile  = gConfig.get('Files', 'settings',  fallback='settings.json')
gInventoryFile = gConfig.get('Files', 'inventory', fallback='inventory.json')
gSETTINGS      = load_settings()
gINVENTORY     = load_inventory()

################################################################################################
# ROUTES
################################################################################################

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated') or not session.get('is_admin'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

################################################################################################

@app.route('/favicon.ico')
def favicon_page():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

################################################################################################

def set_bounds(value,min,max):
    if value < min:
        value = min
    if value > max:
        value = max
    return value

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings_page():

    error = None
    
    if request.method == 'POST':
        
        try:
            new_max = int(request.form.get('maxColumns', gSETTINGS['maxColumns']))
            new_valid = int(request.form.get('validTimeout', gSETTINGS['validTimeout']))
            new_remove = int(request.form.get('removeTimeout', gSETTINGS['removeTimeout']))
        except ValueError:
            error = "Timeout and column values must be numbers."

        if error is None:
            with _inventory_lock:
                gSETTINGS['maxColumns'] = set_bounds(new_max,2,10)
                gSETTINGS['validTimeout'] = set_bounds(new_valid,60,90000)
                gSETTINGS['removeTimeout'] = set_bounds(new_remove,60,31622400)
                gSETTINGS['showName'] = 'showName' in request.form
                gSETTINGS['showDescription'] = 'showDescription' in request.form
                gSETTINGS['showLastSeen'] = 'showLastSeen' in request.form
                gSETTINGS['demandKey'] = 'demandKey' in request.form
                keys_raw = request.form.get('keys', '')
                gSETTINGS['keys'] = [k.strip() for k in keys_raw.splitlines() if k.strip()]
                new_user_pw = request.form.get('userpassword', '').strip()
                new_admin_pw = request.form.get('adminpassword', '').strip()
                if new_user_pw:
                    gSETTINGS['userpassword'] = new_user_pw
                if new_admin_pw:
                    gSETTINGS['adminpassword'] = new_admin_pw
            save_settings(gSETTINGS)

    return render_template('setting.html', settings=gSETTINGS, error=error)

################################################################################################

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    
    error = None
    
    if request.method == 'POST':
        entered = request.form.get('password')
        if entered == gSETTINGS['adminpassword']:
            session.permanent = True
            session['authenticated'] = True
            session['is_admin'] = True
            return redirect(url_for('dashboard_page'))
        elif entered == gSETTINGS['userpassword']:
            session.permanent = True
            session['authenticated'] = True
            session['is_admin'] = False
            return redirect(url_for('dashboard_page'))
        error = "Invalid password."
        
    return render_template('login.html', error=error)

################################################################################################

@app.route('/logout')
def logout_page():
    session.clear()
    return redirect(url_for('login_page'))

################################################################################################

@app.route('/cleanup', methods=['GET'])
@admin_required
def cleanup_stale_page():

    with _inventory_lock:
        staleEntries = [
            entryName for entryName, entryData in gINVENTORY.items()
            if entryData.get('isStale', False)
        ]
        for entryName in staleEntries:
            del gINVENTORY[entryName]
    save_inventory()
    
    return redirect(url_for('dashboard_page'))

################################################################################################

@app.route('/')
def dashboard_page():

    if not session.get('authenticated'):
        return redirect(url_for('login_page'))

    timeNow = datetime.now()
    
    with _inventory_lock:
        changed = False
        for hostname, data in list(gINVENTORY.items()):
            timeStamp = data.get('timeStamp')
            if isinstance(timeStamp, datetime):
                timeElapsed = (timeNow - timeStamp).total_seconds()
                validLimit = data.setdefault('timeoutError', gSETTINGS['validTimeout'])
                data['isStale'] = timeElapsed > validLimit        
                removeLimit = data.get('timeoutDelete', gSETTINGS['removeTimeout'])
                if timeElapsed > removeLimit:
                    del gINVENTORY[hostname]
                    changed = True
            else:
                data['isStale'] = True

        INVENTORYsort = OrderedDict(sorted(gINVENTORY.items()))

    if changed:
        save_inventory()

    return render_template('dashboard.html', inventory=INVENTORYsort, settings=gSETTINGS, now=timeNow)

################################################################################################

@app.route('/report', methods=['POST'])
def receive_report_page():
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    if gSETTINGS.get('demandKey', False):
        provided_key = data.get('key')
        if not provided_key or provided_key not in gSETTINGS.get('keys', []):
            return jsonify({"status": "error", "message": "Invalid or missing key"}), 401

    hostname = data.get("name", "Unknown")
    
    raw_time = data.get('timeStamp')
    if isinstance(raw_time, str):
        try:
            clean_time = raw_time.replace('T', ' ').replace('Z', '')[:19]
            timeStamp = datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            timeStamp = datetime.now()
    else:
        timeStamp = datetime.now()

    data.pop('key', None)
    data['timeStamp'] = timeStamp

    with _inventory_lock:
        gINVENTORY[hostname] = data
    save_inventory()
    
    return jsonify({"status": "success"}), 200

################################################################################################
# MAIN
################################################################################################

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=gPort, debug=True)
