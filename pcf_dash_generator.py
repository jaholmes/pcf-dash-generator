#!flask/bin/python
from flask import Flask, jsonify, request, Response
from string import Template
import os
import argparse
import requests
import re
import logging
from logging.config import fileConfig
import app_config
from requests.exceptions import HTTPError
from tenacity import *

pcf_dash_template_file = 'templates/pcf_dashboard_template_v1.json'
pcf_dash_generated_file = 'generated/pcf_dashboard_generated.json'
pcf_hrs_template_file = 'templates/pcf_healthrules_template_v1.xml'
pcf_hrs_generated_file = 'generated/pcf_healthrules_generated.xml'
#dashboard_name should match name used in dashboard template; 
#otherwise check for existing dashboard will fail -- dashboard_already_exists()
dashboard_name = '${APPLICATION_NAME}-${TIER_NAME}-PCF KPI Dashboard'
publish_max_retries = 10
publish_max_retry_delay_seconds = 60 

fileConfig('logging_config.ini')
logger = logging.getLogger()
service = Flask(__name__)

#todo
#flask/REST endpoints
#    3. get generated dashboard w/o publishing
#    4. get default settings
#    5. get recent status
#unexpected exceptions, mapping to http error codes

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
    app_config.tier_id = os.getenv('APPD_NOZZLE_TIER_ID')    

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_host', help='the controller host', default=None)
    parser.add_argument('--controller_port', help='the controller port', default=None)
    parser.add_argument('--controller_ssl', help='True if ssl is enabled', default=False)
    parser.add_argument('--account_name', help='the controller account name', default='customer1')
    parser.add_argument('--user_name', help='the controller username', default=None)
    parser.add_argument('--user_pass', help='the controller user password', default=None)       
    parser.add_argument('--app', help='the Appd app where PCF metrics are published by the PCF tile and where dashboard and health rules will be generated', default=None)            
    parser.add_argument('--tier', help='the Appd tier where PCF metrics are published by the PCF tile', default=None)
    parser.add_argument('--tier_id', help='the tier component id used in metric path as COMPONENT:<id>', default=None)
    parser.add_argument('--start_service', help='start the rest API service', action='store_true', default=False)
    parser.add_argument('--service_port', help='override the default port 8080 for the service', type=int, default=8080)
    parser.add_argument("--overwrite", help='set to true to overwrite existing health rules and recreate dashboard on the target controller', 
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
    app_config.tier_id = args.tier_id    
    app_config.overwrite = args.overwrite
    app_config.start_service = args.start_service
    app_config.service_port = args.service_port
    
def get_system_metrics_parent_folder():
    metric_path_root = 'Application Infrastructure Performance|' + app_config.tier + '|Custom Metrics|PCF Firehose|SERVER25|System (BOSH) Metrics|bosh-system-metrics-forwarder'
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
    
def get_pcf_services(system_metrics_parent_folder):
    logger.info('getting pcf service details from controller')

    metric_path_root = 'Application Infrastructure Performance|' + app_config.tier + '|Custom Metrics|PCF Firehose|SERVER25|System (BOSH) Metrics|bosh-system-metrics-forwarder|' + system_metrics_parent_folder    

    query_prams='?output=json&metric-path=' + metric_path_root
    url = app_config.controller_url + '/controller/rest/applications/' + app_config.app + '/metrics' + query_prams
    logger.debug('url: ' + url)    
    response = requests.get(url, auth=(app_config.get_full_user_name(), app_config.user_pass))
    response.raise_for_status();
    logger.debug('response: + ' + str(response.json()))
    if len(response.json()) == 0:   
        raise RuntimeError("unable to get list of pcf services using url: " + url)
    pcf_services = {}
    pcf_service_list = response.json()
    
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
            pcf_services[service_name][i] = {'guid' : guid}
    return pcf_services

def generate_dashboard(pcf_services, system_metrics_parent_folder, app, tier):
    logger.info('generating dashboard from template')
    with open(pcf_dash_template_file, 'r', encoding='utf-8') as myfile:
        dash_template=myfile.read()
    dash_template = Template(dash_template)
    generated = dash_template.substitute(APPLICATION_NAME=app,
                                 TIER_NAME=tier,
                                 SERVER_NAME='SERVER25',
                                 SYSTEM_METRICS_PARENT_FOLDER=system_metrics_parent_folder,
                                 DIEGO_CELL_0_GUID=pcf_services['diego_cell'][0]['guid'], 
                                 DIEGO_CELL_1_GUID=pcf_services['diego_cell'][1]['guid'], 
                                 DIEGO_CELL_2_GUID=pcf_services['diego_cell'][2]['guid'], 
                                 ROUTER_0_GUID=pcf_services['router'][0]['guid'],
                                 UAA_0_GUID=pcf_services['uaa'][0]['guid'])
                                 
    return generated

def generate_healthrules(pcf_services, system_metrics_parent_folder, app, tier, tier_id):
    logger.info('generating health rules from template')    
    with open(pcf_hrs_template_file, 'r', encoding='utf-8') as myfile:
        hr_template=myfile.read()
    hr_template = Template(hr_template)
    generated = hr_template.substitute(TIER_NAME=tier,
                                       TIER_ID=tier_id,
                                       SERVER_NAME='SERVER25',
                                       SYSTEM_METRICS_PARENT_FOLDER=system_metrics_parent_folder,
                                       CLOCK_GLOBAL_0_GUID=pcf_services['clock_global'][0]['guid'],
                                       CLOUD_CONTROLLER_0_GUID=pcf_services['cloud_controller'][0]['guid'],
                                       CLOUD_CONTROLLER_WORKER_0_GUID=pcf_services['cloud_controller_worker'][0]['guid'],
                                       CONSUL_SERVER_0_GUID=pcf_services['consul_server'][0]['guid'],
                                       CREDHUB_0_GUID=pcf_services['credhub'][0]['guid'],
                                       DIEGO_BRAIN_0_GUID=pcf_services['diego_brain'][0]['guid'],
                                       DIEGO_CELL_0_GUID=pcf_services['diego_cell'][0]['guid'],
                                       DIEGO_CELL_1_GUID=pcf_services['diego_cell'][1]['guid'],
                                       DIEGO_CELL_2_GUID=pcf_services['diego_cell'][2]['guid'],
                                       DIEGO_DATABASE_0_GUID=pcf_services['diego_database'][0]['guid'],
                                       DOPPLER_0_GUID=pcf_services['doppler'][0]['guid'],
                                       LOGGREGATOR_TRAFFICCONTROLLER_0_GUID=pcf_services['loggregator_trafficcontroller'][0]['guid'],
                                       MYSQL_0_GUID=pcf_services['mysql'][0]['guid'],
                                       MYSQL_PROXY_0_GUID=pcf_services['mysql_proxy'][0]['guid'],
                                       NATS_0_GUID=pcf_services['nats'][0]['guid'],
                                       ROUTER_0_GUID=pcf_services['router'][0]['guid'],
                                       SYSLOG_ADAPTER_0_GUID=pcf_services['syslog_adapter'][0]['guid'],
                                       SYSLOG_SCHEDULER_0_GUID=pcf_services['syslog_scheduler'][0]['guid'],
                                       TCP_ROUTER_0_GUID=pcf_services['tcp_router'][0]['guid'],                                       
                                       UAA_0_GUID=pcf_services['uaa'][0]['guid'])
    return generated

def dashboard_already_exists():
    dash_name_template = Template(dashboard_name)
    dash_name = dash_name_template.substitute(APPLICATION_NAME=app_config.app, TIER_NAME=app_config.tier)
    logger.info('checking if dashboard already exists on controller with name: ' + dash_name)
    session = requests.Session()
    session.auth=app_config.get_full_user_name(), app_config.user_pass
    login = session.get(app_config.controller_url + '/controller/auth?action=login')
    session.headers['X-CSRF-TOKEN'] = login.cookies['X-CSRF-TOKEN']
    url = app_config.controller_url + '/controller/restui/dashboards/getAllDashboardsByType/false'
    logger.debug('url: ' + url)        
    response = session.get(url)
    logger.debug('response: ' + str(response.json()))
    response.raise_for_status();
    dashboards = response.json()
    for dashboard in dashboards:
        logger.debug('name: ' + dashboard['name'])
        if dashboard['name'] == dash_name:
            return True
    return False

def return_last_value(last_attempt):
    return last_attempt.result()
def is_false(value):
    return value is False

@retry(wait=wait_exponential(max=publish_max_retry_delay_seconds),
       stop=stop_after_attempt(publish_max_retries),
       retry=retry_if_result(is_false),
       retry_error_callback=return_last_value) 
def pcf_metric_path_exists_with_retry():
    return pcf_metric_path_exists()
    
def pcf_metric_path_exists():
    metric_path_root = 'Application Infrastructure Performance|' + app_config.tier + '|Custom Metrics|PCF Firehose|SERVER25|System (BOSH) Metrics|bosh-system-metrics-forwarder'
    query_prams='?output=json&metric-path=' + metric_path_root
    url = app_config.controller_url + '/controller/rest/applications/' + app_config.app + '/metrics' + query_prams
    logger.debug('url: ' + url)    
    try:
        response = requests.get(url, auth=(app_config.get_full_user_name(), app_config.user_pass))
        response.raise_for_status()
    except HTTPError as err:
        if err.response.status_code == 400 and 'invalid application' in err.response.reason.lower():
            logger.debug('application \'%s\' doesn\'t exist', app_config.app)
            return False
    logger.debug('response: ' + str(response.json()))
    if len(response.json()) == 0:
        return False   
    return True
    
def upload_healthrules(healthrules_xml, overwrite):
    logger.info('uploading health rules to controller (overwrite=(' + str(app_config.overwrite) + '))')    
    url = app_config.controller_url + '/controller/healthrules/' + app_config.app
    if overwrite:
        url += "?overwrite=true"
    logger.debug('url: ' + url)    
    response = requests.post(url, auth=(app_config.get_full_user_name(), app_config.user_pass), files={'file':healthrules_xml})
    response.raise_for_status();
    logger.debug('response: ' + str(response.content))

def upload_dashboard(dashboard_json, overwrite):
    logger.info('uploading dashboard to controller')
    if not overwrite and dashboard_already_exists(): 
        logger.info('dashboard already exists on controller, skipping upload (overwrite=(' + str(overwrite) + '))')
        return
    url = app_config.controller_url + '/controller/CustomDashboardImportExportServlet'
    logger.debug('url: ' + url)    
    response = requests.post(url, auth=(app_config.get_full_user_name(), app_config.user_pass), files={'file':dashboard_json})
    response.raise_for_status();
    logger.debug('response status code: ' + str(response.status_code))

def publish_dashboard_and_hrs(overwrite):
    logger.info('publishing pcf dashboards and hrs')
    system_metrics_parent_folder = get_system_metrics_parent_folder()
    logger.debug('system_metrics_parent_folder: ' + str(system_metrics_parent_folder))
    pcf_services = get_pcf_services(system_metrics_parent_folder)
    logger.debug('pcf_services: ' + str(pcf_services))    
    dashboard = generate_dashboard(pcf_services, system_metrics_parent_folder, app_config.app, app_config.tier)
    healthrules = generate_healthrules(pcf_services, system_metrics_parent_folder, app_config.app, app_config.tier, app_config.tier_id)
    if app_config.commandline and not app_config.start_service:
        logger.info('writing generated dashboard and hrs to file system')
        with open(pcf_dash_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(dashboard)
        with open(pcf_hrs_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(healthrules)
    upload_dashboard(dashboard, overwrite)
    upload_healthrules(healthrules, overwrite)
    logger.info('done publishing pcf dashboards and hrs')
    
def start_flask():
    logger.info('starting service on port ' + str(app_config.service_port))
    service.run(debug=True, port=app_config.service_port)

@service.route('/pcf-dash/publish', methods=['POST'])
def publish():
    logger.info('request received: publish')    
    overwrite = request.args.get('overwrite') is not None and request.args.get('overwrite').lower() == 'true'
    retry = request.args.get('retry') is not None and request.args.get('retry').lower() == 'true'
    if retry:
        metric_path_exists = pcf_metric_path_exists_with_retry()
    else:     
        metric_path_exists = pcf_metric_path_exists()        
    if not metric_path_exists:
        msg = 'failed to find PCF metric paths in target controller required to publish dashboard, giving up'        
        logger.error(msg)
        return Response(msg, 404)
    publish_dashboard_and_hrs(overwrite)
    return 'done'

def start_app_commandline():
    app_config.commandline = True
    parse_args()
    if app_config.start_service:
        logger.info('starting service')
        start_flask()
    else:
        if not pcf_metric_path_exists():
            logger.error('failed to find PCF metric paths in target controller required to publish dashboard, giving up')
            return
        publish_dashboard_and_hrs(app_config.overwrite)

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
