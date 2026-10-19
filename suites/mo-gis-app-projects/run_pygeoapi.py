"""Run real pygeoapi without a development reloader or debugger."""
from pygeoapi.flask_app import APP
APP.run(host='127.0.0.1',port=18880,debug=False,use_reloader=False,threaded=True)
