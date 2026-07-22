#!/usr/bin/env bash

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./install.sh [InstallFolder])"
  exit 1
fi

if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" &> /dev/null; then
  echo "INFO:  Python 3.6 or higher is installed."
  python3 --version
else
  echo "ERROR: Python 3.6 or higher is required, but not found."
  exit 1
fi

if ! python3 -m venv --help &> /dev/null; then
  echo "ERROR: Python venv module is missing. You must install it in"
  echo "       order to install this service. Aborting!"
  echo "       On Debian/Ubuntu, run: apt install python3-venv"
  echo "       On RHEL/Alma/Rocky, run: dnf install python3-venv"
  echo "       On SLES/OpenSuse, run: zypper install python3-venv"
  exit 1
fi

pyinclude=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['include'])")
if grep -qiE '^(pyuwsgi|uwsgi)' src/requirements.txt; then
  echo "INFO:  requirements.txt will build (py)uwsgi into the venv;"
  echo "       checking for build prerequisites."
  if [ ! -f "$pyinclude/Python.h" ]; then
    echo "ERROR: Python development headers (Python.h) are missing. These are"
    echo "       required to build the pyuwsgi package from source. Aborting!"
    echo "       On Debian/Ubuntu, run: apt install python3-dev"
    echo "       On RHEL/Alma/Rocky, run: dnf install python3-devel"
    echo "       On SLES/OpenSuse, run: zypper install python3-devel"
    exit 1
  fi

  if ! command -v gcc &> /dev/null; then
    echo "ERROR: A C compiler (gcc) is missing. This is required to build"
    echo "       the pyuwsgi package from source. Aborting!"
    echo "       On Debian/Ubuntu, run: apt install build-essential"
    echo "       On RHEL/Alma/Rocky, run: dnf groupinstall \"Development Tools\""
    echo "       On SLES/OpenSuse, run: zypper install -t pattern devel_basis"
    exit 1
  fi
else
  echo "INFO:  requirements.txt has no (py)uwsgi entry; a system-wide uwsgi"
  echo "       installation with the Python 3 plugin will be used instead."
  if ! command -v uwsgi &> /dev/null; then
    echo "ERROR: No system-wide 'uwsgi' command found. Install it along with"
    echo "       its Python 3 plugin, or add pyuwsgi to requirements.txt to"
    echo "       have it built into the venv instead. Aborting!"
    echo "       On Debian/Ubuntu, run: apt install uwsgi uwsgi-plugin-python3"
    echo "       On RHEL/Alma/Rocky, run: dnf install uwsgi uwsgi-plugin-python3"
    echo "       On SLES/OpenSuse, run: zypper install uwsgi uwsgi-python3"
    exit 1
  fi
fi

if [ "$#" -gt 0 ] && [[ "$1" == /* ]]; then
  installfolder=$1
  echo "INFO:  Selecting provided install path: $installfolder"
elif [ "$#" -gt 0 ]; then
  echo "ERROR: The provided path must be an absolute path (starting with /)."
  exit 1
else
  installfolder="/srv/Gmonitor"
  echo "INFO:  Selecting default install path: $installfolder"
fi

if [ -d "$installfolder" ] && [ "$(find "$installfolder" -mindepth 1 -print -quit)" ]; then
  echo "CRITICAL: The selected install folder already exists and is NOT empty."
  echo "          Aborting install as to not overwrite existing files in the folder."
  echo "          Select different folder or clean files in selected folder."
  exit 1
fi

echo "INFO:  Making install directory and copying files"
mkdir -p "$installfolder"
cp -r src/* "$installfolder"
chmod +x "$installfolder/Gmonitor.py"
chmod +x "$installfolder/start_uwsgi.sh"
python3 -c "import secrets; print(secrets.token_hex(32))" > "$installfolder/.secret_key"
chmod 600 "$installfolder/.secret_key"

echo "INFO:  Installing Python virtual environment ..."
echo "       This may take a while based on your internet connection"
echo "       If this seems not to work, check you internet connection"
echo "       and try again."
python3 -m venv "$installfolder/venv"
if ! "$installfolder/venv/bin/pip" install -r "$installfolder/requirements.txt"; then
    echo "CRITICAL: pip install failed. Aborting."
    exit 1
fi

PORT=$(python3 -c "import configparser; c=configparser.ConfigParser(); c.read('$installfolder/Gmonitor.ini'); print(c.get('Server','port', fallback='8080'))")
if [ -z "$PORT" ]; then 
  PORT=8080 
fi

if command -v firewall-cmd &> /dev/null; then
  echo "INFO:  Opening Firewall port $PORT for TCP"
  echo "       To change port, edit $installfolder/Gmonitor.ini"
  echo "       and manually configure firewall"
  firewall-cmd --permanent --add-port=$PORT/tcp
  firewall-cmd --reload
else
  echo "WARNING: firewall not found or not configured"
fi

if [ "$(ps -p 1 -o comm=)" != "systemd" ]; then
  echo "WARNING: This installation script is designed for systemd-based Linux"
  echo "         distribution. To start the service on your system, you must"
  echo "         manually configure your system for service execution."
  exit 0
fi

if [ ! -f "gmonitor.service" ]; then
  echo "CRITICAL: system unit file gmonitor.service not found. Aborting systemd"
  echo "          configuration. Please configure systemd manually."
  exit 1
else
  echo "INFO:  Configuring systemd for starting the service now and at system startup"  
  cat gmonitor.service | sed "s|__InsertInstallPath__|$installfolder|g" > /etc/systemd/system/gmonitor.service
  systemctl daemon-reload
  if ! systemctl start gmonitor; then
    echo "WARNING: gmonitor service failed to start."
    echo "         Run 'journalctl -u gmonitor' to see the error logs."
  fi
  systemctl enable gmonitor
  systemctl status gmonitor
fi
