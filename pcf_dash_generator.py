#!flask/bin/python
from flask import Flask, request, Response
from string import Template
import os
import argparse
import requests
import re
import logging
from logging.config import fileConfig
from requests.exceptions import HTTPError
from tenacity import *
import time
from json.decoder import JSONDecodeError

pcf_dash_template_file = 'templates/pcf_dashboard_template_v1.json'
pcf_dash_generated_file = 'generated/pcf_dashboard_generated.json'
pcf_hrs_template_file = 'templates/pcf_healthrules_template_v1.xml'
pcf_hrs_generated_file = 'generated/pcf_healthrules_generated.xml'

# DASHBOARD_NAME should match name used in dashboard template;
# otherwise check for existing dashboard will fail -- dashboard_already_exists()
DASHBOARD_NAME = '${APPLICATION_NAME}-${TIER_NAME}-PCF KPI Dashboard'
PUBLISH_MAX_RETRIES = 10
PUBLISH_MAX_RETRY_DELAY_SECONDS = 60
DELAY_AFTER_HR_UPLOAD_SECONDS = 30
PCF_SERVICE_NAMES = ['clock_global', 'cloud_controller', 'cloud_controller_worker', 'consul_server', 'credhub', 
                     'diego_brain', 'diego_cell', 'diego_database', 'doppler', 'loggregator_trafficcontroller', 
                     'mysql', 'mysql_proxy', 'nats', 'router', 'syslog_adapter', 'syslog_scheduler', 'tcp_router', 'uaa'] 

fileConfig('logging_config.ini')
logger = logging.getLogger()
service = Flask(__name__)


class MetricPathNotFound(Exception):
    def __init__(self, message):
        super().__init__(message)


class AppConfig(object):
    controller_url = None
    account_name = None
    user_name = None
    user_pass = None
    app = None
    tier = None
    tier_id = None
    recreate_dashboard = False    
    overwrite_hrs = False
    start_service = None
    port = None
    commandline = False

    @classmethod
    def get_full_user_name(cls):
        return cls.user_name + '@' + cls.account_name

    @staticmethod
    def get_controller_url(host, port, ssl_enabled):
        if ssl_enabled is True:
            controller_url = 'https://'
        else:
            controller_url = 'http://'
        controller_url += host
        if port:
            controller_url += ':' + port
        return controller_url


def parse_env():
    controller_host = os.getenv('APPD_MA_HOST_NAME')
    controller_port = os.getenv('APPD_MA_PORT')
    controller_ssl_enabled = os.getenv('APPD_MA_SSL_ENABLED')
    AppConfig.controller_url = AppConfig.get_controller_url(controller_host, controller_port, controller_ssl_enabled)
    logger.debug('controller url: ' + AppConfig.controller_url)
    AppConfig.account_name = os.getenv('APPD_MA_ACCOUNT_NAME', 'customer1')
    AppConfig.user_name = os.getenv('APPD_MA_USER_NAME')
    AppConfig.user_pass = os.getenv('APPD_MA_USER_PASS')
    AppConfig.app = os.getenv('APPD_NOZZLE_APP_NAME')
    AppConfig.tier = os.getenv('APPD_NOZZLE_TIER_NAME')
    AppConfig.tier_id = os.getenv('APPD_NOZZLE_TIER_ID')
    AppConfig.recreate_dashboard = os.getenv('APPD_MA_RECREATE_DASHBOARD')
    AppConfig.overwrite_hrs = os.getenv('APPD_MA_OVERWRITE_HRS')
    


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_host', help='the controller host', required=True, default=None)
    parser.add_argument('--controller_port', help='the controller port', required=True, default=None)
    parser.add_argument('--controller_ssl_enabled', help='controller ssl is enabled', action='store_true', default=False)
    parser.add_argument('--account_name', help='the controller account name', required=True, default=None)
    parser.add_argument('--user_name', help='the controller username', required=True, default=None)
    parser.add_argument('--user_pass', help='the controller user password', required=True, default=None)
    parser.add_argument('--app', help='the Appd app where PCF metrics are published by the PCF tile and where dashboard'
                                      ' and health rules will be generated', required=True, default=None)
    parser.add_argument('--tier', help='the Appd tier where PCF metrics are published by the PCF tile', required=True, default=None)
    parser.add_argument('--tier_id', help='the tier component id used in metric path as COMPONENT:<id>', required=True, default=None)
    parser.add_argument('--start_service', help='start the rest API service', action='store_true', default=False)
    parser.add_argument('--service_port', help='override the default port 8080 for the service',
                        type=int, default=8080)
    parser.add_argument("--recreate_dashboard", help='set to true to recreate dashboard on the target controller if one already exists',
                        action='store_true', default=False)
    parser.add_argument("--overwrite_hrs", help='set to true to overwrite existing health rules on the target controller',
                        action='store_true', default=False)
    args = parser.parse_args()
    logger.info('args: ' + str(args))
    AppConfig.controller_url = AppConfig.get_controller_url(args.controller_host, args.controller_port,
                                                            args.controller_ssl_enabled)
    logger.debug('controller url: ' + AppConfig.controller_url)
    AppConfig.account_name = args.account_name
    AppConfig.user_name = args.user_name
    AppConfig.user_pass = args.user_pass
    AppConfig.app = args.app
    AppConfig.tier = args.tier
    AppConfig.tier_id = args.tier_id
    AppConfig.recreate_dashboard = args.recreate_dashboard
    AppConfig.overwrite_hrs = args.overwrite_hrs    
    AppConfig.start_service = args.start_service
    AppConfig.service_port = args.service_port


def get_system_metrics_parent_folder():
    metric_path_root = 'Application Infrastructure Performance|' + AppConfig.tier +\
                       '|Custom Metrics|PCF Firehose Monitor|System (BOSH) Metrics|bosh-system-metrics-forwarder'
    query_prams='?output=json&metric-path=' + metric_path_root
    url = AppConfig.controller_url + '/controller/rest/applications/' + AppConfig.app + '/metrics' + query_prams
    logger.debug('url: ' + url)
    response = requests.get(url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass))
    response.raise_for_status();
    logger.debug('response: ' + str(response.json()))
    folders = response.json()

    logger.debug('folders: ' + str(folders))

    resource_parent_folder = None
    for folder in folders:
        if re.match('cf-\w+', str(folder['name']), re.I):
            logger.debug('name: ' + str(folder['name']))
            test_url = AppConfig.controller_url + '/controller/rest/applications/' + AppConfig.app + '/metrics' + query_prams + '|' + str(folder['name']) + '|diego_cell'
            logger.debug('test_url: ' + test_url)
            test_response = requests.get(test_url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass))
            response.raise_for_status();            
            logger.debug('test_response: ' + str(test_response.json()))
            if not len(test_response.json()) == 0:
                resource_parent_folder = str(folder['name'])
    if resource_parent_folder is None:
        raise RuntimeError("unable to locate resource metrics parent folder using url: " + url)
    return resource_parent_folder


def get_pcf_services(system_metrics_parent_folder):
    logger.info('getting pcf service details from controller')

    metric_path_root = 'Application Infrastructure Performance|' + AppConfig.tier +\
                       '|Custom Metrics|PCF Firehose Monitor|System (BOSH) Metrics|bosh-system-metrics-forwarder|' +\
                       system_metrics_parent_folder

    query_prams='?output=json&metric-path=' + metric_path_root
    url = AppConfig.controller_url + '/controller/rest/applications/' + AppConfig.app + '/metrics' + query_prams
    logger.debug('url: ' + url)
    response = requests.get(url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass))
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
        service_url = AppConfig.controller_url + '/controller/rest/applications/' + AppConfig.app + '/metrics' +\
                      query_prams
        logger.debug('service_url: ' + service_url)
        response = requests.get(service_url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass))
        response.raise_for_status();
        service_instances = response.json()
        logger.debug('nbr of instances: ' + str(len(service_instances)))
        pcf_services[service_name] = [dict() for x in range(len(service_instances))]
        for i, service_instance in enumerate(service_instances):
            logger.debug('service instance: ' + str(service_instance))
            guid = service_instance['name']
            pcf_services[service_name][i] = {'guid' : guid}
    return pcf_services


def get_template_keyvalues(pcf_services, system_metrics_parent_folder, app, tier, tier_id):
    logger.info('getting template key/values')
    keyvalues = {
        'APPLICATION_NAME' : app,        
        'TIER_NAME' : tier,
        'TIER_ID' : tier_id,                
        'SYSTEM_METRICS_PARENT_FOLDER' : system_metrics_parent_folder
    }
    for pcf_service_name in PCF_SERVICE_NAMES:
        service_vms = pcf_services[pcf_service_name]
        logger.debug('service vms: ' + str(service_vms))        
        for i, service_vm in enumerate(service_vms):
            logger.debug('service vm guid: ' + service_vm['guid'])
            keyvalues[pcf_service_name.upper() + '_' + str(i) + '_GUID'] = service_vm['guid']
    logger.debug('keyvalues: ' + str(keyvalues))
    return keyvalues


def generate_dashboard(template_keyvalues):
    logger.info('generating dashboard from template')
    with open(pcf_dash_template_file, 'r', encoding='utf-8') as myfile:
        dash_template=myfile.read()
    dash_template = Template(dash_template)
    generated = dash_template.substitute(template_keyvalues)
    #logger.debug('generated: ' + generated)        
    return generated


def generate_healthrules(template_keyvalues):
    logger.info('generating health rules from template')
    with open(pcf_hrs_template_file, 'r', encoding='utf-8') as myfile:
        hr_template=myfile.read()
    hr_template = Template(hr_template)
    generated = hr_template.substitute(template_keyvalues)
    return generated


def dashboard_already_exists():
    dash_name_template = Template(DASHBOARD_NAME)
    dash_name = dash_name_template.substitute(APPLICATION_NAME=AppConfig.app, TIER_NAME=AppConfig.tier)
    logger.info('checking if dashboard already exists on controller with name: ' + dash_name)
    session = requests.Session()
    session.auth=AppConfig.get_full_user_name(), AppConfig.user_pass
    login = session.get(AppConfig.controller_url + '/controller/auth?action=login')
    session.headers['X-CSRF-TOKEN'] = login.cookies['X-CSRF-TOKEN']
    url = AppConfig.controller_url + '/controller/restui/dashboards/getAllDashboardsByType/false'
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


@retry(wait=wait_exponential(max=PUBLISH_MAX_RETRY_DELAY_SECONDS),
       stop=stop_after_attempt(PUBLISH_MAX_RETRIES),
       retry=retry_if_result(is_false),
       retry_error_callback=return_last_value)
def pcf_metric_path_exists_with_retry():
    return pcf_metric_path_exists()


def pcf_metric_path_exists():
    metric_path_root = 'Application Infrastructure Performance|' + AppConfig.tier +\
                       '|Custom Metrics|PCF Firehose Monitor|System (BOSH) Metrics|bosh-system-metrics-forwarder'
    query_prams = {
        'output': 'json',
        'metric-path': metric_path_root
    }
    url = AppConfig.controller_url + '/controller/rest/applications/' + AppConfig.app + '/metrics'
    logger.debug('url: ' + url)
    response = None
    try:
        session = requests.Session()
        session.auth = (AppConfig.get_full_user_name(), AppConfig.user_pass)
        if os.getenv('APPD_MA_SSL_ENABLED') == 'true':
            session.verify = 'cert.pem'
        response = session.get(url, params=query_prams)
        response.raise_for_status()
        if response is not None: logger.debug('response: ' + str(response.json()))
    except HTTPError as err:
        if err.response.status_code == 400 and 'invalid application' in err.response.reason.lower():
            logger.debug('application \'%s\' doesn\'t exist', AppConfig.app)
            return False
    if response is None:
        return False
    try:
        if len(response.json()) == 0:
            return False
    except JSONDecodeError:
        return False
    return True


def check_pcf_metric_path_exists(retry=False):
    if retry:
        metric_path_exists = pcf_metric_path_exists_with_retry()
    else:
        metric_path_exists = pcf_metric_path_exists()
    if not metric_path_exists:
        msg = 'error: failed to find PCF metric path in target controller required to publish dashboard'
        logger.error(msg)
        raise MetricPathNotFound(msg)


def upload_healthrules(healthrules_xml, overwrite_hrs):
    logger.info('uploading health rules to controller (overwrite_hrs=' + str(AppConfig.overwrite_hrs) + ')')
    url = AppConfig.controller_url + '/controller/healthrules/' + AppConfig.app
    if overwrite_hrs:
        url += "?overwrite=true"
    logger.debug('url: ' + url)
    response = requests.post(url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass),
                             files={'file':healthrules_xml})
    response.raise_for_status();
    logger.debug('response: ' + str(response.content))


def upload_dashboard(dashboard_json, recreate_dashboard):
    logger.info('uploading dashboard to controller')
    if not recreate_dashboard and dashboard_already_exists():
        logger.info('dashboard already exists on controller, will not recreate (recreate_dashboard=' + str(recreate_dashboard) + ')', )
        return
    url = AppConfig.controller_url + '/controller/CustomDashboardImportExportServlet'
    logger.debug('url: ' + url)
    response = requests.post(url, auth=(AppConfig.get_full_user_name(), AppConfig.user_pass),
                             files={'file':dashboard_json})
    response.raise_for_status();
    logger.debug('response status code: ' + str(response.status_code))


def publish_dashboard_and_hrs(retry=False, recreate_dashboard=False, overwrite_hrs=False):
    logger.info('publishing pcf dashboards and hrs')
    check_pcf_metric_path_exists(retry)
    system_metrics_parent_folder = get_system_metrics_parent_folder()
    logger.debug('system_metrics_parent_folder: ' + str(system_metrics_parent_folder))
    pcf_services = get_pcf_services(system_metrics_parent_folder)
    logger.debug('pcf_services: ' + str(pcf_services))
    template_keyvalues = get_template_keyvalues(pcf_services, system_metrics_parent_folder, 
                                                AppConfig.app, AppConfig.tier, AppConfig.tier_id)    
    dashboard = generate_dashboard(template_keyvalues)
    healthrules = generate_healthrules(template_keyvalues)
    if AppConfig.commandline and not AppConfig.start_service:
        logger.debug('writing generated dashboard and hrs to file system')
        with open(pcf_dash_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(dashboard)
        with open(pcf_hrs_generated_file, 'w', encoding='utf-8') as myfile:
            myfile.write(healthrules)
    upload_healthrules(healthrules, overwrite_hrs)
    logger.debug('sleeping %s seconds for health rules to be saved', str(DELAY_AFTER_HR_UPLOAD_SECONDS))
    time.sleep(DELAY_AFTER_HR_UPLOAD_SECONDS)
    upload_dashboard(dashboard, recreate_dashboard)
    logger.info('done publishing pcf dashboards and hrs')


def start_flask():
    logger.info('starting service on port ' + str(AppConfig.service_port))
    service.run(debug=True, port=AppConfig.service_port)


@service.route('/pcf-dash/publish', methods=['POST'])
def publish():
    logger.info('request received: publish')
    overwrite_hrs = request.args.get('overwrite_hrs') and request.args.get('overwrite_hrs').lower() == 'true'
    recreate_dashboard = request.args.get('recreate_dashboard') and request.args.get('recreate_dashboard').lower() == 'true'    
    retry = request.args.get('retry') and request.args.get('retry').lower() == 'true'
    try:
        publish_dashboard_and_hrs(retry, recreate_dashboard, overwrite_hrs)
    except MetricPathNotFound as e:
        logger.error(str(e))
        return Response(str(e), 404)
    return 'done'


def start_app_commandline():
    AppConfig.commandline = True
    parse_args()
    if AppConfig.start_service:
        logger.info('starting service')
        start_flask()
    else:
        publish_dashboard_and_hrs(retry=False, recreate_dashboard=AppConfig.recreate_dashboard, overwrite_hrs=AppConfig.overwrite_hrs)


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
