#!flask/bin/python
from flask import Flask, jsonify, request
from string import Template
import os
import argparse
import requests
import re
import logging
from logging.config import fileConfig
import app_config

pcf_dash_template_file = 'templates/pcf_dashboard_template_v1.json'
pcf_dash_generated_file = 'generated/pcf_dashboard_generated.json'
pcf_hrs_template_file = 'templates/pcf_healthrules_template_v1.xml'
pcf_hrs_generated_file = 'generated/pcf_healthrules_generated.xml'

fileConfig('logging_config.ini')
logger = logging.getLogger()
service = Flask(__name__)
commandline = False

#todo
#flask/REST endpoints
#    1. publish dashboard based on template on file system, 
#             optionally supply new settings
#             optionally supply overwrite flag
#    2. publish with retry and delay for initial tile deployment use case
#    3. get logs
#    4. get default settings
#exceptions, mapping to http error codes

def parse_env():
    controller_host = os.getenv('APPD_MA_HOST_NAME')
    controller_port = os.getenv('APPD_MA_PORT')
    controller_ssl = os.getenv('APPD_MA_SSL_ENABLED')
    app_config.controller_url = app_config.get_controller_url(controller_host, controller_port, controller_ssl)
    logger.debug('controller url: ' + app_config.controller_url)    
    app_config.account_name = os.getenv('APPD_MA_ACCOUNT_NAME', 'customer1')
    app_config.user_name = os.getenv('APPD_MA_USER_NAME')
    app_config.user_pass = os.getenv('APPD_MA_USER_PASS')
    app_config.app = os.getenv('APPD_NOZZLE_APP_NAME')
    app_config.tier = os.getenv('APPD_NOZZLE_TIER_NAME')

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_host', help='the controller host', default=None)
    parser.add_argument('--controller_port', help='the controller port', default=None)
    parser.add_argument('--controller_ssl', help='True if ssl is enabled', default=False)
    parser.add_argument('--account_name', help='the controller account name', default='customer1')    
    parser.add_argument('--user_name', help='the controller username', default=None)
    parser.add_argument('--user_pass', help='the controller user password', default=None)       
    parser.add_argument('--app', help='the Appd app where PCF metrics are published by the PCF tile', default=None)            
    parser.add_argument('--tier', help='the Appd tier where PCF metrics are published by the PCF tile', default=None)            
    parser.add_argument('--start_service', help='start the rest API service', action='store_true', default=False)
    parser.add_argument('--service_port', help='override the default port 8080 for the service', type=int, default=8080)
    parser.add_argument("--overwrite_hrs", help='set to true to overwrite existing health rules with the same name in the target controller', 
                        action='store_true', default=False)
    args = parser.parse_args()
    logger.info('args: ' + str(args))
    app_config.controller_url = app_config.get_controller_url(args.controller_host, args.controller_port, args.controller_ssl)
    logger.debug('controller url: ' + app_config.controller_url)
    app_config.account_name = args.account_name
    app_config.user_name = args.user_name
    app_config.user_pass = args.user_pass    
    app_config.app = args.app
    app_config.tier = args.tier
    app_config.overwrite_hrs = args.overwrite_hrs
    app_config.start_service = args.start_service
    app_config.service_port = args.service_port
    
def get_resources_parent_folder():
    metric_path_root = 'Application Infrastructure Performance|' + app_config.tier + '|Custom Metrics|CF'
    query_prams='?output=json&metric-path=' + metric_path_root
    url = app_config.controller_url + '/controller/rest/applications/' + app_config.app + '/metrics' + query_prams
    logger.debug('url: ' + url)    
    response = requests.get(url, auth=(app_config.get_full_user_name(), app_config.user_pass))
    response.raise_for_status();
    logger.debug('response: ' + str(response.json()))
    folders = response.json()

    logger.debug('folders: ' + str(folders))

    resource_parent_folder = None
    for folder in folders:
        #todo need to filter out other cf- matches like cf-redis, but wait for new version of tile
        #to confirm this is necessary (bosh/resource metric location may change)
        if re.match('cf-\w+', str(folder['name']), re.I) and 'redis' not in str(folder['name']):
            logger.debug('name: ' + str(folder['name']))
            resource_parent_folder = str(folder['name'])
    if resource_parent_folder is None: 
        raise RuntimeError("unable to locate resource metrics parent folder using url: " + url)
    return resource_parent_folder
    
def get_pcf_services():
    logger.info('getting pcf service details from controller')
    metric_path_root = 'Application Infrastructure Performance|' + app_config.tier + '|Custom Metrics|CF|cf'    
    query_prams='?output=json&metric-path=' + metric_path_root
    url = app_config.controller_url + '/controller/rest/applications/' + app_config.app + '/metrics' + query_prams
    logger.debug('url: ' + url)    
    response = requests.get(url, auth=(app_config.get_full_user_name(), app_config.user_pass))
    response.raise_for_status();
    logger.debug('response: + ' + str(response.json())) 
    pcf_service_list = response.json()
    
    pcf_services = {}
    for pcf_service in pcf_service_list:
        service_name = pcf_service['name']
        logger.debug('service: ' + service_name)
        pcf_service_metric_path = metric_path_root + '|' + service_name 
        query_prams='?output=json&metric-path=' + pcf_service_metric_path
        service_url = app_config.controller_url + '/controller/rest/applications/' + app_config.app + '/metrics' + query_prams
        logger.debug('service_url: ' + service_url)
        response = requests.get(service_url, auth=(app_config.get_full_user_name(), app_config.user_pass))
        response.raise_for_status();
        service_instances = response.json()
        logger.debug('nbr of instances: ' + str(len(service_instances))) 
        pcf_services[service_name] = [dict() for x in range(len(service_instances))]
        for i, service_instance in enumerate(service_instances):
            logger.debug('service instance: ' + str(service_instance))
            guid = service_instance['name']
            pcf_services[service_name][i] = {'guid' : guid, 'ips' : []}
            guid_url = service_url + '|' + guid
            logger.debug('guid_url: ' + guid_url)
            response = requests.get(guid_url, auth=(app_config.get_full_user_name(), app_config.user_pass))
            response.raise_for_status();
            ips = response.json()
            logger.debug('ips: ' + str(ips))
            pcf_services[service_name][i]['ips'] = [None] * len(ips)
            for j, ip in enumerate(ips):
                 #pcf_services[service_name][i] = {'guid' : guid, 'ips' : []}
                 logger.debug('ip: ' + ip['name'])
                 pcf_services[service_name][i]['ips'][j] = ip['name']
    return pcf_services

def generate_dashboard(pcf_services, resources_parent_folder, app, tier):
    logger.info('generating dashboard from template')
    with open(pcf_dash_template_file, 'r', encoding='utf-8') as myfile:
        dash_template=myfile.read()
    dash_template = Template(dash_template)
    generated = dash_template.substitute(APP_NAME=app,
                                 TIER_NAME=tier, 
                                 DIEGO_CELL_0_GUID=pcf_services['diego_cell'][0]['guid'], 
                                 DIEGO_CELL_0_IP_0=pcf_services['diego_cell'][0]['ips'][0],
                                 DIEGO_CELL_1_GUID=pcf_services['diego_cell'][1]['guid'], 
                                 DIEGO_CELL_1_IP_0=pcf_services['diego_cell'][1]['ips'][0],
                                 DIEGO_CELL_2_GUID=pcf_services['diego_cell'][2]['guid'], 
                                 DIEGO_CELL_2_IP_0=pcf_services['diego_cell'][2]['ips'][0],
                                 RESOURCES_PARENT_FOLDER=resources_parent_folder)
    return generated

def generate_healthrules(pcf_services, resources_parent_folder, app, tier):
    logger.info('generating health rules from template')    
    with open(pcf_hrs_template_file, 'r', encoding='utf-8') as myfile:
        hr_template=myfile.read()
    hr_template = Template(hr_template)
    generated = hr_template.substitute(TIER_NAME=tier, 
                                       DIEGO_CELL_0_GUID=pcf_services['diego_cell'][0]['guid'], 
                                       DIEGO_CELL_0_IP_0=pcf_services['diego_cell'][0]['ips'][0],
                                       DIEGO_CELL_1_GUID=pcf_services['diego_cell'][1]['guid'], 
                                       DIEGO_CELL_1_IP_0=pcf_services['diego_cell'][1]['ips'][0],
                                       DIEGO_CELL_2_GUID=pcf_services['diego_cell'][2]['guid'], 
                                       DIEGO_CELL_2_IP_0=pcf_services['diego_cell'][2]['ips'][0],
                                       DIEGO_BRAIN_GUID=pcf_services['diego_brain'][0]['guid'], 
                                       DIEGO_BRAIN_IP=pcf_services['diego_brain'][0]['ips'][0],
                                       ROUTER_GUID=pcf_services['router'][0]['guid'], 
                                       ROUTER_IP=pcf_services['router'][0]['ips'][0],
                                       DIEGO_DATABASE_GUID=pcf_services['diego_database'][0]['guid'], 
                                       DIEGO_DATABASE_IP=pcf_services['diego_database'][0]['ips'][0],
                                       RESOURCES_PARENT_FOLDER=resources_parent_folder)
    return generated

def upload_healthrules(healthrules_xml):
    logger.info('uploading health rules to controller (overwrite=(' + str(app_config.overwrite_hrs) + '))')    
    url = app_config.controller_url + '/controller/healthrules/' + app_config.app
    if app_config.overwrite_hrs:
        url += "?overwrite=true"
    logger.debug('url: ' + url)    
    response = requests.post(url, auth=(app_config.get_full_user_name(), app_config.user_pass), files={'file':healthrules_xml})
    response.raise_for_status();
    logger.debug('response: ' + str(response.content))

def upload_dashboard(dashboard_json):
    logger.info('uploading dashboard to controller')        
    url = app_config.controller_url + '/controller/CustomDashboardImportExportServlet'
    logger.debug('url: ' + url)    
    response = requests.post(url, auth=(app_config.get_full_user_name(), app_config.user_pass), files={'file':dashboard_json})
    response.raise_for_status();
    logger.debug('response status code: ' + str(response.status_code))

def publish_dashboard_and_hrs():
    logger.info('publishing pcf dashboards and hrs')
    pcf_services = get_pcf_services()
    resources_parent_folder = get_resources_parent_folder()
    logger.debug('pcf_services: ' + str(pcf_services))
    logger.debug('resources_parent_folder: ' + str(resources_parent_folder))
    dashboard = generate_dashboard(pcf_services, resources_parent_folder, app_config.app, app_config.tier)
    healthrules = generate_healthrules(pcf_services, resources_parent_folder, app_config.app, app_config.tier)
    if commandline and not app_config.start_service:
        logger.info('writing generated dashboard and hrs to file system')
        with open(pcf_dash_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(dashboard)
        with open(pcf_hrs_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(healthrules)
    upload_dashboard(dashboard)
    upload_healthrules(healthrules)
    logger.info('done publishing pcf dashboards and hrs')
    
def start_flask():
    logger.info('starting service on port ' + str(app_config.service_port))
    service.run(debug=True, port=app_config.service_port)

@service.route('/pcf-dash/publish', methods=['POST'])
def publish():
    #todo content = request.json
    #logger.debug('content: ' + str(content))
    publish_dashboard_and_hrs()
    return 'done'
    
def start_app_commandline():
    commandline = True
    parse_args()
    if app_config.start_service:
        logger.info('starting service')
        start_flask()
    else:
        publish_dashboard_and_hrs()

def start_app_pcf():
    parse_env()
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger is not None:
        service.logger.handlers = gunicorn_logger.handlers
        service.logger.setLevel(gunicorn_logger.level)
        
if __name__ == '__main__':
    start_app_commandline()
else:
    start_app_pcf()
