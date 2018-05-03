
#!flask/bin/python
from flask import Flask, jsonify
from string import Template
import argparse
import requests
import re

pcf_dash_template_file = 'templates/pcf_dashboard_template_v1.json'
pcf_dash_generated_file = 'generated/pcf_dashboard_generated.json'
pcf_hrs_template_file = 'templates/pcf_healthrules_template_v1.json'
pcf_hrs_generated_file = 'generated/pcf_healthrules_generated.json'

app = Flask(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-controller_url", help='the controller url, i.e. http://mycontroller:8090', required=True)
    parser.add_argument("-user_name", help='the controller username (user@account)', required=True)    
    parser.add_argument("-user_pass", help='the controller user password', required=True)        
    parser.add_argument("-app", help='the Appd app where PCF metrics are published by the PCF tile', required=True)            
    parser.add_argument("-tier", help='the Appd tier where PCF metrics are published by the PCF tile', required=True)                
    parser.add_argument("-v", "--verbose", action='store_true', dest="verbose", default=False, help="print verbose output")
    args = parser.parse_args()
    if args.verbose:
        print(args)
    return args
    
def get_resources_parent_path(args):
    metric_path_root = 'Application Infrastructure Performance|' + args.tier + '|Custom Metrics|CF'
    query_prams='?output=json&metric-path=' + metric_path_root
    url = args.controller_url + '/controller/rest/applications/' + args.app + '/metrics' + query_prams
    if args.verbose: print('url: ' + url)    
    response = requests.get(url, auth=(args.user_name, args.user_pass))
    response.raise_for_status();
    print(response.json()) 
    folders = response.json()
    print('folders: ' + str(folders))

    resource_parent_path = None
    for folder in folders:
        #todo need to filter out other cf- matches like cf-redis, but wait for new version of tile
        #to confirm this is necessary (bosh/resource metric location may change)
        if re.match('cf-\w+', str(folder['name']), re.I) and 'redis' not in str(folder['name']):
            print('name: ' + str(folder['name']))
            resource_parent_path = str(folder['name'])
    if resource_parent_path is None: 
        raise RuntimeError("unable to locate resource metrics parent folder using url: " + url)
    return resource_parent_path
    
    
    
def get_pcf_services(args):
    metric_path_root = 'Application Infrastructure Performance|' + args.tier + '|Custom Metrics|CF|cf'    
    query_prams='?output=json&metric-path=' + metric_path_root
    url = args.controller_url + '/controller/rest/applications/' + args.app + '/metrics' + query_prams
    if args.verbose: print('url: ' + url)    
    response = requests.get(url, auth=(args.user_name, args.user_pass))
    response.raise_for_status();
    print(response.json()) 
    pcf_service_list = response.json()
    
    pcf_services = {}
    for pcf_service in pcf_service_list:
        service_name = pcf_service['name']
        print('service: ' + service_name)
        pcf_service_metric_path = metric_path_root + '|' + service_name 
        query_prams='?output=json&metric-path=' + pcf_service_metric_path
        service_url = args.controller_url + '/controller/rest/applications/' + args.app + '/metrics' + query_prams
        print ('service_url: ' + service_url)
        response = requests.get(service_url, auth=(args.user_name, args.user_pass))
        response.raise_for_status();
        service_instances = response.json()
        print('nbr of instances: ' + str(len(service_instances))) 
        pcf_services[service_name] = [dict() for x in range(len(service_instances))]
        for i, service_instance in enumerate(service_instances):
            print('service instance: ' + str(service_instance))
            guid = service_instance['name']
            pcf_services[service_name][i] = {'guid' : guid, 'ips' : []}
            guid_url = service_url + '|' + guid
            print ('guid_url: ' + guid_url)
            response = requests.get(guid_url, auth=(args.user_name, args.user_pass))
            response.raise_for_status();
            ips = response.json()
            print('ips: ' + str(ips))
            pcf_services[service_name][i]['ips'] = [None] * len(ips)
            for j, ip in enumerate(ips):
                 #pcf_services[service_name][i] = {'guid' : guid, 'ips' : []}
                 print('ip: ' + ip['name'])
                 pcf_services[service_name][i]['ips'][j] = ip['name']

    return pcf_services

def generate_dashboard(pcf_services, resources_parent_path, app, tier):
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
                                 RESOURCES_PARENT_PATH=resources_parent_path)
    return generated

    
def start_flask():
    app.run(debug=True, port=8082)

@app.route('/publish')
def publish():
    gen()
    return 'done!'
    
def run():
    args = parse_args()
    pcf_services = get_pcf_services(args)
    resources_parent_path = get_resources_parent_path(args)
    print('pcf_services: ' + str(pcf_services))
    print('resources_parent_path: ' + str(resources_parent_path))
    generated = generate_dashboard(pcf_services, resources_parent_path, args.app, args.tier)
    with open(pcf_dash_generated_file, 'w', encoding='utf-8') as myfile:
        myfile.write(generated)
    
if __name__ == '__main__':
    run()



    #start_flask()
