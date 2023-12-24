import re
from flask import Flask, request, send_from_directory, render_template, Response, send_file
from pathlib import Path

import requests
import xmltodict

import pynetbox
import json

app = Flask(__name__, template_folder="templates")
current_dir = Path(__file__)

SERIAL_NUM_RE = re.compile(r'PID:(?P<product_id>\w+),VID:(?P<hw_version>\w+),SN:(?P<serial_number>\w+)')

session = requests.Session()
session.verify = False

nb = pynetbox.api(
    'https://192.168.88.20',
    token='a2c0d29623b5eef6e06ee0dbee9cd3e06d0d2300'
)

nb.http_session = session

def work_request(host, type="device_info"):
    url = f"http://{host}/pnp/WORK-REQUEST"
    with open(current_dir / f"{type}.xml") as f:
        data = f.read()
    return requests.post(url, data)

def get_device_info(host):
    url = f"http://{host}/pnp/WORK-REQUEST"

@app.route('/test-xml')
def test_xml():
    result = render_template('load_config.xml', correlator_id="123", config_filename="test.cfg", udi="123")
    return Response(result, mimetype='text/xml')

@app.route('/')
def root():
    return 'Hello Stream!'

@app.route('/configs/<path:path>')
def serve_configs(path):
    return send_from_directory('configs', path)

@app.route('/config/provision.cfg')
def config():
  return render_template('provision.cfg')

@app.route('/images/<path:path>')
def serve_sw_images(path):
    return send_from_directory('sw_images', path)

@app.route('/pnp/HELLO')
def pnp_hello():
    return '', 200

@app.route('/pnp/WORK-REQUEST', methods=['POST'])
def pnp_work_request():
    print(request.data)
    data = xmltodict.parse(request.data)
    print(data)
    correlator_id = data['pnp']['info']['@correlator']
    print(correlator_id)
    udi = data['pnp']['@udi']
    print(udi)
    udi_match = re.match(r'PID:(?P<product_id>[\w-]+),VID:(?P<hw_version>\w+),SN:(?P<serial_number>\w+)', udi)
    serial_number = udi_match.group('serial_number')
    product_id = udi_match.group('product_id')
    print (product_id, serial_number) 
    print("count: " + str(nb.dcim.devices.count(serial=serial_number)))
    if nb.dcim.devices.count(serial=serial_number) == 0:
      print ("Device not in netbox. Adding ...")
      device = nb.dcim.devices.create(
        name = 'staging',
        serial = serial_number,
        status='planned',
        site = nb.dcim.sites.get(name='home').id,
        device_type=nb.dcim.device_types.get(model=product_id).id,
        role=nb.dcim.device_roles.get(name='switch').id
      )
      return '', 200
    else:
      device = nb.dcim.devices.get(serial=serial_number)
      if device.status.value == 'staged':
        config_filename = device.serial + '.cfg'
        print(config_filename)
        #
        jinja_context = {
          "device": device
        }
        config_text = render_template('provision.jinja', **jinja_context)
        print (config_text)
        #   
        url = "http://192.168.88.20/api/dcim/devices/" + str(device.id) + "/render-config/"
        headers = {"Content-Type": "application/json", "Authorization": "Token a2c0d29623b5eef6e06ee0dbee9cd3e06d0d2300"}
        response = requests.post(url, headers=headers)
        # print("JSON Response ", response.json.content())
        print(response.json().get("content") )
        #
        with open("configs/"+config_filename, "w") as f:
          f.write(response.json().get("content"))
        #
        jinja_context = {
          "udi": udi,
          "correlator_id": correlator_id,
          "config_filename": config_filename,
        }
        result_data = render_template('config-upgrade.xml', **jinja_context)
        print (result_data)
        #
        return Response(result_data, mimetype='text/xml')
      else:
        return '',200

@app.route('/pnp/WORK-RESPONSE', methods=['POST'])
def pnp_work_response():
    print(request.data)
    data = xmltodict.parse(request.data)
    correlator_id = data['pnp']['response']['@correlator']
    udi = data['pnp']['@udi']
    jinja_context = {
        "udi": udi,
        "correlator_id": correlator_id,
    }
    result_data = render_template('bye.xml', **jinja_context)
    return Response(result_data, mimetype='text/xml')
