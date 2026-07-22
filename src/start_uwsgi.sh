#!/usr/bin/env bash
cd "$(dirname "$0")"
export SECRET_KEY="$(cat .secret_key)"
PORT=$(python3 -c "import configparser; c=configparser.ConfigParser(); c.read('Gmonitor.ini'); print(c.get('Server', 'port', fallback='8080'))")
echo "Starting server on port $PORT..."

if [ -x "venv/bin/uwsgi" ]; then
    # pyuwsgi was installed into the venv (default) - use it directly
    exec venv/bin/uwsgi --http "0.0.0.0:$PORT" --wsgi-file Gmonitor.py --callable app --processes 2 --threads 2
else
    # fall back to a system-wide uwsgi install, pointed at this venv's
    # site-packages via --virtualenv. Note: the plugin name below
    # ("python3") may need adjusting depending on your distro's uwsgi
    # packaging (e.g. some name it python36).
    exec uwsgi --http "0.0.0.0:$PORT" --wsgi-file Gmonitor.py --callable app \
        --virtualenv "$(pwd)/venv" --plugin python3 --processes 2 --threads 2
fi
